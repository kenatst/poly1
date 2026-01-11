from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Deque, Dict, Iterable, List, Tuple

from src.data.storage import Trade


@dataclass
class OrderBookView:
    best_bid: float
    best_ask: float
    bids: List[Tuple[float, float]]
    asks: List[Tuple[float, float]]

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid


class AnomalyDetector:
    def __init__(self, volume_windows_sec: List[int], baseline_window_sec: int, churn_window_sec: int,
                 repeat_print_window_sec: int, spread_window_sec: int, imbalance_depth_levels: int) -> None:
        self.volume_windows_sec = volume_windows_sec
        self.baseline_window_sec = baseline_window_sec
        self.churn_window_sec = churn_window_sec
        self.repeat_print_window_sec = repeat_print_window_sec
        self.spread_window_sec = spread_window_sec
        self.imbalance_depth_levels = imbalance_depth_levels
        self.trade_history: Dict[str, Deque[Trade]] = defaultdict(deque)
        self.mid_history: Dict[str, Deque[Tuple[datetime, float]]] = defaultdict(deque)
        self.spread_history: Dict[str, Deque[Tuple[datetime, float]]] = defaultdict(deque)

    def _trim(self, market: str, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.baseline_window_sec)
        trades = self.trade_history[market]
        while trades and trades[0].timestamp < cutoff:
            trades.popleft()
        mids = self.mid_history[market]
        while mids and mids[0][0] < cutoff:
            mids.popleft()
        spreads = self.spread_history[market]
        while spreads and spreads[0][0] < cutoff:
            spreads.popleft()

    def update(self, market: str, trades: Iterable[Trade], orderbook: OrderBookView) -> None:
        now = datetime.now(timezone.utc)
        for trade in trades:
            self.trade_history[market].append(trade)
        self.mid_history[market].append((now, orderbook.mid))
        self.spread_history[market].append((now, orderbook.spread))
        self._trim(market, now)

    def _window_trades(self, market: str, window_sec: int) -> List[Trade]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_sec)
        return [trade for trade in self.trade_history[market] if trade.timestamp >= cutoff]

    def _volume(self, trades: Iterable[Trade]) -> float:
        return sum(trade.size for trade in trades)

    def _mid_delta(self, market: str, window_sec: int) -> float:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_sec)
        mids = [mid for ts, mid in self.mid_history[market] if ts >= cutoff]
        if len(mids) < 2:
            return 0.0
        return mids[-1] - mids[0]

    def _repeat_print_score(self, market: str) -> float:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.repeat_print_window_sec)
        recent = [trade for trade in self.trade_history[market] if trade.timestamp >= cutoff]
        if not recent:
            return 0.0
        buckets: Dict[str, int] = defaultdict(int)
        for trade in recent:
            key = f"{trade.price:.4f}:{trade.size:.4f}"
            buckets[key] += 1
        repeats = [count for count in buckets.values() if count > 1]
        if not repeats:
            return 0.0
        return min(1.0, sum(repeats) / len(recent))

    def _spread_regime(self, market: str) -> float:
        spreads = [spread for _, spread in self.spread_history[market]]
        if not spreads:
            return 0.0
        median = sorted(spreads)[len(spreads) // 2]
        current = spreads[-1]
        if median == 0:
            return 0.0
        return min(1.0, current / median)

    def _orderbook_imbalance(self, orderbook: OrderBookView) -> float:
        bid_depth = sum(size for _, size in orderbook.bids[: self.imbalance_depth_levels])
        ask_depth = sum(size for _, size in orderbook.asks[: self.imbalance_depth_levels])
        total = bid_depth + ask_depth
        if total == 0:
            return 0.0
        return (bid_depth - ask_depth) / total

    def score(self, market: str, orderbook: OrderBookView) -> Tuple[float, Dict[str, float]]:
        now = datetime.now(timezone.utc)
        self._trim(market, now)
        explain: Dict[str, float] = {}

        baseline_trades = self._window_trades(market, self.baseline_window_sec)
        baseline_volume = self._volume(baseline_trades)
        baseline_volumes = []
        for window in self.volume_windows_sec:
            window_trades = self._window_trades(market, window)
            volume = self._volume(window_trades)
            baseline_volumes.append(volume)
            explain[f"volume_{window}s"] = volume
        baseline_mean = mean(baseline_volumes) if baseline_volumes else 0.0
        baseline_std = pstdev(baseline_volumes) if len(baseline_volumes) > 1 else 0.0
        z_scores = []
        for volume in baseline_volumes:
            if baseline_std == 0:
                z_scores.append(0.0)
            else:
                z_scores.append((volume - baseline_mean) / baseline_std)
        volume_spike_z = max(z_scores) if z_scores else 0.0
        explain["volume_spike_z"] = volume_spike_z

        churn_trades = self._window_trades(market, self.churn_window_sec)
        churn_volume = self._volume(churn_trades)
        churn_mid_delta = abs(self._mid_delta(market, self.churn_window_sec))
        churn_ratio = churn_volume / churn_mid_delta if churn_mid_delta else 0.0
        explain["churn_ratio"] = churn_ratio

        repeat_print_score = self._repeat_print_score(market)
        explain["repeat_print_score"] = repeat_print_score

        impact_per_volume = churn_mid_delta / churn_volume if churn_volume else 0.0
        explain["impact_per_volume"] = impact_per_volume

        spread_regime = self._spread_regime(market)
        explain["spread_regime"] = spread_regime

        orderbook_imbalance = self._orderbook_imbalance(orderbook)
        explain["orderbook_imbalance"] = orderbook_imbalance

        normalized_spike = min(1.0, max(0.0, volume_spike_z / 3.0))
        churn_signal = min(1.0, churn_ratio / (baseline_volume + 1.0))
        score = (
            0.35 * normalized_spike
            + 0.2 * repeat_print_score
            + 0.15 * min(1.0, spread_regime / 2.0)
            + 0.2 * min(1.0, abs(orderbook_imbalance))
            + 0.1 * min(1.0, churn_signal)
        )
        score = max(0.0, min(1.0, score))
        explain["anomaly_score"] = score
        return score, explain
