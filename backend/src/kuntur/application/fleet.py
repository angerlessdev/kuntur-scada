"""Keeps the registered fleet in line with its declaration (idempotent, safe to run on every start)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from kuntur.application.ports import UnitOfWorkFactory
from kuntur.domain.devices import Device
from kuntur.domain.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class SyncReport:
    added: int
    updated: int
    retired: int


def sync_fleet(uow_factory: UnitOfWorkFactory, declared: Sequence[Device]) -> SyncReport:
    """Adds new devices, updates changed ones and takes out of service the ones no longer declared.
    Nothing is deleted: a retired device keeps its readings, alerts and audit log."""
    declared_ids = {device.id for device in declared}
    if len(declared_ids) != len(declared):
        raise DomainValidationError("The fleet declaration repeats a device id")

    added = updated = retired = 0
    with uow_factory() as uow:
        for device in declared:
            current = uow.devices.get(device.id)
            if current is None:
                uow.devices.add(device)
                added += 1
            elif current != device:
                uow.devices.update(device)
                updated += 1
        for current in uow.devices.list(active_only=True):
            if current.id not in declared_ids:
                uow.devices.update(replace(current, active=False))
                retired += 1
        uow.commit()
    return SyncReport(added, updated, retired)
