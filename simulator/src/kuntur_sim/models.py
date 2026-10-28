"""Physical models of the simulated devices.

Pure state machines: ``tick(dt)`` advances time, commands change state, nothing does I/O. With the
same seed the same story repeats, which keeps the tests and the alert-quality report reproducible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import ClassVar


class CommandRejected(Exception):  # noqa: N818 - it is an answer from the device, not a bug
    """The device refuses the command in its current state. ``busy`` means "try again later"."""

    def __init__(self, message: str, *, busy: bool = False) -> None:
        super().__init__(message)
        self.busy = busy


def approach(current: float, target: float, dt: float, tau: float) -> float:
    """First-order lag: moves ``current`` towards ``target`` with time constant ``tau`` seconds."""
    return target + (current - target) * math.exp(-dt / tau)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def poisson(rng: random.Random, mean: float) -> int:
    """Knuth's method; fine for the small means of a one-second tick."""
    threshold, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


@dataclass
class UpsModel:
    """A double-conversion UPS. On battery it discharges faster the higher the load; batteries warm
    up while they work and settle towards the room temperature."""

    rng: random.Random = field(default_factory=random.Random)
    ambient_c: float = 25.0
    base_load_pct: float = 40.0
    grid_ok: bool = True
    temp_sensor_ok: bool = True
    load_pct: float = 40.0
    battery_charge_pct: float = 100.0
    battery_temp_c: float = 25.0
    input_voltage_v: float = 220.0
    output_voltage_v: float = 220.0
    alarm_silenced: bool = False
    test_remaining_s: float = 0.0

    BATTERY_TEST_S: ClassVar[float] = 3.0
    AUTONOMY_AT_FULL_LOAD_MIN: ClassVar[float] = 10.0
    RECHARGE_PCT_PER_S: ClassVar[float] = 0.05
    NOMINAL_VOLTAGE_V: ClassVar[float] = 220.0

    def __post_init__(self) -> None:
        self.load_pct = self.base_load_pct
        self.battery_temp_c = self.ambient_c

    @property
    def on_battery(self) -> bool:
        return not self.grid_ok or self.test_remaining_s > 0

    @property
    def autonomy_min(self) -> float:
        """Minutes the battery lasts at the current load and charge."""
        full = self.AUTONOMY_AT_FULL_LOAD_MIN * 100 / max(self.load_pct, 5.0)
        return full * self.battery_charge_pct / 100

    def tick(self, dt: float) -> None:
        self.load_pct = clamp(
            approach(self.load_pct, self.base_load_pct, dt, 30) + self.rng.gauss(0, 0.4), 0, 100
        )
        self.test_remaining_s = max(0.0, self.test_remaining_s - dt)
        if self.on_battery:
            full_min = self.AUTONOMY_AT_FULL_LOAD_MIN * 100 / max(self.load_pct, 5.0)
            self.battery_charge_pct = max(0.0, self.battery_charge_pct - 100 * dt / (full_min * 60))
            heating = 6.0
        else:
            self.battery_charge_pct = min(100.0, self.battery_charge_pct + self.RECHARGE_PCT_PER_S * dt)
            heating = 2.0 if self.battery_charge_pct < 100 else 0.5  # noqa: PLR2004 - charging warms it
        self.battery_temp_c = approach(self.battery_temp_c, self.ambient_c + heating, dt, 60)
        self.battery_temp_c += self.rng.gauss(0, 0.03)
        self.input_voltage_v = self.NOMINAL_VOLTAGE_V + self.rng.gauss(0, 1.5) if self.grid_ok else 0.0
        powered = self.grid_ok or self.battery_charge_pct > 0
        self.output_voltage_v = self.NOMINAL_VOLTAGE_V + self.rng.gauss(0, 0.4) if powered else 0.0

    def battery_test(self) -> str:
        if not self.grid_ok:
            raise CommandRejected("Sin red eléctrica: no se puede probar la batería")
        if self.test_remaining_s > 0:
            raise CommandRejected("Ya hay una prueba de batería en curso", busy=True)
        if self.battery_charge_pct < 60:  # noqa: PLR2004 - vendor-style safety margin
            raise CommandRejected("Carga insuficiente para una prueba de batería")
        self.test_remaining_s = self.BATTERY_TEST_S
        return "Prueba de batería iniciada"

    def silence_alarm(self) -> str:
        self.alarm_silenced = True
        return "Alarma acústica silenciada"


@dataclass
class BarrierModel:
    """A vehicle barrier. Each passing vehicle is one open/close cycle; the motor warms up with the
    traffic. Impacts only happen when someone injects them."""

    rng: random.Random = field(default_factory=random.Random)
    traffic_per_min: float = 4.0
    cycles_total: int = 0
    impacts_total: int = 0
    ambient_c: float = 22.0
    motor_temp_c: float = 30.0
    position: str = "CLOSED"
    faulted: bool = False
    held_open: bool = False
    cycles_per_min: float = 0.0

    def tick(self, dt: float) -> None:
        arrivals = 0 if self.faulted or self.held_open else poisson(self.rng, self.traffic_per_min * dt / 60)
        self.cycles_total += arrivals
        self.cycles_per_min = approach(self.cycles_per_min, arrivals * 60 / dt, dt, 120)
        target = self.ambient_c + 8.0 + 0.9 * self.cycles_per_min
        self.motor_temp_c = approach(self.motor_temp_c, target, dt, 300) + self.rng.gauss(0, 0.03)
        if not self.held_open:
            self.position = "OPEN" if arrivals else "CLOSED"

    def impact(self) -> None:
        self.impacts_total += 1

    def open(self) -> str:
        if self.faulted:
            raise CommandRejected("Barrera en falla: el motor no responde")
        if self.held_open:
            return "La barrera ya estaba abierta"
        self.held_open, self.position = True, "OPEN"
        return "Barrera abierta"

    def close(self) -> str:
        if self.faulted:
            raise CommandRejected("Barrera en falla: el motor no responde")
        self.held_open, self.position = False, "CLOSED"
        return "Barrera cerrada"


@dataclass
class CameraModel:
    """An IP camera whose clock drifts until a reboot re-synchronises it with NTP."""

    rng: random.Random = field(default_factory=random.Random)
    clock_offset_s: float = 0.0
    drift_s_per_hour: float = 0.3
    recording: bool = True
    storage_free_pct: float = 40.0
    ambient_c: float = 24.0
    temperature_c: float = 42.0
    uptime_s: float = 86_400.0
    reboot_remaining_s: float = 0.0

    REBOOT_S: ClassVar[float] = 20.0

    @property
    def rebooting(self) -> bool:
        return self.reboot_remaining_s > 0

    def tick(self, dt: float) -> None:
        if self.rebooting:
            self.reboot_remaining_s = max(0.0, self.reboot_remaining_s - dt)
            if not self.rebooting:
                self.uptime_s, self.clock_offset_s = 0.0, 0.0  # NTP sync on boot
            return
        self.uptime_s += dt
        self.clock_offset_s += self.drift_s_per_hour * dt / 3600
        self.temperature_c = approach(self.temperature_c, self.ambient_c + 18, dt, 600) + self.rng.gauss(
            0, 0.03
        )
        # Recording fills the disk and the oldest footage is overwritten: free space hovers around 40 %
        self.storage_free_pct = clamp(
            approach(self.storage_free_pct, 40, dt, 900) + self.rng.gauss(0, 0.02), 0, 100
        )

    def device_time(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self.clock_offset_s)

    def reboot(self) -> str:
        if self.rebooting:
            raise CommandRejected("La cámara ya se está reiniciando", busy=True)
        self.reboot_remaining_s = self.REBOOT_S
        return "Reinicio en curso"
