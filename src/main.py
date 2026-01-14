import json
import time
from datetime import datetime, timezone
from typing import Dict, List

from src.alerts.discord_alerter import DiscordAlerter
from src.config import load_config
from src.data.polymarket_client import PolymarketClient
from src.data.storage import OrderBookSnapshot, SignalRecord, SqliteStorage, Trade
from src.execution.execution_engine import ExecutionEngine
from src.execution.wallet_signer import ExternalWalletSigner, PrivateKeyEnvSigner, WalletSigner
from src.features.anomaly_detector import AnomalyDetector, OrderBookView
from src.data.polymarket_client import TradePrint, OrderBook
from src.risk.risk_manager import RiskManager
from src.strategy.fade_strategy import FadeStrategy


def _select_markets(client: PolymarketClient, allowlist: List[str], top_n: int | None) -> List[str]:
    if allowlist:
        return allowlist
    markets = client.list_markets(limit=top_n or 200)
    markets = [m for m in markets if m.status.lower() == "active"]
    markets.sort(key=lambda m: m.volume, reverse=True)
    if top_n:
        markets = markets[:top_n]
    return [m.market_id for m in markets]


def _parse_orderbook(orderbook_payload: Dict[str, List[List[float]]]) -> OrderBookView:
    bids = [(float(price), float(size)) for price, size in orderbook_payload.get("bids", [])]
    asks = [(float(price), float(size)) for price, size in orderbook_payload.get("asks", [])]
    best_bid = bids[0][0] if bids else 0.0
    best_ask = asks[0][0] if asks else 0.0
    return OrderBookView(best_bid=best_bid, best_ask=best_ask, bids=bids, asks=asks)


def _short_move(detector: AnomalyDetector, market: str, window_sec: int = 60) -> float:
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - window_sec
    history = [mid for ts, mid in detector.mid_history[market] if ts.timestamp() >= cutoff]
    if len(history) < 2:
        return 0.0
    return history[-1] - history[0]


def _build_wallet_signer(mode: str, polymarket_config) -> WalletSigner | None:
    if mode == "external":
        if not polymarket_config.wallet_signer_url:
            return None
        return ExternalWalletSigner(polymarket_config.wallet_signer_url)
    if mode == "private_key_env":
        if not polymarket_config.private_key:
            return None
        return PrivateKeyEnvSigner(
            private_key=polymarket_config.private_key,
            public_key=polymarket_config.wallet_public_key,
        )
    return None


def _resolve_order_size(config) -> float:
    percent = config.execution.order_size_percent_wallet
    if percent is None:
        return config.execution.order_size_default
    balance = config.execution.wallet_balance_override
    if balance is None:
        raise ValueError("order_size_percent_wallet requires WALLET_BALANCE_OVERRIDE")
    return balance * percent


def run() -> None:
    config = load_config("config.yaml")
    storage = SqliteStorage("data.sqlite")

    client = PolymarketClient(
        rest_base_url=config.polymarket.rest_base_url,
        ws_url=config.polymarket.ws_url,
        api_key=config.polymarket.api_key,
        api_secret=config.polymarket.api_secret,
        api_passphrase=config.polymarket.api_passphrase,
    )

    detector = AnomalyDetector(
        volume_windows_sec=config.detector.volume_windows_sec,
        baseline_window_sec=config.detector.baseline_window_sec,
        churn_window_sec=config.detector.churn_window_sec,
        repeat_print_window_sec=config.detector.repeat_print_window_sec,
        spread_window_sec=config.detector.spread_window_sec,
        imbalance_depth_levels=config.detector.imbalance_depth_levels,
    )

    strategy = FadeStrategy(
        anomaly_threshold=config.strategy.anomaly_threshold,
        min_impact_per_volume=config.strategy.min_impact_per_volume,
        take_profit_bps=config.strategy.take_profit_bps,
        stop_loss_bps=config.strategy.stop_loss_bps,
        time_stop_min=config.strategy.time_stop_min,
        atr_window=config.strategy.atr_window,
    )

    wallet_signer = _build_wallet_signer(config.polymarket.wallet_signer_mode, config.polymarket)
    order_size = _resolve_order_size(config)
    execution = ExecutionEngine(
        rest_base_url=config.polymarket.rest_base_url,
        api_key=config.polymarket.api_key,
        api_secret=config.polymarket.api_secret,
        api_passphrase=config.polymarket.api_passphrase,
        trading_mode=config.trading_mode,
        rate_limit_per_minute=config.execution.rate_limit_per_minute,
        retry_attempts=config.execution.retry_attempts,
        retry_backoff_sec=config.execution.retry_backoff_sec,
        wallet_signer=wallet_signer,
    )

    risk = RiskManager(
        max_position_per_market=config.risk.max_position_per_market,
        max_global_exposure=config.risk.max_global_exposure,
        max_daily_loss=config.risk.max_daily_loss,
        max_orders_per_minute=config.risk.max_orders_per_minute,
    )

    alerter = DiscordAlerter(
        webhook_url=config.alerts.discord_webhook_url,
        throttle_sec=config.alerts.throttle_sec,
        batch_size=config.alerts.batch_size,
    )

    markets = _select_markets(client, config.allowlist_markets, config.top_n_by_volume)
    alerter.enqueue("HEALTH", {"event": "startup", "markets": markets, "mode": config.trading_mode})
    alerter.flush()

    def on_trade(trade: TradePrint):
        trade_model = Trade(
            market=trade.market_id,
            trade_id=trade.trade_id,
            price=trade.price,
            size=trade.size,
            side=trade.side,
            timestamp=trade.timestamp,
        )
        storage.insert_trades([trade_model])
        detector.update(trade.market_id, [trade_model], detector.last_orderbook.get(trade.market_id))

    def on_orderbook(ob: OrderBook):
        storage.insert_orderbook(
            OrderBookSnapshot(
                market=ob.market_id,
                timestamp=ob.timestamp,
                bids=json.dumps(ob.bids),
                asks=json.dumps(ob.asks),
            )
        )
        view = _parse_orderbook({"bids": ob.bids, "asks": ob.asks})
        detector.update(ob.market_id, [], view)

    # Initialize detector last_orderbook if not present
    if not hasattr(detector, "last_orderbook"):
        detector.last_orderbook = {}

    client.start_ws(markets, on_trade=on_trade, on_orderbook=on_orderbook)

    try:
        while True:
            for market in markets:
                orderbook_view = detector.last_orderbook.get(market)
                if not orderbook_view:
                    continue

                score, features = detector.score(market, orderbook_view)
                short_move = _short_move(detector, market)
                signal = strategy.generate_signal(
                    market=market,
                    mid=orderbook_view.mid,
                    short_move=short_move,
                    score=score,
                    features=features,
                    order_size=order_size,
                )

                storage.insert_signal(
                    SignalRecord(
                        market=market,
                        timestamp=datetime.now(timezone.utc),
                        score=score,
                        payload=json.dumps(features),
                    )
                )

                if signal:
                    alerter.enqueue(
                        "SIGNAL",
                        {
                            "market": signal.market,
                            "side": signal.side,
                            "price": signal.price,
                            "score": signal.score,
                            "features": signal.features,
                        },
                    )
                    if risk.check_order(signal.market, signal.size, signal.price):
                        payload = {
                            "market": signal.market,
                            "side": signal.side,
                            "price": signal.price,
                            "size": signal.size,
                            "type": "limit",
                        }
                        order_response = execution.place_order(payload)
                        risk.record_order()
                        alerter.enqueue(
                            "ORDER",
                            {
                                "market": signal.market,
                                "order_id": order_response.order_id,
                                "status": order_response.status,
                                "payload": order_response.payload,
                            },
                        )
                    else:
                        alerter.enqueue("RISK", {"market": signal.market, "reason": "risk_block"})
                alerter.flush()
            time.sleep(config.data_poll_sec)
    finally:
        client.stop_ws()


if __name__ == "__main__":
    run()
