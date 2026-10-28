from datetime import UTC, datetime, timedelta

import jwt
import pytest

from kuntur.adapters.security import Argon2PasswordHasher, JwtTokenService
from kuntur.domain.errors import AuthenticationError
from kuntur.domain.security import Actor, Role

SECRET = "clave-de-firma-solo-para-las-pruebas-0123456789"
ACTOR = Actor("operador", Role.OPERATOR)


def test_a_token_names_its_subject() -> None:
    tokens = JwtTokenService(SECRET, timedelta(minutes=5))
    issued = tokens.issue(ACTOR)
    assert tokens.subject(issued.token) == "operador"
    assert issued.expires_at > datetime.now(UTC)


def test_an_expired_token_is_refused() -> None:
    issued_an_hour_ago = JwtTokenService(
        SECRET, timedelta(minutes=5), now=lambda: datetime.now(UTC) - timedelta(hours=1)
    ).issue(ACTOR)
    with pytest.raises(AuthenticationError):
        JwtTokenService(SECRET, timedelta(minutes=5)).subject(issued_an_hour_ago.token)


@pytest.mark.parametrize(
    "token",
    [
        jwt.encode(
            {"sub": "operador", "iss": "kuntur", "iat": 0, "exp": 2**40},
            "otra-clave-de-32-bytes-o-mas-123456",
            "HS256",
        ),
        jwt.encode({"sub": "operador", "iss": "otro", "iat": 0, "exp": 2**40}, SECRET, "HS256"),
        jwt.encode({"sub": "operador", "iss": "kuntur"}, SECRET, "HS256"),
        "no.es.un-token",
    ],
    ids=["wrong-key", "wrong-issuer", "no-expiry", "garbage"],
)
def test_a_token_we_did_not_issue_is_refused(token: str) -> None:
    with pytest.raises(AuthenticationError):
        JwtTokenService(SECRET, timedelta(minutes=5)).subject(token)


def test_the_none_algorithm_is_refused() -> None:
    unsigned = jwt.encode({"sub": "operador", "iss": "kuntur", "iat": 0, "exp": 2**40}, None, "none")
    with pytest.raises(AuthenticationError):
        JwtTokenService(SECRET, timedelta(minutes=5)).subject(unsigned)


def test_a_short_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        JwtTokenService("corta", timedelta(minutes=5))


def test_argon2_hashes_verify_and_a_broken_hash_is_no_match() -> None:
    hasher = Argon2PasswordHasher()
    stored = hasher.hash("secreta")
    assert stored.startswith("$argon2id$")
    assert hasher.verify("secreta", stored)
    assert not hasher.verify("otra", stored)
    assert not hasher.verify("secreta", "no-es-un-hash")
