from pathlib import Path

import pytest

from kuntur_sim.fleet import FleetError, Kind, expand_env, load_fleet, parse_fleet

FLEET_FILE = Path(__file__).resolve().parents[2] / "config" / "fleet.json"


def _fleet(*devices: tuple[str, int]) -> str:
    entries = ",".join(f'{{"id": "{i}", "kind": "UPS", "endpoint": {{"port": {p}}}}}' for i, p in devices)
    return f'{{"devices": [{entries}]}}'


def test_the_shipped_fleet_file_is_valid() -> None:
    specs = load_fleet(FLEET_FILE, env={})
    assert {spec.kind for spec in specs} == set(Kind)
    assert all(spec.path.startswith("/cameras/") for spec in specs if spec.kind is Kind.CAMERA)


def test_env_references_take_the_value_or_the_default() -> None:
    assert expand_env("${SIM_HOST:-127.0.0.1}", {}) == "127.0.0.1"
    assert expand_env("${SIM_HOST:-127.0.0.1}", {"SIM_HOST": "simulator"}) == "simulator"
    with pytest.raises(FleetError, match="SIM_HOST"):
        expand_env("${SIM_HOST}", {})


def test_repeated_ids_and_shared_ports_are_rejected() -> None:
    with pytest.raises(FleetError, match="repeats"):
        parse_fleet(_fleet(("ups-a", 1), ("ups-a", 2)), {})
    with pytest.raises(FleetError, match="share"):
        parse_fleet(_fleet(("ups-a", 1), ("ups-b", 1)), {})


@pytest.mark.parametrize(
    "raw", ["no es json", '{"devices": [{"id": "x"}]}', '{"devices": [{"id": "x", "kind": "PLC"}]}']
)
def test_a_malformed_file_is_a_fleet_error(raw: str) -> None:
    with pytest.raises(FleetError):
        parse_fleet(raw, {})
