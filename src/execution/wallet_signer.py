import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from nacl.signing import SigningKey


@dataclass
class SignResult:
    headers: Dict[str, str]


class WalletSigner:
    def sign(self, payload: Dict[str, Any]) -> SignResult:
        raise NotImplementedError


class ExternalWalletSigner(WalletSigner):
    def __init__(self, signer_url: str) -> None:
        self.signer_url = signer_url
        self.session = requests.Session()

    def sign(self, payload: Dict[str, Any]) -> SignResult:
        response = self.session.post(self.signer_url, json={"payload": payload}, timeout=10)
        response.raise_for_status()
        data = response.json()
        signature = data.get("signature")
        public_key = data.get("public_key")
        if not signature or not public_key:
            raise ValueError("External signer response missing signature/public_key")
        headers = {
            "X-WALLET-SIGNATURE": signature,
            "X-WALLET-PUBLIC-KEY": public_key,
        }
        extra_headers = data.get("headers")
        if isinstance(extra_headers, dict):
            headers.update({str(k): str(v) for k, v in extra_headers.items()})
        return SignResult(headers=headers)


class PrivateKeyEnvSigner(WalletSigner):
    def __init__(self, private_key: str, public_key: Optional[str] = None) -> None:
        self.signing_key = SigningKey(_decode_key(private_key))
        self.public_key = public_key or self.signing_key.verify_key.encode().hex()

    def sign(self, payload: Dict[str, Any]) -> SignResult:
        message = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signed = self.signing_key.sign(message)
        signature = base64.b64encode(signed.signature).decode("utf-8")
        headers = {
            "X-WALLET-SIGNATURE": signature,
            "X-WALLET-PUBLIC-KEY": self.public_key,
        }
        return SignResult(headers=headers)


def _decode_key(value: str) -> bytes:
    sanitized = value.strip()
    if sanitized.startswith("0x"):
        return bytes.fromhex(sanitized[2:])
    try:
        return base64.b64decode(sanitized)
    except ValueError:
        return bytes.fromhex(sanitized)
