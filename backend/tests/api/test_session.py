from kuntur.domain.security import Role, User
from tests.api.conftest import OPERATOR_PASSWORD, Api

PROBLEM = "application/problem+json"


def test_signing_in_gives_a_bearer_token_with_the_role(api: Api) -> None:
    response = api.client.post(
        "/api/v1/auth/token", json={"username": "Operador ", "password": OPERATOR_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["token_type"], body["username"], body["role"]) == ("bearer", "operador", "OPERATOR")
    me = api.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json() == {"username": "operador", "role": "OPERATOR"}


def test_wrong_credentials_do_not_say_which_part_was_wrong(api: Api) -> None:
    unknown = api.client.post("/api/v1/auth/token", json={"username": "nadie", "password": "x"})
    wrong = api.client.post("/api/v1/auth/token", json={"username": "operador", "password": "x"})
    for response in (unknown, wrong):
        assert response.status_code == 401
        assert response.headers["content-type"] == PROBLEM
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["detail"] == "Usuario o contraseña incorrectos"


def test_five_failures_lock_that_account_from_that_origin(api: Api) -> None:
    for _ in range(5):
        api.client.post("/api/v1/auth/token", json={"username": "operador", "password": "x"})
    locked = api.client.post(
        "/api/v1/auth/token", json={"username": "operador", "password": OPERATOR_PASSWORD}
    )
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    assert locked.json()["type"] == "urn:kuntur:problem:too-many-attempts"
    assert api.token("visitante", "clave-del-visitante")  # other accounts are untouched


def test_reads_need_a_valid_session(api: Api) -> None:
    assert api.client.get("/api/v1/devices").status_code == 401
    forged = api.client.get("/api/v1/devices", headers={"Authorization": "Bearer no.es.un-token"})
    assert forged.status_code == 401
    assert forged.json()["type"] == "urn:kuntur:problem:unauthenticated"


def test_deactivating_an_account_ends_its_sessions_at_once(api: Api) -> None:
    headers = api.headers()
    with api.application.uow_factory() as uow:
        user = uow.users.get("operador")
        assert user is not None
        uow.users.update(User(user.username, user.password_hash, Role.OPERATOR, active=False))
        uow.commit()
    assert api.client.get("/api/v1/auth/me", headers=headers).status_code == 401
