import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from kuntur_sim.models import BarrierModel, CameraModel, CommandRejected, UpsModel, approach, poisson


def run(model: UpsModel | BarrierModel | CameraModel, seconds: float, dt: float = 1.0) -> None:
    for _ in range(round(seconds / dt)):
        model.tick(dt)


class TestUps:
    def test_without_grid_it_runs_on_battery_and_discharges(self) -> None:
        ups = UpsModel(random.Random(1), base_load_pct=50)
        ups.grid_ok = False
        run(ups, 60)
        assert ups.on_battery
        assert ups.input_voltage_v == 0
        # 10 min of autonomy at full load is 20 min at 50 %: one minute costs about 5 %
        assert ups.battery_charge_pct == pytest.approx(95, abs=0.6)

    def test_more_load_drains_the_battery_faster(self) -> None:
        light = UpsModel(random.Random(1), base_load_pct=20)
        heavy = UpsModel(random.Random(1), base_load_pct=80)
        for ups in (light, heavy):
            ups.grid_ok = False
            run(ups, 120)
        assert heavy.battery_charge_pct < light.battery_charge_pct

    def test_the_battery_settles_towards_the_room_temperature(self) -> None:
        ups = UpsModel(random.Random(1), ambient_c=25)
        ups.ambient_c = 48
        run(ups, 300)
        assert 47 < ups.battery_temp_c < 49.5

    def test_a_battery_test_is_brief_and_cannot_overlap(self) -> None:
        ups = UpsModel(random.Random(1))
        assert ups.battery_test() == "Prueba de batería iniciada"
        assert ups.on_battery
        with pytest.raises(CommandRejected) as busy:
            ups.battery_test()
        assert busy.value.busy
        run(ups, UpsModel.BATTERY_TEST_S)
        assert not ups.on_battery

    def test_there_is_no_battery_test_without_grid(self) -> None:
        ups = UpsModel(random.Random(1))
        ups.grid_ok = False
        with pytest.raises(CommandRejected) as refused:
            ups.battery_test()
        assert not refused.value.busy


class TestBarrier:
    def test_traffic_turns_into_cycles(self) -> None:
        barrier = BarrierModel(random.Random(7), traffic_per_min=6)
        run(barrier, 3600)
        assert 300 < barrier.cycles_total < 420  # 360 expected, three standard deviations

    def test_impacts_happen_only_when_injected(self) -> None:
        barrier = BarrierModel(random.Random(7), traffic_per_min=30)
        run(barrier, 600)
        assert barrier.impacts_total == 0
        barrier.impact()
        assert barrier.impacts_total == 1

    def test_held_open_it_stops_cycling_until_closed(self) -> None:
        barrier = BarrierModel(random.Random(7), traffic_per_min=30)
        assert barrier.open() == "Barrera abierta"
        assert barrier.open() == "La barrera ya estaba abierta"
        before = barrier.cycles_total
        run(barrier, 120)
        assert (barrier.cycles_total, barrier.position) == (before, "OPEN")
        assert barrier.close() == "Barrera cerrada"

    def test_a_faulted_barrier_refuses_commands(self) -> None:
        barrier = BarrierModel(random.Random(7))
        barrier.faulted = True
        with pytest.raises(CommandRejected):
            barrier.open()


class TestCamera:
    def test_the_clock_drifts_until_a_reboot_resyncs_it(self) -> None:
        camera = CameraModel(random.Random(3), clock_offset_s=100, drift_s_per_hour=36)
        run(camera, 100)
        assert camera.clock_offset_s == pytest.approx(101)
        assert camera.reboot() == "Reinicio en curso"
        with pytest.raises(CommandRejected):
            camera.reboot()
        run(camera, CameraModel.REBOOT_S)
        assert not camera.rebooting
        assert (camera.clock_offset_s, camera.uptime_s) == (0, 0)

    def test_the_device_time_carries_the_offset(self) -> None:
        now = datetime(2026, 1, 15, tzinfo=UTC)
        assert CameraModel(clock_offset_s=-30).device_time(now) == now - timedelta(seconds=30)


def test_the_same_seed_tells_the_same_story() -> None:
    def story(seed: int) -> tuple[float, float]:
        ups = UpsModel(random.Random(seed))
        run(ups, 50)
        return ups.load_pct, ups.battery_temp_c

    assert story(5) == story(5)
    assert story(5) != story(6)


def test_poisson_has_the_requested_mean() -> None:
    rng = random.Random(11)
    samples = [poisson(rng, 0.5) for _ in range(20_000)]
    assert sum(samples) / len(samples) == pytest.approx(0.5, abs=0.02)


def test_approach_is_a_first_order_lag() -> None:
    assert approach(0, 100, dt=10, tau=10) == pytest.approx(100 * (1 - math.exp(-1)))
