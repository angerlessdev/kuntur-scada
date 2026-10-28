import pytest
from starlette.websockets import WebSocketDisconnect

from kuntur.adapters.api.middleware import SECURITY_HEADERS
from tests.api.conftest import Api
from tests.factories import failed, ok


def test_the_live_channel_greets_and_then_streams_what_happens(api: Api) -> None:
    token = api.token("visitante", "clave-del-visitante")
    with api.client.websocket_connect("/api/v1/live") as live:
        live.send_json({"token": token})
        assert live.receive_json() == {"type": "hello", "username": "visitante", "role": "VIEWER"}
        api.application.record(ok(0))
        message = live.receive_json()
        assert (message["type"], message["device_id"], message["health"]) == ("reading", "ups-01", "OK")
        for i in range(1, 5):
            api.application.record(failed(i))
        kinds = [live.receive_json()["type"] for _ in range(5)]
        assert kinds == ["reading", "reading", "reading", "reading", "alert_raised"]


def test_the_live_channel_closes_without_a_valid_session(api: Api) -> None:
    with api.client.websocket_connect("/api/v1/live") as live:
        live.send_json({"token": "inventado"})
        with pytest.raises(WebSocketDisconnect) as closed:
            live.receive_json()
    assert closed.value.code == 4401


def test_every_answer_carries_the_security_headers(api: Api) -> None:
    for response in (api.client.get("/healthz"), api.client.get("/api/v1/devices")):
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value


def test_a_body_over_the_limit_is_refused_before_it_is_read(api: Api) -> None:
    response = api.client.post(
        "/api/v1/auth/token",
        content=b"{" + b" " * 70_000 + b"}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"


def test_probes_and_metrics(api: Api) -> None:
    api.application.record(ok(0))
    assert api.client.get("/healthz").json() == {"status": "ok"}
    assert api.client.get("/readyz").json() == {"status": "ready"}
    metrics = api.client.get("/metrics").text
    assert 'kuntur_readings_total{kind="UPS",status="OK"} 1.0' in metrics
    assert "ups-01" not in metrics  # device ids never become labels


def test_an_unknown_route_is_a_problem_too(api: Api) -> None:
    response = api.client.get("/api/v1/nada")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
