from tests.api.conftest import Api


def test_a_viewer_cannot_send_commands(api: Api) -> None:
    response = api.client.post(
        "/api/v1/devices/barrera-01/commands", json={"kind": "BARRIER_OPEN"}, headers=api.headers("visitante")
    )
    assert response.status_code == 403
    assert response.json()["type"] == "urn:kuntur:problem:forbidden"
    assert api.driver.executed == []


def test_an_operator_command_is_created_and_audited(api: Api) -> None:
    api.driver.command_results.append("Barrera abierta")
    headers = api.headers()
    created = api.client.post(
        "/api/v1/devices/barrera-01/commands", json={"kind": "BARRIER_OPEN"}, headers=headers
    )
    assert created.status_code == 201
    assert (created.json()["status"], created.json()["detail"]) == ("SUCCEEDED", "Barrera abierta")
    [audited] = api.client.get("/api/v1/commands", headers=api.headers("visitante")).json()
    assert audited == created.json()
    assert audited["requested_by"] == "operador"


def test_a_command_that_does_not_fit_the_device_is_a_conflict(api: Api) -> None:
    response = api.client.post(
        "/api/v1/devices/ups-01/commands", json={"kind": "BARRIER_OPEN"}, headers=api.headers()
    )
    assert response.status_code == 409
    assert response.json()["type"] == "urn:kuntur:problem:command-not-allowed"


def test_a_command_body_with_unknown_fields_is_refused(api: Api) -> None:
    response = api.client.post(
        "/api/v1/devices/ups-01/commands",
        json={"kind": "UPS_BATTERY_TEST", "forzar": True},
        headers=api.headers(),
    )
    assert response.status_code == 422
