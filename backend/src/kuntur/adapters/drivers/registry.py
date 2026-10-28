"""Which driver speaks to which kind of device."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from kuntur.application.ports import DeviceDriver
from kuntur.domain.devices import DeviceKind


class StaticDriverRegistry:
    def __init__(self, drivers: Mapping[DeviceKind, DeviceDriver]) -> None:
        missing = set(DeviceKind) - set(drivers)
        if missing:
            raise ValueError(f"No driver for {sorted(missing)}")
        self._drivers = MappingProxyType(dict(drivers))

    def for_kind(self, kind: DeviceKind) -> DeviceDriver:
        return self._drivers[kind]
