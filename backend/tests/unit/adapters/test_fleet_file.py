import json
from pathlib import Path
from typing import Any

import pytest

from kuntur.adapters.fleet_file import FleetFileError, load_fleet, parse_fleet
from kuntur.domain.devices import DeviceKind

FLEET_FILE = Path(__file__).resolve().parents[4] / "config" / "fleet.json"


def test_the_shipped_fleet_file_builds_valid_devices() -> None:
    devices = load_fleet(FLEET_FILE, env={})
    assert {device.kind for device in devices} == set(DeviceKind)
    assert all(device.endpoint.host == "127.0.0.1" for device in devices)


def test_the_host_follows_the_environment() -> None:
    devices = load_fleet(FLEET_FILE, env={"KUNTUR_SIM_HOST": "simulator"})
    assert {device.endpoint.host for device in devices} == {"simulator"}


def _fleet(**changes: Any) -> str:
    device: dict[str, Any] = {
        "id": "ups-x",
        "name": "UPS",
        "kind": "UPS",
        "site": "Sitio",
        "installed_on": "2024-01-01",
        "endpoint": {"host": "h", "port": 1},
        "lifetime": {"design_life_years": 5, "battery_design_life_years": 3},
    }
    return json.dumps({"devices": [{**device, **changes}]})


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        _fleet(id="UPS MAL"),
        _fleet(kind="BARRIER", lifetime={"design_life_years": 5}),
        _fleet(endpoint={"host": "h", "port": 1, "usuario": "admin"}),
    ],
    ids=["no-devices-key", "invalid-id", "barrier-without-ratings", "unknown-endpoint-field"],
)
def test_an_invalid_declaration_says_why(raw: str) -> None:
    with pytest.raises(FleetFileError, match="Invalid fleet file"):
        parse_fleet(raw, {})


def test_a_missing_file_is_a_fleet_error(tmp_path: Path) -> None:
    with pytest.raises(FleetFileError, match="Cannot read"):
        load_fleet(tmp_path / "no-existe.json")
