from datetime import timedelta

import pytest

from kuntur.adapters.persistence.memory import InMemoryStore, InMemoryUnitOfWork
from kuntur.application.identity import Authenticate, LoginLimiter, ResolveActor, ensure_accounts
from kuntur.application.ports import IssuedToken, UnitOfWork, UnitOfWorkFactory
from kuntur.domain.errors import AuthenticationError, TooManyAttemptsError
from kuntur.domain.security import Actor, Role, User
from tests.factories import T0
from tests.fakes import FakeClock


class PlainHasher:
    """Readable stand-in for Argon2: the tests are about the rules, not the hashing."""

    def __init__(self) -> None:
        self.verified = 0

    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        self.verified += 1
        return password_hash == f"hash:{password}"


class EchoTokens:
    def issue(self, actor: Actor) -> IssuedToken:
        return IssuedToken(f"token-{actor.username}", T0, actor)

    def subject(self, token: str) -> str:
        if not token.startswith("token-"):
            raise AuthenticationError("Sesión inválida o vencida")
        return token.removeprefix("token-")


@pytest.fixture
def uow_factory() -> UnitOfWorkFactory:
    store = InMemoryStore()

    def factory() -> UnitOfWork:
        return InMemoryUnitOfWork(store)

    ensure_accounts(factory, PlainHasher(), {"operador": (Role.OPERATOR, "secreta")})
    return factory


def _authenticate(
    factory: UnitOfWorkFactory, clock: FakeClock | None = None
) -> tuple[Authenticate, PlainHasher]:
    hasher = PlainHasher()
    return Authenticate(factory, hasher, EchoTokens(), LoginLimiter(clock or FakeClock())), hasher


def test_the_right_password_issues_a_token(uow_factory: UnitOfWorkFactory) -> None:
    authenticate, _ = _authenticate(uow_factory)
    assert authenticate(" Operador", "secreta", "10.0.0.1").actor == Actor("operador", Role.OPERATOR)


def test_an_unknown_account_costs_the_same_hash_check(uow_factory: UnitOfWorkFactory) -> None:
    authenticate, hasher = _authenticate(uow_factory)
    with pytest.raises(AuthenticationError):
        authenticate("nadie", "secreta", "10.0.0.1")
    assert hasher.verified == 1  # the decoy hash was checked: no timing difference to exploit


def test_an_inactive_account_cannot_sign_in(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory() as uow:
        uow.users.update(User("operador", "hash:secreta", Role.OPERATOR, active=False))
        uow.commit()
    authenticate, _ = _authenticate(uow_factory)
    with pytest.raises(AuthenticationError):
        authenticate("operador", "secreta", "10.0.0.1")


class TestLimiter:
    def test_five_failures_lock_the_pair_until_the_window_passes(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        clock = FakeClock()
        authenticate, _ = _authenticate(uow_factory, clock)
        for _ in range(5):
            with pytest.raises(AuthenticationError):
                authenticate("operador", "mal", "10.0.0.1")
        with pytest.raises(TooManyAttemptsError) as locked:
            authenticate("operador", "secreta", "10.0.0.1")
        assert locked.value.retry_after_s == 15 * 60
        assert authenticate("operador", "secreta", "10.0.0.2")  # another origin is not locked out
        clock.advance(timedelta(minutes=15))
        assert authenticate("operador", "secreta", "10.0.0.1")

    def test_a_success_clears_the_failures(self, uow_factory: UnitOfWorkFactory) -> None:
        authenticate, _ = _authenticate(uow_factory)
        for _ in range(4):
            with pytest.raises(AuthenticationError):
                authenticate("operador", "mal", "10.0.0.1")
        authenticate("operador", "secreta", "10.0.0.1")
        for _ in range(4):
            with pytest.raises(AuthenticationError):
                authenticate("operador", "mal", "10.0.0.1")


def test_the_role_comes_from_the_account_not_from_the_token(uow_factory: UnitOfWorkFactory) -> None:
    resolve = ResolveActor(uow_factory, EchoTokens())
    assert resolve("token-operador").role is Role.OPERATOR
    with uow_factory() as uow:
        uow.users.update(User("operador", "hash:secreta", Role.VIEWER))
        uow.commit()
    assert resolve("token-operador").role is Role.VIEWER
    with pytest.raises(AuthenticationError):
        resolve("token-nadie")


def test_declared_accounts_are_kept_in_line(uow_factory: UnitOfWorkFactory) -> None:
    hasher = PlainHasher()
    assert ensure_accounts(uow_factory, hasher, {"operador": (Role.OPERATOR, "secreta")}) == 0
    assert ensure_accounts(uow_factory, hasher, {"operador": (Role.OPERATOR, "nueva")}) == 1
    assert ensure_accounts(uow_factory, hasher, {"visitante": (Role.VIEWER, "mirar")}) == 1
    with uow_factory() as uow:
        assert [uow.users.get(name) for name in ("operador", "visitante")] == [
            User("operador", "hash:nueva", Role.OPERATOR),
            User("visitante", "hash:mirar", Role.VIEWER),
        ]
