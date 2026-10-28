"""The collector: polls every active device on a fixed cadence, a bounded number at a time."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from kuntur.application.acquisition import PollDevice
from kuntur.application.ports import UnitOfWorkFactory
from kuntur.domain.devices import Device

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Collector:
    """Every ``interval_s`` it reads the fleet again (devices added or retired are picked up) and polls
    each device, at most ``max_concurrency`` at once. One device failing, even one whose reading cannot
    be stored, never stops the others. A round that overruns starts the next one at once instead of
    piling up."""

    poll: PollDevice
    uow_factory: UnitOfWorkFactory
    interval_s: float = 5.0
    max_concurrency: int = 16

    def _active_devices(self) -> list[Device]:
        with self.uow_factory() as uow:
            return uow.devices.list(active_only=True)

    async def run_once(self) -> int:
        """Polls the whole fleet once and returns how many devices were polled."""
        devices = await asyncio.to_thread(self._active_devices)
        slots = asyncio.Semaphore(self.max_concurrency)

        async def poll(device: Device) -> None:
            async with slots:
                try:
                    await self.poll(device)
                except Exception:
                    logger.exception("Could not poll or record %s", device.id)

        async with asyncio.TaskGroup() as group:
            for device in devices:
                group.create_task(poll(device), name=f"poll-{device.id}")
        return len(devices)

    async def run_forever(self, stop: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        next_round = loop.time()
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:  # the fleet could not be read (database down): try again next round
                logger.exception("Polling round failed")
            next_round = max(next_round + self.interval_s, loop.time())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), next_round - loop.time())
