import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests


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
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
    ) -> None:
        self.rest_base_url = rest_base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.session = requests.Session()

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
        markets = []
        for item in data.get("markets", data):
            markets.append(
                Market(
                    market_id=str(item.get("id") or item.get("market_id")),
                    title=item.get("title", ""),
                    status=item.get("status", ""),
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
        payload = response.json()
        trades = []
        for item in payload.get("trades", payload):
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
