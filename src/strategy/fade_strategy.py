from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional


@dataclass
class Signal:
    market: str
    side: str
    price: float
    size: float
    reason: str
    score: float
    features: Dict[str, float]


class FadeStrategy:
    def __init__(
        self,
        anomaly_threshold: float,
        min_impact_per_volume: float,
        take_profit_bps: int,
        stop_loss_bps: int,
        time_stop_min: int,
        atr_window: int = 14,
    ) -> None:
        self.anomaly_threshold = anomaly_threshold
        self.min_impact_per_volume = min_impact_per_volume
        self.take_profit_bps = take_profit_bps
        self.stop_loss_bps = stop_loss_bps
        self.time_stop_min = time_stop_min
        self.atr_window = atr_window
        self.price_history: Dict[str, Deque[float]] = {}

    def _update_atr(self, market: str, price: float) -> float:
        if market not in self.price_history:
            self.price_history[market] = deque(maxlen=self.atr_window + 1)
        self.price_history[market].append(price)
        if len(self.price_history[market]) < 2:
            return 0.0
        
        # Simple ATR-like proxy: mean of absolute returns over window
        returns = []
        prices = list(self.price_history[market])
        for i in range(1, len(prices)):
            returns.append(abs(prices[i] - prices[i-1]))
        return sum(returns) / len(returns)

    def generate_signal(
        self,
        market: str,
        mid: float,
        short_move: float,
        score: float,
        features: Dict[str, float],
        order_size: float,
    ) -> Optional[Signal]:
        atr = self._update_atr(market, mid)
        
        if score < self.anomaly_threshold:
            return None
        impact_per_volume = features.get("impact_per_volume", 0.0)
        if impact_per_volume > self.min_impact_per_volume:
            return None
        if short_move == 0:
            return None
            
        side = "sell" if short_move > 0 else "buy"
        
        # Volatility-adjusted price offset (optional)
        # Here we just use a small offset from mid
        price = mid * (1 + (-0.0005 if side == "sell" else 0.0005))
        
        # Calculate dynamic SL/TP if ATR is available
        # Default to BPS if ATR is 0 or not enough data
        tp_price = price * (1 + (self.take_profit_bps / 10000 if side == "buy" else -self.take_profit_bps / 10000))
        sl_price = price * (1 - (self.stop_loss_bps / 10000 if side == "buy" else -self.stop_loss_bps / 10000))

        if atr > 0:
            # TP at 2.0 * ATR, SL at 1.5 * ATR (example)
            if side == "buy":
                tp_price = max(tp_price, price + 2.0 * atr)
                sl_price = min(sl_price, price - 1.5 * atr)
            else:
                tp_price = min(tp_price, price - 2.0 * atr)
                sl_price = max(sl_price, price + 1.5 * atr)

        reason = "fade_micro_move_atr"
        features["atr"] = atr
        features["tp_price"] = tp_price
        features["sl_price"] = sl_price

        return Signal(
            market=market,
            side=side,
            price=price,
            size=order_size,
            reason=reason,
            score=score,
            features=features,
        )
