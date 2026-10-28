"""Command line entry point: ``kuntur-sim --fleet config/fleet.json``."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
from pathlib import Path

from kuntur_sim.control import create_control_app
from kuntur_sim.fleet import load_fleet
from kuntur_sim.servers import HttpServer
from kuntur_sim.simulator import Simulator

logger = logging.getLogger("kuntur_sim")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"Set {name} (see .env.example)")
    return value


async def serve(args: argparse.Namespace) -> None:
    sim = Simulator(
        load_fleet(args.fleet),
        camera_user=os.environ.get("KUNTUR_SIM_CAMERA_USER", "admin"),
        camera_password=_required_env("KUNTUR_SIM_CAMERA_PASSWORD"),
        bind_host=args.bind,
        seed=args.seed,
    )
    await sim.start()
    control = HttpServer(create_control_app(sim), args.bind, args.control_port)
    await control.start()
    logger.info("Control API on http://%s:%d/docs", args.bind, args.control_port)
    try:
        await asyncio.Event().wait()
    finally:
        await control.stop()
        await sim.stop()


def run() -> None:
    parser = argparse.ArgumentParser(
        prog="kuntur-sim", description="Simulador de equipos de campo para Kuntur SCADA"
    )
    parser.add_argument(
        "--fleet", type=Path, default=Path(os.environ.get("KUNTUR_FLEET_FILE", "config/fleet.json"))
    )
    parser.add_argument("--bind", default=os.environ.get("KUNTUR_SIM_BIND", "127.0.0.1"))
    parser.add_argument(
        "--control-port", type=int, default=int(os.environ.get("KUNTUR_SIM_CONTROL_PORT", "15000"))
    )
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # Every poll opens a connection: logging each one would bury the faults and scenarios worth reading
    for noisy in ("websockets", "pymodbus"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(args))


if __name__ == "__main__":
    run()
