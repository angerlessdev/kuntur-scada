from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from kuntur.adapters.api.app import create_api
from kuntur.bootstrap import Application, build_application
from kuntur.config import Settings
from tests.factories import barrier, camera, ups
from tests.fakes import FakeClock, ScriptedDriver, SingleDriverRegistry

OPERATOR_PASSWORD = "clave-del-operador"
VIEWER_PASSWORD = "clave-del-visitante"


@dataclass
class Api:
    client: TestClient
    application: Application
    driver: ScriptedDriver

    def token(self, username: str = "operador", password: str = OPERATOR_PASSWORD) -> str:
        response = self.client.post("/api/v1/auth/token", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        token: str = response.json()["access_token"]
        return token

    def headers(self, username: str = "operador") -> dict[str, str]:
        password = OPERATOR_PASSWORD if username == "operador" else VIEWER_PASSWORD
        return {"Authorization": f"Bearer {self.token(username, password)}"}


def settings() -> Settings:
    # Every field that matters is explicit, so a real KUNTUR_* variable on the machine cannot leak in
    return Settings(
        _env_file=None,
        database_url=None,
        token_secret=SecretStr("clave-de-firma-solo-para-las-pruebas-0123456789"),
        operator_password=SecretStr(OPERATOR_PASSWORD),
        viewer_password=SecretStr(VIEWER_PASSWORD),
        collector_enabled=False,
        expose_docs=True,
    )


@pytest.fixture
def api() -> Iterator[Api]:
    driver = ScriptedDriver()
    application = build_application(
        settings(),
        drivers=SingleDriverRegistry(driver),
        clock=FakeClock(),
        fleet=[ups(), barrier(), camera()],
    )
    with TestClient(create_api(application)) as client:
        yield Api(client, application, driver)
