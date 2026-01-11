from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


@dataclass
class MarketExposure:
    position: float = 0.0
    notional: float = 0.0


@dataclass
class RiskState:
    exposures: Dict[str, MarketExposure] = field(default_factory=dict)
    realized_pnl: float = 0.0
    orders_last_minute: int = 0
    last_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RiskManager:
    def __init__(
        self,
        max_position_per_market: float,
        max_global_exposure: float,
        max_daily_loss: float,
        max_orders_per_minute: int,
        kill_switch_file: str = "KILL_SWITCH",
    ) -> None:
        self.max_position_per_market = max_position_per_market
        self.max_global_exposure = max_global_exposure
        self.max_daily_loss = max_daily_loss
        self.max_orders_per_minute = max_orders_per_minute
        self.kill_switch_file = kill_switch_file
        self.state = RiskState()

    def _reset_rate_limit(self) -> None:
        now = datetime.now(timezone.utc)
        delta = (now - self.state.last_reset).total_seconds()
        if delta >= 60:
            self.state.orders_last_minute = 0
            self.state.last_reset = now

    def kill_switch_active(self) -> bool:
        return Path(self.kill_switch_file).exists()

    def check_order(self, market: str, size: float, price: float) -> bool:
        if self.kill_switch_active():
            return False
        self._reset_rate_limit()
        if self.state.orders_last_minute >= self.max_orders_per_minute:
            return False
        exposure = self.state.exposures.get(market, MarketExposure())
        projected_position = exposure.position + size
        projected_notional = abs(projected_position * price)
        if projected_notional > self.max_position_per_market:
            return False
        total_exposure = sum(abs(exp.position) for exp in self.state.exposures.values()) + abs(size)
        if total_exposure > self.max_global_exposure:
            return False
        if self.state.realized_pnl <= -abs(self.max_daily_loss):
            return False
        return True

    def record_order(self) -> None:
        self._reset_rate_limit()
        self.state.orders_last_minute += 1

    def record_fill(self, market: str, filled_size: float, price: float, pnl: float) -> None:
        exposure = self.state.exposures.get(market)
        if exposure is None:
            exposure = MarketExposure()
            self.state.exposures[market] = exposure
        exposure.position += filled_size
        exposure.notional = exposure.position * price
        self.state.realized_pnl += pnl
