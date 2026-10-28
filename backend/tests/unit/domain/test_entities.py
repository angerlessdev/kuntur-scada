from datetime import UTC, date, datetime, timedelta

import pytest

from kuntur.domain.alerts import Alert, AlertCode, AlertState, Severity
from kuntur.domain.commands import Command, CommandKind, CommandStatus, ensure_command_allowed
from kuntur.domain.devices import DeviceKind, Endpoint, LifetimeProfile
from kuntur.domain.errors import (
    CommandNotAllowedError,
    DomainValidationError,
    InvalidTransitionError,
    PermissionDeniedError,
)
from kuntur.domain.events import AlertRaised, AlertResolved, CommandFinished
from kuntur.domain.health import Health, assess_health
from kuntur.domain.readings import FailureCause, Reading, ReadingStatus
from kuntur.domain.security import Actor, Role, ensure_can_command
from tests.factories import T0, barrier, camera, failed, ok, ups


def _alert(code: AlertCode = AlertCode.UPS_BATTERY_HOT) -> Alert:
    return Alert("a-1", "ups-01", code, Severity.WARNING, "Temperatura alta", T0)


class TestDevices:
    @pytest.mark.parametrize("bad_id", ["", "U", "UPS-01", "ups_01", "-ups", "x" * 41])
    def test_rejects_invalid_ids(self, bad_id: str) -> None:
        with pytest.raises(DomainValidationError):
            ups(bad_id)

    def test_age_is_never_negative(self) -> None:
        device = ups(installed_on=date(2030, 1, 1))
        assert device.age_in_days(date(2026, 1, 1)) == 0
        assert ups(installed_on=date(2026, 1, 1)).age_in_days(date(2026, 1, 31)) == 30

    def test_each_kind_requires_its_wear_parameters(self) -> None:
        with pytest.raises(DomainValidationError):
            ups(lifetime=LifetimeProfile(design_life_years=10))
        with pytest.raises(DomainValidationError):
            ups(kind=DeviceKind.BARRIER)

    @pytest.mark.parametrize("port", [0, 65536])
    def test_endpoint_port_range(self, port: int) -> None:
        with pytest.raises(DomainValidationError):
            Endpoint("10.0.0.1", port)

    def test_lifetime_values_must_be_positive(self) -> None:
        with pytest.raises(DomainValidationError):
            LifetimeProfile(design_life_years=0)
        with pytest.raises(DomainValidationError):
            LifetimeProfile(design_life_years=5, rated_cycles=-1)


class TestReadings:
    def test_factories_keep_the_invariants(self) -> None:
        assert ok(0).status is ReadingStatus.OK
        assert ok(0).answered
        assert failed(0).status is ReadingStatus.FAILED
        assert not failed(0).answered
        partial = Reading.partial("cam", T0, {"latency_ms": 80}, FailureCause.INVALID_DATA, "sin imagen")
        assert partial.answered
        assert partial.cause is FailureCause.INVALID_DATA

    def test_metrics_cannot_be_changed_after_recording(self) -> None:
        source = {"load_pct": 40.0}
        reading = Reading.ok("ups-01", T0, source)
        source["load_pct"] = 99.0
        assert reading.metric("load_pct") == 40.0
        with pytest.raises(TypeError):
            reading.metrics["load_pct"] = 1.0  # type: ignore[index]

    @pytest.mark.parametrize(
        "build",
        [
            lambda: Reading("u", datetime(2026, 1, 1), ReadingStatus.OK),  # noqa: DTZ001 - naive on purpose
            lambda: Reading("u", T0, ReadingStatus.OK, cause=FailureCause.TIMEOUT),
            lambda: Reading("u", T0, ReadingStatus.FAILED),
            lambda: Reading("u", T0, ReadingStatus.FAILED, {"x": 1}, FailureCause.TIMEOUT),
            lambda: Reading("u", T0, ReadingStatus.PARTIAL, {}, FailureCause.INVALID_DATA),
        ],
    )
    def test_rejects_inconsistent_readings(self, build: object) -> None:
        with pytest.raises(DomainValidationError):
            build()  # type: ignore[operator]


class TestAlerts:
    def test_resolves_once(self) -> None:
        alert = _alert()
        alert.resolve(T0 + timedelta(minutes=5))
        assert alert.state is AlertState.RESOLVED
        assert alert.duration(T0 + timedelta(hours=1)) == timedelta(minutes=5)
        with pytest.raises(InvalidTransitionError):
            alert.resolve(T0 + timedelta(minutes=6))

    def test_cannot_resolve_before_it_was_raised(self) -> None:
        with pytest.raises(InvalidTransitionError):
            _alert().resolve(T0 - timedelta(seconds=1))

    def test_resolution_time_matches_the_state(self) -> None:
        with pytest.raises(DomainValidationError):
            Alert("a", "ups-01", AlertCode.UPS_BATTERY_HOT, Severity.WARNING, "x", T0, AlertState.RESOLVED)

    def test_events_are_snapshots(self) -> None:
        alert = _alert()
        raised = AlertRaised.of(alert)
        alert.resolve(T0 + timedelta(minutes=1))
        resolved = AlertResolved.of(alert)
        assert raised.alert.state is AlertState.ACTIVE
        assert resolved.alert.state is AlertState.RESOLVED
        assert resolved.occurred_at == T0 + timedelta(minutes=1)


class TestHealth:
    def test_colours(self) -> None:
        assert assess_health(None, []) is Health.UNKNOWN
        assert assess_health(ok(0), []) is Health.OK
        assert assess_health(failed(0), []) is Health.DEGRADED
        assert assess_health(ok(0), [_alert()]) is Health.DEGRADED
        assert assess_health(ok(0), [_alert(AlertCode.DEVICE_UNREACHABLE)]) is Health.DOWN

    def test_resolved_alerts_do_not_count(self) -> None:
        alert = _alert()
        alert.resolve(T0)
        assert assess_health(ok(0), [alert]) is Health.OK


class TestCommands:
    def _command(self) -> Command:
        return Command("c-1", "barrera-01", CommandKind.BARRIER_OPEN, "operador", T0)

    def test_lifecycle(self) -> None:
        command = self._command()
        command.succeed(T0 + timedelta(seconds=1), "abierta")
        assert command.status is CommandStatus.SUCCEEDED
        finished = CommandFinished.of(command)
        assert finished.command.detail == "abierta"
        with pytest.raises(InvalidTransitionError):
            command.fail(T0 + timedelta(seconds=2), "tarde")

    def test_cannot_finish_before_being_requested(self) -> None:
        with pytest.raises(InvalidTransitionError):
            self._command().fail(T0 - timedelta(seconds=1), "x")

    def test_needs_an_author_and_aware_time(self) -> None:
        with pytest.raises(DomainValidationError):
            Command("c", "b", CommandKind.BARRIER_OPEN, " ", T0)
        with pytest.raises(DomainValidationError):
            Command("c", "b", CommandKind.BARRIER_OPEN, "op", datetime(2026, 1, 1))  # noqa: DTZ001

    def test_only_commands_of_the_device_kind_are_allowed(self) -> None:
        ensure_command_allowed(barrier(), CommandKind.BARRIER_OPEN)
        ensure_command_allowed(camera(), CommandKind.CAMERA_REBOOT)
        with pytest.raises(CommandNotAllowedError):
            ensure_command_allowed(barrier(), CommandKind.CAMERA_REBOOT)

    def test_an_inactive_device_takes_no_commands(self) -> None:
        device = ups()
        device.active = False
        with pytest.raises(CommandNotAllowedError):
            ensure_command_allowed(device, CommandKind.UPS_BATTERY_TEST)


class TestSecurity:
    def test_only_operators_send_commands(self) -> None:
        ensure_can_command(Actor("ana", Role.OPERATOR))
        with pytest.raises(PermissionDeniedError):
            ensure_can_command(Actor("luis", Role.VIEWER))


def test_aware_datetimes_in_factories() -> None:
    assert T0.tzinfo is UTC
