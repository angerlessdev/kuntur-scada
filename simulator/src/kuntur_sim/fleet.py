"""Reads the shared fleet declaration. The simulator only needs each device's kind, port and initial
conditions (the ``sim`` section, which the backend ignores)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

_ENV_REFERENCE = re.compile(r"\$\{(?P<name>[A-Z_][A-Z0-9_]*)(?::-(?P<default>[^}]*))?\}")


class FleetError(ValueError):
    """The fleet file is not valid."""


class Kind(StrEnum):
    UPS = "UPS"
    BARRIER = "BARRIER"
    CAMERA = "CAMERA"


@dataclass(frozen=True, slots=True)
class DeviceSpec:
    id: str
    kind: Kind
    port: int
    path: str = ""
    sim: Mapping[str, float] = field(default_factory=dict)


def expand_env(text: str, env: Mapping[str, str] | None = None) -> str:
    """Replaces ``${NAME}`` and ``${NAME:-default}``. A reference without a value or default is an error."""
    values = os.environ if env is None else env

    def substitute(match: re.Match[str]) -> str:
        name, default = match["name"], match["default"]
        if name in values:
            return values[name]
        if default is not None:
            return default
        raise FleetError(f"Environment variable {name} is not set and has no default")

    return _ENV_REFERENCE.sub(substitute, text)


def parse_fleet(raw: str, env: Mapping[str, str] | None = None) -> list[DeviceSpec]:
    try:
        document: Any = json.loads(expand_env(raw, env))
        specs = [_spec(entry) for entry in document["devices"]]
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, FleetError):
            raise
        raise FleetError(f"Invalid fleet file: {exc!r}") from exc
    ids = [spec.id for spec in specs]
    if len(ids) != len(set(ids)):
        raise FleetError("The fleet file repeats a device id")
    ports = [spec.port for spec in specs]
    if len(ports) != len(set(ports)):
        raise FleetError("Two devices share a port")
    return specs


def load_fleet(path: Path, env: Mapping[str, str] | None = None) -> list[DeviceSpec]:
    return parse_fleet(path.read_text(encoding="utf-8"), env)


def _spec(entry: Mapping[str, Any]) -> DeviceSpec:
    endpoint = entry["endpoint"]
    sim = {str(k): float(v) for k, v in entry.get("sim", {}).items()}
    return DeviceSpec(
        str(entry["id"]), Kind(entry["kind"]), int(endpoint["port"]), str(endpoint.get("path", "")), sim
    )
