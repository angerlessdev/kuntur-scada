"""Server side of HTTP Digest authentication (RFC 7616): SHA-256, ``qop=auth``, stateless nonces.

The nonce carries its own timestamp signed with a per-process key, so the server keeps no state. A real
camera should also track nonce counts against replays; a simulator does not need to.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.request import parse_http_list, parse_keqv_list

_REQUIRED = frozenset({"username", "realm", "nonce", "uri", "response", "qop", "nc", "cnonce"})


class DigestResult(StrEnum):
    OK = "OK"
    STALE = "STALE"
    """Right credentials, expired nonce: the client should retry with a fresh one."""
    DENIED = "DENIED"


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class DigestVerifier:
    realm: str
    username: str
    password: str = field(repr=False)
    nonce_ttl_s: float = 300.0
    clock: Callable[[], float] = time.time
    _key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    _opaque: str = field(default_factory=lambda: secrets.token_hex(16))

    def challenge(self, *, stale: bool = False) -> str:
        header = (
            f'Digest realm="{self.realm}", qop="auth", algorithm=SHA-256, '
            f'nonce="{self._new_nonce()}", opaque="{self._opaque}"'
        )
        return f"{header}, stale=true" if stale else header

    def verify(self, authorization: str | None, method: str, uri: str) -> DigestResult:
        if not authorization or authorization[:7].lower() != "digest ":
            return DigestResult.DENIED
        params = parse_keqv_list(parse_http_list(authorization[7:]))
        if not params.keys() >= _REQUIRED:
            return DigestResult.DENIED
        if (
            params["realm"] != self.realm
            or params["qop"] != "auth"
            or params.get("algorithm", "MD5").upper() != "SHA-256"
            or params["uri"] != uri
        ):
            return DigestResult.DENIED
        ha1 = _h(f"{params['username']}:{self.realm}:{self.password}")
        ha2 = _h(f"{method}:{params['uri']}")
        expected = _h(f"{ha1}:{params['nonce']}:{params['nc']}:{params['cnonce']}:auth:{ha2}")
        user_ok = hmac.compare_digest(params["username"], self.username)
        if not (hmac.compare_digest(expected, params["response"]) and user_ok):
            return DigestResult.DENIED
        issued_at = self._nonce_time(params["nonce"])
        if issued_at is None:
            return DigestResult.DENIED
        return DigestResult.OK if self.clock() - issued_at <= self.nonce_ttl_s else DigestResult.STALE

    def _sign(self, timestamp: str) -> str:
        return hmac.new(self._key, timestamp.encode(), hashlib.sha256).hexdigest()[:32]

    def _new_nonce(self) -> str:
        timestamp = str(int(self.clock()))
        return base64.urlsafe_b64encode(f"{timestamp}:{self._sign(timestamp)}".encode()).decode()

    def _nonce_time(self, nonce: str) -> float | None:
        """The nonce's issue time, or ``None`` if this server did not sign it."""
        try:
            timestamp, signature = base64.urlsafe_b64decode(nonce.encode()).decode().split(":")
        except ValueError:
            return None
        if not hmac.compare_digest(signature, self._sign(timestamp)):
            return None
        return float(timestamp)
