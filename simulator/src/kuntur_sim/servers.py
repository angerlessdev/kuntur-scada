"""Helpers to run several network servers inside the simulator's single event loop."""

from __future__ import annotations

import asyncio
import contextlib
import socket
from collections.abc import Generator

import uvicorn
from fastapi import FastAPI


class EmbeddedUvicorn(uvicorn.Server):
    """A uvicorn server that leaves signal handling to the simulator: several of them share a process."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield


class HttpServer:
    def __init__(self, app: FastAPI, host: str, port: int) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._server: EmbeddedUvicorn | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> int:
        """Starts serving and returns the bound port (useful with port 0)."""
        family = socket.AF_INET6 if ":" in self._host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        port = int(sock.getsockname()[1])
        config = uvicorn.Config(self._app, log_level="warning", lifespan="off", access_log=False)
        self._server = EmbeddedUvicorn(config)
        self._task = asyncio.create_task(self._server.serve(sockets=[sock]), name=f"http-{port}")
        while not self._server.started:
            if self._task.done():
                self._task.result()  # surfaces the startup error
            await asyncio.sleep(0.01)
        return port

    async def stop(self) -> None:
        if self._server is not None and self._task is not None:
            self._server.should_exit = True
            await self._task
