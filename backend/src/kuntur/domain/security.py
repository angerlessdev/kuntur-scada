"""Who may do what. Authentication lives in the adapters; the policy lives here."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from kuntur.domain.errors import DomainValidationError, PermissionDeniedError

_USERNAME = re.compile(r"^[a-z][a-z0-9._-]{2,39}$")


class Role(StrEnum):
    VIEWER = "VIEWER"
    """Reads everything, changes nothing."""
    OPERATOR = "OPERATOR"
    """Can also send commands to devices."""


@dataclass(frozen=True, slots=True)
class Actor:
    username: str
    role: Role


@dataclass(slots=True)
class User:
    """An account. Only the password's hash is kept, and it never shows in a repr or a log."""

    username: str
    password_hash: str = field(repr=False)
    role: Role
    active: bool = True

    def __post_init__(self) -> None:
        if not _USERNAME.fullmatch(self.username):
            raise DomainValidationError(
                f"Invalid username {self.username!r}: use 3-40 lowercase letters, digits, '.', '-' or '_'"
            )
        if not self.password_hash:
            raise DomainValidationError("A user needs a password hash")

    def actor(self) -> Actor:
        return Actor(self.username, self.role)


def ensure_can_command(actor: Actor) -> None:
    if actor.role is not Role.OPERATOR:
        raise PermissionDeniedError(f"{actor.username} ({actor.role}) cannot send commands")
