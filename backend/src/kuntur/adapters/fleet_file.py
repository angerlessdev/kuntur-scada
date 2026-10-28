"""Reads the fleet declaration (``config/fleet.json``) into devices.

``${NAME}`` and ``${NAME:-default}`` are expanded first, with the same syntax as the simulator; the
few lines are repeated on purpose so that neither package depends on the other.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from kuntur.domain.devices import Device, DeviceKind, Endpoint, LifetimeProfile
from kuntur.domain.errors import DomainValidationError

_ENV_REFERENCE = re.compile(r"\$\{(?P<name>[A-Z_][A-Z0-9_]*)(?::-(?P<default>[^}]*))?\}")


class FleetFileError(ValueError):
    """The fleet file cannot be used. The message says where."""


class _Endpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str
    port: int
    path: str = ""


class _Lifetime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design_life_years: float
    rated_cycles: int | None = None
    rated_impacts: int | None = None
    battery_design_life_years: float | None = None


class _Device(BaseModel):
    model_config = ConfigDict(extra="ignore")  # the "sim" section belongs to the simulator
    id: str
    name: str
    kind: DeviceKind
    site: str
    endpoint: _Endpoint
    installed_on: date
    lifetime: _Lifetime
    active: bool = True


class _Fleet(BaseModel):
    devices: list[_Device]


def expand_env(text: str, env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env

    def substitute(match: re.Match[str]) -> str:
        name, default = match["name"], match["default"]
        if name in values:
            return values[name]
        if default is not None:
            return default
        raise FleetFileError(f"Environment variable {name} is not set and has no default")

    return _ENV_REFERENCE.sub(substitute, text)


def parse_fleet(raw: str, env: Mapping[str, str] | None = None) -> list[Device]:
    try:
        fleet = _Fleet.model_validate_json(expand_env(raw, env))
        devices = [
            Device(
                entry.id,
                entry.name,
                entry.kind,
                entry.site,
                Endpoint(**entry.endpoint.model_dump()),
                entry.installed_on,
                LifetimeProfile(**entry.lifetime.model_dump()),
                entry.active,
            )
            for entry in fleet.devices
        ]
    except (ValidationError, DomainValidationError) as exc:
        raise FleetFileError(f"Invalid fleet file: {exc}") from exc
    ids = [device.id for device in devices]
    if len(ids) != len(set(ids)):
        raise FleetFileError("The fleet file repeats a device id")
    return devices


def load_fleet(path: Path, env: Mapping[str, str] | None = None) -> list[Device]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FleetFileError(f"Cannot read the fleet file {path}: {exc.strerror}") from exc
    return parse_fleet(raw, env)
