"""Supervisory control use case. The command is audited before it reaches the device."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from kuntur.application.ports import (
    Clock,
    CommandExecutionError,
    DriverRegistry,
    EventPublisher,
    IdGenerator,
    UnitOfWorkFactory,
)
from kuntur.domain.commands import Command, CommandKind, ensure_command_allowed
from kuntur.domain.devices import Device
from kuntur.domain.errors import NotFoundError
from kuntur.domain.events import CommandFinished
from kuntur.domain.security import Actor, ensure_can_command

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IssueCommand:
    """Checks the actor and the device, audits the command as PENDING, sends it and records the
    outcome. Whatever the driver does, the audit log ends with SUCCEEDED or FAILED."""

    uow_factory: UnitOfWorkFactory
    drivers: DriverRegistry
    clock: Clock
    ids: IdGenerator
    publisher: EventPublisher
    timeout_s: float = 5.0

    async def __call__(self, actor: Actor, device_id: str, kind: CommandKind) -> Command:
        ensure_can_command(actor)
        device, command = await asyncio.to_thread(self._register, actor, device_id, kind)
        try:
            detail = await asyncio.wait_for(
                self.drivers.for_kind(device.kind).execute(device, kind), self.timeout_s
            )
            command.succeed(self.clock.now(), detail)
        except TimeoutError:
            command.fail(self.clock.now(), f"El equipo no respondió en {self.timeout_s:g} s")
        except CommandExecutionError as exc:
            command.fail(self.clock.now(), str(exc))
        except Exception as exc:  # the driver broke its contract: still close the audit entry
            logger.exception("Driver for %s crashed executing %s", device.id, kind)
            command.fail(self.clock.now(), f"Error interno del controlador ({type(exc).__name__})")
        await asyncio.to_thread(self._save, command)
        self.publisher.publish([CommandFinished.of(command)])
        return command

    def _register(self, actor: Actor, device_id: str, kind: CommandKind) -> tuple[Device, Command]:
        """Persists the PENDING command first: even if the process dies mid-way, the attempt is audited."""
        with self.uow_factory() as uow:
            device = uow.devices.get(device_id)
            if device is None:
                raise NotFoundError(f"Unknown device {device_id}")
            ensure_command_allowed(device, kind)
            command = Command(self.ids.new_id(), device.id, kind, actor.username, self.clock.now())
            uow.commands.add(command)
            uow.commit()
        return device, command

    def _save(self, command: Command) -> None:
        with self.uow_factory() as uow:
            uow.commands.update(command)
            uow.commit()
