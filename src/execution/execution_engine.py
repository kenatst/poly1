import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from src.execution.wallet_signer import WalletSigner

@dataclass
class OrderResponse:
    order_id: str
    status: str
    payload: Dict[str, Any]


class ExecutionEngine:
    def __init__(
        self,
        rest_base_url: str,
        api_key: Optional[str],
        api_secret: Optional[str],
        api_passphrase: Optional[str],
        trading_mode: str,
        rate_limit_per_minute: int,
        retry_attempts: int,
        retry_backoff_sec: float,
        wallet_signer: Optional[WalletSigner] = None,
    ) -> None:
        self.rest_base_url = rest_base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.trading_mode = trading_mode
        self.rate_limit_per_minute = rate_limit_per_minute
        self.retry_attempts = retry_attempts
        self.retry_backoff_sec = retry_backoff_sec
        self.wallet_signer = wallet_signer
        self.session = requests.Session()
        self.requests_sent = 0
        self.last_reset = time.time()

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        if self.api_passphrase:
            headers["X-API-PASSPHRASE"] = self.api_passphrase
        return headers

    def _rate_limit(self) -> None:
        now = time.time()
        if now - self.last_reset >= 60:
            self.requests_sent = 0
            self.last_reset = now
        if self.requests_sent >= self.rate_limit_per_minute:
            time.sleep(60 - (now - self.last_reset))
            self.requests_sent = 0
            self.last_reset = time.time()

    def place_order(self, payload: Dict[str, Any]) -> OrderResponse:
        self._rate_limit()
        if self.trading_mode != "live":
            return OrderResponse(order_id=f"sim-{uuid.uuid4().hex[:10]}", status="simulated", payload=payload)
        if self.wallet_signer is None:
            raise ValueError("Live trading requires a wallet signer")
        url = f"{self.rest_base_url}/orders"
        for attempt in range(self.retry_attempts):
            signer_headers = self.wallet_signer.sign(payload).headers
            headers = {**self._headers(), **signer_headers}
            response = self.session.post(url, json=payload, headers=headers, timeout=10)
            self.requests_sent += 1
            if response.status_code < 500:
                response.raise_for_status()
                return OrderResponse(
                    order_id=str(response.json().get("order_id", uuid.uuid4().hex)),
                    status="submitted",
                    payload=response.json(),
                )
            time.sleep(self.retry_backoff_sec * (attempt + 1))
        return OrderResponse(order_id=f"err-{uuid.uuid4().hex[:8]}", status="error", payload={"error": "retry_exhausted"})

    def cancel_order(self, order_id: str) -> OrderResponse:
        self._rate_limit()
        if self.trading_mode != "live":
            return OrderResponse(order_id=order_id, status="cancelled", payload={"mode": "simulated"})
        if self.wallet_signer is None:
            raise ValueError("Live trading requires a wallet signer")
        url = f"{self.rest_base_url}/orders/{order_id}"
        signer_headers = self.wallet_signer.sign({\"order_id\": order_id}).headers
        headers = {**self._headers(), **signer_headers}
        response = self.session.delete(url, headers=headers, timeout=10)
        self.requests_sent += 1
        response.raise_for_status()
        return OrderResponse(order_id=order_id, status="cancelled", payload=response.json())
