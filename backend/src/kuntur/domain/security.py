"""Who may do what. Authentication lives in the adapters; the policy lives here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kuntur.domain.errors import PermissionDeniedError


class Role(StrEnum):
    VIEWER = "VIEWER"
    """Reads everything, changes nothing."""
    OPERATOR = "OPERATOR"
    """Can also send commands to devices."""


@dataclass(frozen=True, slots=True)
class Actor:
    username: str
    role: Role


def ensure_can_command(actor: Actor) -> None:
    if actor.role is not Role.OPERATOR:
        raise PermissionDeniedError(f"{actor.username} ({actor.role}) cannot send commands")
