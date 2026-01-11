import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional


@dataclass
class Trade:
    market: str
    trade_id: str
    price: float
    size: float
    side: str
    timestamp: datetime


@dataclass
class OrderBookSnapshot:
    market: str
    timestamp: datetime
    bids: str
    asks: str


@dataclass
class SignalRecord:
    market: str
    timestamp: datetime
    score: float
    payload: str


@dataclass
class OrderRecord:
    market: str
    timestamp: datetime
    order_id: str
    side: str
    price: float
    size: float
    status: str
    payload: str


@dataclass
class FillRecord:
    market: str
    timestamp: datetime
    order_id: str
    price: float
    size: float
    payload: str


class SqliteStorage:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trades (
                market TEXT,
                trade_id TEXT,
                price REAL,
                size REAL,
                side TEXT,
                timestamp TEXT,
                PRIMARY KEY (market, trade_id)
            );
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                market TEXT,
                timestamp TEXT,
                bids TEXT,
                asks TEXT
            );
            CREATE TABLE IF NOT EXISTS signals (
                market TEXT,
                timestamp TEXT,
                score REAL,
                payload TEXT
            );
            CREATE TABLE IF NOT EXISTS orders (
                market TEXT,
                timestamp TEXT,
                order_id TEXT,
                side TEXT,
                price REAL,
                size REAL,
                status TEXT,
                payload TEXT
            );
            CREATE TABLE IF NOT EXISTS fills (
                market TEXT,
                timestamp TEXT,
                order_id TEXT,
                price REAL,
                size REAL,
                payload TEXT
            );
            """
        )
        self.connection.commit()

    def insert_trades(self, trades: Iterable[Trade]) -> int:
        cursor = self.connection.cursor()
        count = 0
        for trade in trades:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO trades VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        trade.market,
                        trade.trade_id,
                        trade.price,
                        trade.size,
                        trade.side,
                        trade.timestamp.isoformat(),
                    ),
                )
                if cursor.rowcount:
                    count += 1
            except sqlite3.Error:
                continue
        self.connection.commit()
        return count

    def insert_orderbook(self, snapshot: OrderBookSnapshot) -> None:
        self.connection.execute(
            "INSERT INTO orderbook_snapshots VALUES (?, ?, ?, ?)",
            (
                snapshot.market,
                snapshot.timestamp.isoformat(),
                snapshot.bids,
                snapshot.asks,
            ),
        )
        self.connection.commit()

    def insert_signal(self, signal: SignalRecord) -> None:
        self.connection.execute(
            "INSERT INTO signals VALUES (?, ?, ?, ?)",
            (
                signal.market,
                signal.timestamp.isoformat(),
                signal.score,
                signal.payload,
            ),
        )
        self.connection.commit()

    def insert_order(self, order: OrderRecord) -> None:
        self.connection.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order.market,
                order.timestamp.isoformat(),
                order.order_id,
                order.side,
                order.price,
                order.size,
                order.status,
                order.payload,
            ),
        )
        self.connection.commit()

    def insert_fill(self, fill: FillRecord) -> None:
        self.connection.execute(
            "INSERT INTO fills VALUES (?, ?, ?, ?, ?, ?)",
            (
                fill.market,
                fill.timestamp.isoformat(),
                fill.order_id,
                fill.price,
                fill.size,
                fill.payload,
            ),
        )
        self.connection.commit()

    def fetch_trades(self, market: str, since: Optional[str] = None) -> Iterable[Dict[str, Any]]:
        cursor = self.connection.cursor()
        if since:
            cursor.execute(
                "SELECT market, trade_id, price, size, side, timestamp FROM trades WHERE market = ? AND timestamp >= ? ORDER BY timestamp ASC",
                (market, since),
            )
        else:
            cursor.execute(
                "SELECT market, trade_id, price, size, side, timestamp FROM trades WHERE market = ? ORDER BY timestamp ASC",
                (market,),
            )
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            yield dict(zip(columns, row))

    def close(self) -> None:
        self.connection.close()
