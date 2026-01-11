from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List

from src.data.storage import SqliteStorage


@dataclass
class BacktestResult:
    total_pnl: float
    max_drawdown: float
    hit_rate: float


def compute_drawdown(equity_curve: List[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = peak - value
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd


def replay_fills(storage: SqliteStorage, market: str) -> Iterable[Dict[str, str]]:
    cursor = storage.connection.cursor()
    cursor.execute(
        "SELECT order_id, price, size, timestamp FROM fills WHERE market = ? ORDER BY timestamp ASC",
        (market,),
    )
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        yield dict(zip(columns, row))


def backtest(storage_path: str, market: str) -> BacktestResult:
    storage = SqliteStorage(storage_path)
    pnl = 0.0
    equity_curve = [0.0]
    hits = 0
    total = 0
    position = 0.0
    average_price = 0.0

    for fill in replay_fills(storage, market):
        size = float(fill["size"])
        price = float(fill["price"])
        total += 1
        if position == 0:
            position = size
            average_price = price
            continue
        pnl_change = (price - average_price) * position
        pnl += pnl_change
        equity_curve.append(pnl)
        if pnl_change > 0:
            hits += 1
        position += size
        average_price = price

    hit_rate = hits / total if total else 0.0
    result = BacktestResult(
        total_pnl=pnl,
        max_drawdown=compute_drawdown(equity_curve),
        hit_rate=hit_rate,
    )
    storage.close()
    return result
