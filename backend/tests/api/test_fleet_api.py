from typing import Any

from fastapi.testclient import TestClient

from kuntur.domain.alerts import AlertCode
from tests.api.conftest import Api
from tests.factories import failed, ok


def test_the_fleet_comes_with_health_and_replacement_dates(api: Api) -> None:
    response = api.client.get("/api/v1/devices", headers=api.headers("visitante"))
    assert response.status_code == 200
    fleet = response.json()
    assert [view["device"]["id"] for view in fleet] == ["barrera-01", "camara-01", "ups-01"]
    assert {view["health"] for view in fleet} == {"UNKNOWN"}
    assert all(view["life"]["replacement_date"] for view in fleet)


def test_a_reading_shows_in_the_device_and_its_history(api: Api) -> None:
    for i in range(3):
        api.application.record(ok(i, load_pct=40.0 + i))
    headers = api.headers("visitante")
    view = api.client.get("/api/v1/devices/ups-01", headers=headers).json()
    assert view["health"] == "OK"
    assert view["last_reading"]["metrics"] == {"load_pct": 42.0}
    history = api.client.get("/api/v1/devices/ups-01/readings", params={"limit": 2}, headers=headers).json()
    assert [reading["metrics"]["load_pct"] for reading in history] == [41.0, 42.0]


def test_a_time_without_zone_is_refused(api: Api) -> None:
    response = api.client.get(
        "/api/v1/devices/ups-01/readings", params={"since": "2026-01-15T08:00:00"}, headers=api.headers()
    )
    assert response.status_code == 422
    assert response.json()["type"] == "urn:kuntur:problem:validation"


def test_an_unknown_device_is_a_404_problem(api: Api) -> None:
    response = api.client.get("/api/v1/devices/no-existe", headers=api.headers())
    assert response.status_code == 404
    assert response.json()["instance"] == "/api/v1/devices/no-existe"


def test_a_confirmed_alert_is_listed_and_found_by_its_id(api: Api) -> None:
    for i in range(4):
        api.application.record(failed(i))
    headers = api.headers("visitante")
    [alert] = api.client.get("/api/v1/alerts", params={"state": "ACTIVE"}, headers=headers).json()
    assert alert["code"] == AlertCode.DEVICE_UNREACHABLE
    assert api.client.get(f"/api/v1/alerts/{alert['id']}", headers=headers).json() == alert
    assert api.client.get("/api/v1/devices/ups-01", headers=headers).json()["health"] == "DOWN"


def test_unexpected_errors_never_leak_their_text(api: Api) -> None:
    class Broken:
        def overview(self) -> Any:
            raise RuntimeError("cadena de conexión con la contraseña")

    headers = api.headers()
    api.application.queries = Broken()  # type: ignore[assignment]
    client = TestClient(api.client.app, raise_server_exceptions=False)
    response = client.get("/api/v1/devices", headers=headers)
    assert response.status_code == 500
    assert "contraseña" not in response.text
    assert response.json()["title"] == "Error interno"


def test_an_alert_comes_with_an_explanation(api: Api) -> None:
    for i in range(4):
        api.application.record(failed(i))
    headers = api.headers("visitante")
    [alert] = api.client.get("/api/v1/alerts", params={"state": "ACTIVE"}, headers=headers).json()
    explanation = api.client.get(f"/api/v1/alerts/{alert['id']}/explanation", headers=headers).json()
    assert explanation["source"] == "template"
    assert explanation["summary"].startswith("Sin comunicación con UPS sala eléctrica")
    assert explanation["checks"]
    assert api.client.get("/api/v1/alerts/no-existe/explanation", headers=headers).status_code == 404
