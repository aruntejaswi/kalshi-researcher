"""Kalshi V2 API request signing using RSA-PSS."""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


@dataclass
class SignedHeaders:
    key_id: str
    timestamp: str
    signature: str

    def as_dict(self) -> dict[str, str]:
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": self.signature,
            "KALSHI-ACCESS-TIMESTAMP": self.timestamp,
        }


def load_private_key(path: str | Path, password: bytes | None = None) -> rsa.RSAPrivateKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_private_key(data, password=password)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError("Kalshi requires an RSA private key")
    return key


def _now_ms() -> str:
    return str(int(time.time() * 1000))


def _strip_query(path: str) -> str:
    # Kalshi signs the path without query string.
    return path.split("?", 1)[0]


def sign_request(
    private_key: rsa.RSAPrivateKey,
    key_id: str,
    method: str,
    path: str,
    timestamp_ms: str | None = None,
) -> SignedHeaders:
    """Build the RSA-PSS signature for a Kalshi V2 request.

    The signed payload is: timestamp + method + path (path excludes query).
    """
    ts = timestamp_ms or _now_ms()
    message = (ts + method.upper() + _strip_query(path)).encode("utf-8")

    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=hashes.SHA256.digest_size,
        ),
        hashes.SHA256(),
    )
    return SignedHeaders(
        key_id=key_id,
        timestamp=ts,
        signature=base64.b64encode(signature).decode("ascii"),
    )
