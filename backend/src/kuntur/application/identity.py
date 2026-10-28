"""Identity use cases: sign in, know who is calling, keep the declared accounts in place."""

from __future__ import annotations

import math
import secrets
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from kuntur.application.ports import Clock, IssuedToken, PasswordHasher, TokenService, UnitOfWorkFactory
from kuntur.domain.errors import AuthenticationError, TooManyAttemptsError
from kuntur.domain.security import Actor, Role, User


@dataclass
class LoginLimiter:
    """At most ``max_failures`` failed sign-ins per account *and* origin within ``window``. Keyed by
    both, someone guessing from one machine is stopped without locking the account for its owner."""

    clock: Clock
    max_failures: int = 5
    window: timedelta = timedelta(minutes=15)
    _failures: dict[tuple[str, str], deque[datetime]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _recent(self, key: tuple[str, str], now: datetime) -> deque[datetime]:
        failures = self._failures.setdefault(key, deque())
        while failures and failures[0] <= now - self.window:
            failures.popleft()
        return failures

    def check(self, username: str, origin: str) -> None:
        now = self.clock.now()
        with self._lock:
            failures = self._recent((username, origin), now)
            if len(failures) >= self.max_failures:
                wait = failures[0] + self.window - now
                raise TooManyAttemptsError(max(1, math.ceil(wait.total_seconds())))

    def failed(self, username: str, origin: str) -> None:
        now = self.clock.now()
        with self._lock:
            self._recent((username, origin), now).append(now)

    def succeeded(self, username: str, origin: str) -> None:
        with self._lock:
            self._failures.pop((username, origin), None)


class Authenticate:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        tokens: TokenService,
        limiter: LoginLimiter,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._tokens = tokens
        self._limiter = limiter
        # Checked against when the account does not exist, so the answer takes the same time
        self._decoy_hash = hasher.hash(secrets.token_urlsafe(16))

    def __call__(self, username: str, password: str, origin: str) -> IssuedToken:
        username = username.strip().lower()
        self._limiter.check(username, origin)
        with self._uow_factory() as uow:
            user = uow.users.get(username)
        matches = self._hasher.verify(password, user.password_hash if user is not None else self._decoy_hash)
        if user is None or not user.active or not matches:
            self._limiter.failed(username, origin)
            raise AuthenticationError("Usuario o contraseña incorrectos")
        self._limiter.succeeded(username, origin)
        return self._tokens.issue(user.actor())


@dataclass(frozen=True, slots=True)
class ResolveActor:
    """Who is behind a token. The role is read from the account on every call, not trusted from the
    token, so taking a role away or deactivating someone applies at once."""

    uow_factory: UnitOfWorkFactory
    tokens: TokenService

    def __call__(self, token: str) -> Actor:
        username = self.tokens.subject(token)
        with self.uow_factory() as uow:
            user = uow.users.get(username)
        if user is None or not user.active:
            raise AuthenticationError("La sesión ya no es válida")
        return user.actor()


def ensure_accounts(
    uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, accounts: Mapping[str, tuple[Role, str]]
) -> int:
    """Creates or updates the declared accounts (role, password, active). Returns how many changed."""
    changed = 0
    with uow_factory() as uow:
        for username, (role, password) in accounts.items():
            current = uow.users.get(username)
            wanted = User(username, hasher.hash(password), role)
            if current is None:
                uow.users.add(wanted)
                changed += 1
            elif (
                current.role is not role
                or not current.active
                or not hasher.verify(password, current.password_hash)
            ):
                uow.users.update(wanted)
                changed += 1
        uow.commit()
    return changed
