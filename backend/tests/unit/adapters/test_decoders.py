from datetime import timedelta
from typing import Any

import httpx
import pytest

from kuntur.adapters.drivers import barrier_websocket, camera_http, ups_modbus
from kuntur.adapters.drivers.failures import ProtocolViolation
from kuntur.domain.readings import FailureCause, ReadingStatus
from tests.factories import T0

REGISTERS = [412, 987, 312, 2201, 2199, 0, 26, 0b10]


class TestUps:
    def test_registers_become_scaled_metrics(self) -> None:
        reading = ups_modbus.decode("ups-01", T0, REGISTERS)
        assert reading.status is ReadingStatus.OK
        assert reading.metrics == {
            "load_pct": 41.2,
            "battery_charge_pct": 98.7,
            "battery_temp_c": 31.2,
            "input_voltage_v": 220.1,
            "output_voltage_v": 219.9,
            "on_battery": 0.0,
            "autonomy_min": 26.0,
            "battery_test": 0.0,
            "alarm_silenced": 1.0,
        }

    def test_a_negative_temperature_comes_as_twos_complement(self) -> None:
        registers = [*REGISTERS[:2], 0x10000 - 55, *REGISTERS[3:]]
        assert ups_modbus.decode("ups-01", T0, registers).metric("battery_temp_c") == -5.5

    def test_a_silent_sensor_makes_the_reading_partial(self) -> None:
        registers = [*REGISTERS[:2], ups_modbus.SENSOR_FAULT, *REGISTERS[3:]]
        reading = ups_modbus.decode("ups-01", T0, registers)
        assert (reading.status, reading.cause) == (ReadingStatus.PARTIAL, FailureCause.INVALID_DATA)
        assert reading.metric("battery_temp_c") is None
        assert reading.detail == "El sensor de temperatura de batería no da valor"

    def test_impossible_values_are_dropped_not_trusted(self) -> None:
        registers = [REGISTERS[0], 1500, REGISTERS[2], REGISTERS[3], REGISTERS[4], 7, *REGISTERS[6:]]
        reading = ups_modbus.decode("ups-01", T0, registers)
        assert reading.status is ReadingStatus.PARTIAL
        assert reading.metric("battery_charge_pct") is None
        assert reading.metric("on_battery") is None
        assert reading.detail == "Carga de batería imposible (150 %); estado de batería ilegible (7)"


STATUS: dict[str, Any] = {
    "op": "status",
    "position": "CLOSED",
    "cycles_total": 1_650_000,
    "impacts_total": 41,
    "motor_temp_c": 35.2,
    "fault": None,
}


class TestBarrier:
    def test_the_status_becomes_metrics(self) -> None:
        reading = barrier_websocket.decode("barrera-01", T0, STATUS)
        assert reading.status is ReadingStatus.OK
        assert reading.metrics == {
            "cycles_total": 1_650_000,
            "impacts_total": 41,
            "motor_temp_c": 35.2,
            "open": 0,
        }

    def test_a_reported_fault_keeps_the_values_and_says_so(self) -> None:
        reading = barrier_websocket.decode("barrera-01", T0, {**STATUS, "fault": "MOTOR"})
        assert (reading.status, reading.cause) == (ReadingStatus.PARTIAL, FailureCause.DEVICE_FAULT)
        assert reading.detail == "El controlador reporta falla: MOTOR"

    @pytest.mark.parametrize("bad", [{"impacts_total": -1}, {"cycles_total": True}, {"position": "MEDIO"}])
    def test_a_value_that_cannot_be_right_makes_it_partial(self, bad: dict[str, Any]) -> None:
        assert barrier_websocket.decode("barrera-01", T0, {**STATUS, **bad}).status is ReadingStatus.PARTIAL

    def test_an_answer_that_is_not_a_status_breaks_the_protocol(self) -> None:
        with pytest.raises(ProtocolViolation):
            barrier_websocket.decode("barrera-01", T0, {"op": "ack"})

    def test_nothing_valid_is_a_failed_reading(self) -> None:
        reading = barrier_websocket.decode("barrera-01", T0, {"op": "status"})
        assert (reading.status, reading.cause) == (ReadingStatus.FAILED, FailureCause.INVALID_DATA)


def _camera(body: Any, *, elapsed_ms: float = 0) -> httpx.Response:
    response = httpx.Response(200, json=body)
    response.elapsed = timedelta(milliseconds=elapsed_ms)
    return response


def _body(device_time: str) -> dict[str, Any]:
    return {
        "device_time": device_time,
        "recording": True,
        "storage_free_pct": 40.0,
        "temperature_c": 42.0,
        "uptime_s": 86_400,
    }


class TestCamera:
    def test_the_drift_is_measured_at_the_middle_of_the_round_trip(self) -> None:
        response = _camera(_body((T0 + timedelta(seconds=300.1)).isoformat()), elapsed_ms=200)
        reading = camera_http.decode("camara-01", T0, response)
        assert reading.status is ReadingStatus.OK
        assert reading.metric("clock_offset_s") == pytest.approx(300.0)

    def test_a_clock_behind_has_a_negative_offset_and_a_positive_drift(self) -> None:
        reading = camera_http.decode(
            "camara-01", T0, _camera(_body((T0 - timedelta(seconds=60)).isoformat()))
        )
        assert (reading.metric("clock_offset_s"), reading.metric("clock_drift_s")) == (-60, 60)

    def test_a_time_without_zone_cannot_be_compared(self) -> None:
        reading = camera_http.decode("camara-01", T0, _camera(_body("2026-01-15T08:00:00")))
        assert reading.status is ReadingStatus.PARTIAL
        assert reading.metric("clock_drift_s") is None
        assert reading.detail == "Hora del equipo ilegible"

    @pytest.mark.parametrize("body", ["<html>error</html>", ["no", "es", "objeto"]])
    def test_an_answer_that_is_not_a_json_object_breaks_the_protocol(self, body: Any) -> None:
        response = httpx.Response(200, text=body) if isinstance(body, str) else _camera(body)
        with pytest.raises(ProtocolViolation):
            camera_http.decode("camara-01", T0, response)
