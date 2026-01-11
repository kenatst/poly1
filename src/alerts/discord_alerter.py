import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import requests


@dataclass
class AlertMessage:
    kind: str
    payload: Dict[str, Any]


class DiscordAlerter:
    def __init__(self, webhook_url: str, throttle_sec: int, batch_size: int) -> None:
        self.webhook_url = webhook_url
        self.throttle_sec = throttle_sec
        self.batch_size = batch_size
        self.buffer: List[AlertMessage] = []
        self.last_sent = 0.0
        self.session = requests.Session()

    def enqueue(self, kind: str, payload: Dict[str, Any]) -> None:
        self.buffer.append(AlertMessage(kind=kind, payload=payload))

    def flush(self) -> None:
        now = time.time()
        if not self.buffer:
            return
        if now - self.last_sent < self.throttle_sec:
            return
        batch = self.buffer[: self.batch_size]
        self.buffer = self.buffer[self.batch_size :]
        content = "\n".join([self._format_message(msg) for msg in batch])
        if not self.webhook_url:
            self.last_sent = now
            return
        response = self.session.post(self.webhook_url, json={"content": content}, timeout=10)
        response.raise_for_status()
        self.last_sent = now

    def _format_message(self, msg: AlertMessage) -> str:
        payload = json.dumps(msg.payload, ensure_ascii=False)
        return f"[{msg.kind}] {payload}"
