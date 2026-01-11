from dataclasses import dataclass
from typing import Dict, Optional


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
    ) -> None:
        self.anomaly_threshold = anomaly_threshold
        self.min_impact_per_volume = min_impact_per_volume
        self.take_profit_bps = take_profit_bps
        self.stop_loss_bps = stop_loss_bps
        self.time_stop_min = time_stop_min

    def generate_signal(
        self,
        market: str,
        mid: float,
        short_move: float,
        score: float,
        features: Dict[str, float],
        order_size: float,
    ) -> Optional[Signal]:
        if score < self.anomaly_threshold:
            return None
        impact_per_volume = features.get("impact_per_volume", 0.0)
        if impact_per_volume > self.min_impact_per_volume:
            return None
        if short_move == 0:
            return None
        side = "sell" if short_move > 0 else "buy"
        price = mid * (1 + (-0.0005 if side == "sell" else 0.0005))
        reason = "fade_micro_move"
        return Signal(
            market=market,
            side=side,
            price=price,
            size=order_size,
            reason=reason,
            score=score,
            features=features,
        )
