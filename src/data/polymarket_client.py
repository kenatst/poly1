import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests
import websockets
from websockets.sync.client import connect


@dataclass
class Market:
    market_id: str
    title: str
    status: str
    volume: float


@dataclass
class OrderBook:
    market_id: str
    bids: List[List[float]]
    asks: List[List[float]]
    timestamp: datetime


@dataclass
class TradePrint:
    market_id: str
    trade_id: str
    price: float
    size: float
    side: str
    timestamp: datetime


class PolymarketClient:
    def __init__(
        self,
        rest_base_url: str,
        ws_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
    ) -> None:
        self.rest_base_url = rest_base_url.rstrip("/")
        self.ws_url = ws_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.session = requests.Session()
        self._ws = None
        self._ws_thread: Optional[threading.Thread] = None
        self._on_trade: Optional[Callable[[TradePrint], None]] = None
        self._on_orderbook: Optional[Callable[[OrderBook], None]] = None
        self._running = False

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        if self.api_passphrase:
            headers["X-API-PASSPHRASE"] = self.api_passphrase
        return headers

    def list_markets(self, limit: int = 200) -> List[Market]:
        url = f"{self.rest_base_url}/markets"
        response = self.session.get(url, headers=self._headers(), params={"limit": limit}, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Handle different response formats (list vs dict with 'markets' key)
        if isinstance(data, dict):
            items = data.get("markets", [])
            # if 'markets' not found, and it's a dict, maybe it's not a list of markets
            if not items and not isinstance(items, list):
                items = [data] # assume single market object
        elif isinstance(data, list):
            items = data
        else:
            items = []

        markets = []
        for item in items:
            if not isinstance(item, dict):
                continue
            markets.append(
                Market(
                    market_id=str(item.get("id") or item.get("condition_id") or item.get("market_id")),
                    title=item.get("title", item.get("question", "")),
                    status=item.get("status", "active"),
                    volume=float(item.get("volume", 0)),
                )
            )
        return markets

    def get_orderbook(self, market_id: str) -> OrderBook:
        url = f"{self.rest_base_url}/markets/{market_id}/orderbook"
        response = self.session.get(url, headers=self._headers(), timeout=10)
        response.raise_for_status()
        payload = response.json()
        bids = payload.get("bids", [])
        asks = payload.get("asks", [])
        return OrderBook(
            market_id=market_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
        )

    def get_recent_trades(self, market_id: str, limit: int = 200) -> List[TradePrint]:
        url = f"{self.rest_base_url}/markets/{market_id}/trades"
        response = self.session.get(url, headers=self._headers(), params={"limit": limit}, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, dict):
            items = data.get("trades", [])
        elif isinstance(data, list):
            items = data
        else:
            items = []

        trades = []
        for item in items:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("timestamp") or item.get("time")
            if isinstance(timestamp, (int, float)):
                ts = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else datetime.now(timezone.utc)
            trades.append(
                TradePrint(
                    market_id=market_id,
                    trade_id=str(item.get("id") or item.get("trade_id")),
                    price=float(item.get("price")),
                    size=float(item.get("size")),
                    side=item.get("side", ""),
                    timestamp=ts,
                )
            )
        return trades

    def poll_trades(self, market_id: str, sleep_sec: int = 5) -> Iterable[List[TradePrint]]:
        while True:
            yield self.get_recent_trades(market_id)
            time.sleep(sleep_sec)

    def start_ws(
        self,
        market_ids: List[str],
        on_trade: Optional[Callable[[TradePrint], None]] = None,
        on_orderbook: Optional[Callable[[OrderBook], None]] = None,
    ) -> None:
        if not self.ws_url:
            raise ValueError("WS URL not configured")
        self._on_trade = on_trade
        self._on_orderbook = on_orderbook
        self._running = True
        self._ws_thread = threading.Thread(target=self._ws_loop, args=(market_ids,), daemon=True)
        self._ws_thread.start()

    def stop_ws(self) -> None:
        self._running = False
        if self._ws_thread:
            self._ws_thread.join(timeout=5)

    def _ws_loop(self, market_ids: List[str]) -> None:
        while self._running:
            try:
                with connect(self.ws_url) as ws:
                    self._ws = ws
                    # Polymarket CLOB WS subscription format
                    subscribe_msg = {
                        "type": "subscribe",
                        "market_ids": market_ids,
                        "channels": ["trades", "orderbook"],
                    }
                    ws.send(json.dumps(subscribe_msg))

                    while self._running:
                        message = ws.recv()
                        self._handle_ws_message(json.loads(message))
            except Exception as e:
                print(f"WS error: {e}. Retrying in 5s...")
                time.sleep(5)

    def _handle_ws_message(self, data: Dict[str, Any]) -> None:
        msg_type = data.get("type")
        market_id = data.get("market_id")
        if not market_id:
            return

        if msg_type == "trades" and self._on_trade:
            for item in data.get("trades", []):
                trade = TradePrint(
                    market_id=market_id,
                    trade_id=str(item.get("id")),
                    price=float(item.get("price")),
                    size=float(item.get("size")),
                    side=item.get("side", ""),
                    timestamp=datetime.fromtimestamp(item.get("timestamp"), tz=timezone.utc)
                    if item.get("timestamp")
                    else datetime.now(timezone.utc),
                )
                self._on_trade(trade)

        elif msg_type == "orderbook" and self._on_orderbook:
            ob = OrderBook(
                market_id=market_id,
                bids=data.get("bids", []),
                asks=data.get("asks", []),
                timestamp=datetime.now(timezone.utc),
            )
            self._on_orderbook(ob)
