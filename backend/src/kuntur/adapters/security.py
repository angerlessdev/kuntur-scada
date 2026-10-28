"""Security adapters: Argon2id password hashes and signed JWT access tokens."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from kuntur.application.ports import IssuedToken
from kuntur.domain.errors import AuthenticationError
from kuntur.domain.security import Actor

MIN_SECRET_BYTES = 32


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hash = PasswordHash((Argon2Hasher(),))

    def hash(self, password: str) -> str:
        return self._hash.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hash.verify(password, password_hash)
        except Exception:
            return False


class JwtTokenService:
    """HS256 tokens with issuer, issue and expiry times. Expiry follows the wall clock on purpose: a
    simulated clock must never stretch a session."""

    ALGORITHM = "HS256"

    def __init__(
        self,
        secret: str,
        ttl: timedelta,
        *,
        issuer: str = "kuntur",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if len(secret.encode()) < MIN_SECRET_BYTES:
            raise ValueError(f"The token secret needs at least {MIN_SECRET_BYTES} bytes")
        self._secret = secret
        self._ttl = ttl
        self._issuer = issuer
        self._now = now

    def issue(self, actor: Actor) -> IssuedToken:
        issued_at = self._now()
        expires_at = issued_at + self._ttl
        payload = {
            "sub": actor.username,
            "role": actor.role.value,
            "iss": self._issuer,
            "iat": issued_at,
            "exp": expires_at,
            "jti": uuid.uuid4().hex,
        }
        return IssuedToken(jwt.encode(payload, self._secret, algorithm=self.ALGORITHM), expires_at, actor)

    def subject(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self.ALGORITHM],
                issuer=self._issuer,
                options={"require": ["sub", "iss", "iat", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Sesión inválida o vencida") from exc
        return str(payload["sub"])
