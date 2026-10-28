"""Field devices: what is supervised and how to reach it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from kuntur.domain.errors import DomainValidationError

_DEVICE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")


class DeviceKind(StrEnum):
    """Each kind speaks its own protocol and has its own wear model."""

    UPS = "UPS"
    BARRIER = "BARRIER"
    CAMERA = "CAMERA"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Network address of a device. ``path`` is used by HTTP devices."""

    host: str
    port: int
    path: str = ""

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise DomainValidationError("Endpoint host cannot be empty")
        if not 1 <= self.port <= 65535:  # noqa: PLR2004 - TCP port range
            raise DomainValidationError(f"Port out of range: {self.port}")


@dataclass(frozen=True, slots=True)
class LifetimeProfile:
    """Nominal design values feeding the remaining-life clocks.

    ``design_life_years`` applies to every device (calendar ageing). Barriers add the
    mechanism's rated cycles and impacts (Palmgren-Miner) and UPS add the battery's
    design life at 25 °C.
    """

    design_life_years: float
    rated_cycles: int | None = None
    rated_impacts: int | None = None
    battery_design_life_years: float | None = None

    def __post_init__(self) -> None:
        if self.design_life_years <= 0:
            raise DomainValidationError("Design life must be positive")
        for name in ("rated_cycles", "rated_impacts", "battery_design_life_years"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise DomainValidationError(f"{name} must be positive")


@dataclass(slots=True)
class Device:
    """A supervised field device. Identity is the ``id`` slug (e.g. ``ups-norte-01``)."""

    id: str
    name: str
    kind: DeviceKind
    site: str
    endpoint: Endpoint
    installed_on: date
    lifetime: LifetimeProfile
    active: bool = True

    def __post_init__(self) -> None:
        if not _DEVICE_ID.fullmatch(self.id):
            raise DomainValidationError(
                f"Invalid device id {self.id!r}: use 2-40 lowercase letters, digits or dashes"
            )
        if not self.name.strip():
            raise DomainValidationError("Device name cannot be empty")
        if not self.site.strip():
            raise DomainValidationError("Device site cannot be empty")
        if self.kind is DeviceKind.BARRIER and (
            self.lifetime.rated_cycles is None or self.lifetime.rated_impacts is None
        ):
            raise DomainValidationError("A barrier needs rated cycles and rated impacts")
        if self.kind is DeviceKind.UPS and self.lifetime.battery_design_life_years is None:
            raise DomainValidationError("A UPS needs the battery design life")

    def age_in_days(self, today: date) -> int:
        """Days in service, never negative (a device installed in the future has age 0)."""
        return max((today - self.installed_on).days, 0)
