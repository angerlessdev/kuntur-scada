import asyncio
from collections.abc import AsyncIterator

import pytest

from kuntur_sim.faults import FaultConfig, FaultMode, FaultProxy


async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(1024):
        writer.write(data)
        await writer.drain()
    writer.close()


@pytest.fixture
async def proxy() -> AsyncIterator[FaultProxy]:
    echo = await asyncio.start_server(_echo, "127.0.0.1", 0)
    proxy = FaultProxy("eco", ("127.0.0.1", 0), ("127.0.0.1", echo.sockets[0].getsockname()[1]))
    await proxy.start()
    yield proxy
    await proxy.stop()
    echo.close()


async def _roundtrip(port: int, within_s: float = 3.0) -> bytes:
    reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), within_s)
    try:
        writer.write(b"ping")
        await writer.drain()
        return await asyncio.wait_for(reader.read(4), within_s)
    finally:
        writer.close()


async def test_traffic_goes_through_untouched(proxy: FaultProxy) -> None:
    assert await _roundtrip(proxy.port) == b"ping"


async def test_down_refuses_connections_and_comes_back_on_the_same_port(proxy: FaultProxy) -> None:
    port = proxy.port
    await proxy.apply(FaultConfig(FaultMode.DOWN))
    with pytest.raises(OSError):  # refused (or, on Windows, slow to be refused)
        await _roundtrip(port)
    await proxy.apply(FaultConfig())
    assert await _roundtrip(port) == b"ping"


async def test_timeout_accepts_but_never_answers(proxy: FaultProxy) -> None:
    await proxy.apply(FaultConfig(FaultMode.TIMEOUT))
    with pytest.raises(TimeoutError):
        await _roundtrip(proxy.port, within_s=0.3)


async def test_slow_delays_every_answer(proxy: FaultProxy) -> None:
    await proxy.apply(FaultConfig(FaultMode.SLOW, delay_s=0.3))
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await _roundtrip(proxy.port) == b"ping"
    assert loop.time() - started >= 0.3


async def test_flapping_alternates_until_cleared(proxy: FaultProxy) -> None:
    await proxy.apply(FaultConfig(FaultMode.FLAPPING, period_s=0.5))
    assert proxy.listening
    await asyncio.sleep(0.75)
    assert not proxy.listening
    await asyncio.sleep(0.5)
    assert proxy.listening
    await proxy.apply(FaultConfig())
    assert proxy.listening


async def test_a_mode_change_drops_open_connections(proxy: FaultProxy) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    await asyncio.sleep(0.05)
    await proxy.apply(FaultConfig(FaultMode.SLOW, delay_s=0))
    try:
        assert await asyncio.wait_for(reader.read(10), 1) == b""
    except ConnectionResetError:
        pass  # an abort may surface as a reset instead of a clean end of stream
    finally:
        writer.close()
