"""TCP fault proxy: sits in front of every simulated device and breaks the network on demand.

Working at the TCP level keeps it protocol-agnostic, so Modbus, WebSocket and HTTP fail exactly the way
a real field network makes them fail, and each driver has to classify the failure on its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class FaultMode(StrEnum):
    NONE = "NONE"
    """Transparent: traffic goes straight through."""
    DOWN = "DOWN"
    """Nothing listens: connections are refused, as with a device that lost power."""
    TIMEOUT = "TIMEOUT"
    """Connections are accepted and requests swallowed: a hung device or a black-holed route."""
    SLOW = "SLOW"
    """Every answer is delayed by ``delay_s``: a saturated link."""
    FLAPPING = "FLAPPING"
    """Alternates DOWN and NONE every ``period_s``: a loose cable or a dying switch port."""


@dataclass(frozen=True, slots=True)
class FaultConfig:
    mode: FaultMode = FaultMode.NONE
    delay_s: float = 3.0
    period_s: float = 15.0

    def __post_init__(self) -> None:
        if self.delay_s < 0 or self.period_s <= 0:
            raise ValueError("delay_s must be >= 0 and period_s > 0")


class FaultProxy:
    def __init__(self, name: str, listen: tuple[str, int], target: tuple[str, int]) -> None:
        self.name = name
        self._listen = listen
        self._target = target
        self._config = FaultConfig()
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.StreamWriter] = set()
        self._handlers: set[asyncio.Task[object]] = set()
        self._flapper: asyncio.Task[None] | None = None

    @property
    def config(self) -> FaultConfig:
        return self._config

    @property
    def listening(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        if self._server is None:
            return self._listen[1]
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        await self._open()

    async def stop(self) -> None:
        await self._stop_flapping()
        await self._close()
        # Wait for the connection handlers so their device-side sockets close while the loop still runs
        for handler in self._handlers:
            handler.cancel()
        await asyncio.gather(*self._handlers, return_exceptions=True)

    async def apply(self, config: FaultConfig) -> None:
        """Switches mode. Open connections are dropped so the new mode applies at once, even to
        clients that keep their connection alive."""
        await self._stop_flapping()
        self._config = config
        if config.mode is FaultMode.DOWN:
            await self._close()
            return
        await self._open()
        self._drop_connections()
        if config.mode is FaultMode.FLAPPING:
            self._flapper = asyncio.create_task(self._flap(config.period_s), name=f"flap-{self.name}")
        logger.info("%s: fault mode %s", self.name, config.mode)

    async def _flap(self, period_s: float) -> None:
        while True:
            await asyncio.sleep(period_s)
            await self._close()
            await asyncio.sleep(period_s)
            await self._open()

    async def _stop_flapping(self) -> None:
        if self._flapper is not None:
            self._flapper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flapper
            self._flapper = None

    async def _open(self) -> None:
        if self._server is None:
            host, port = self._listen
            self._server = await asyncio.start_server(self._handle, host, port)
            # Keep the real port: with port 0 the system picks one, and it must survive a reopen
            self._listen = (host, self.port)

    async def _close(self) -> None:
        if self._server is not None:
            server, self._server = self._server, None
            server.close()
            self._drop_connections()

    def _drop_connections(self) -> None:
        for writer in list(self._connections):
            writer.transport.abort()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handler = asyncio.current_task()
        if handler is not None:
            self._handlers.add(handler)
        self._connections.add(writer)
        try:
            mode = self._config.mode
            if mode is FaultMode.TIMEOUT:
                while await reader.read(65_536):
                    pass  # swallow everything, answer nothing
                return
            try:
                device_reader, device_writer = await asyncio.open_connection(*self._target)
            except OSError:
                logger.warning("%s: the device process is not listening", self.name)
                return
            delay = self._config.delay_s if mode is FaultMode.SLOW else 0.0
            await asyncio.gather(
                self._pipe(reader, device_writer, 0.0),
                self._pipe(device_reader, writer, delay),
            )
        except (ConnectionError, OSError):
            pass  # the client or the device went away: nothing to clean beyond the finally
        finally:
            self._connections.discard(writer)
            if handler is not None:
                self._handlers.discard(handler)
            writer.close()

    @staticmethod
    async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, delay_s: float) -> None:
        try:
            while data := await reader.read(65_536):
                if delay_s:
                    await asyncio.sleep(delay_s)
                writer.write(data)
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
