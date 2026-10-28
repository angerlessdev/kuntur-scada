import hashlib
import re
from datetime import UTC, datetime, timedelta

import httpx

from kuntur_sim.camera_http import create_camera_app
from kuntur_sim.digest import DigestResult, DigestVerifier
from kuntur_sim.models import CameraModel

NOW = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)
AUTH = httpx.DigestAuth("admin", "clave-de-prueba")


def _client(camera: CameraModel) -> httpx.AsyncClient:
    verifier = DigestVerifier("kuntur-camera", "admin", "clave-de-prueba")
    app = create_camera_app({"cam-1": camera}, verifier, lambda: NOW)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://camera")


def _nonce(challenge: str) -> str:
    found = re.search(r'nonce="([^"]+)"', challenge)
    assert found is not None
    return found[1]


def _authorization(nonce: str, uri: str, password: str = "p", method: str = "GET") -> str:
    def h(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    response = h(f"{h(f'u:r:{password}')}:{nonce}:00000001:abc:auth:{h(f'{method}:{uri}')}")
    return (
        f'Digest username="u", realm="r", nonce="{nonce}", uri="{uri}", response="{response}", '
        'qop=auth, nc=00000001, cnonce="abc", algorithm=SHA-256'
    )


async def test_the_right_credentials_read_the_status() -> None:
    async with _client(CameraModel(clock_offset_s=12)) as client:
        response = await client.get("/cameras/cam-1/status", auth=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["device_time"]) == NOW + timedelta(seconds=12)
    assert body["recording"] is True


async def test_a_wrong_password_gets_a_sha256_challenge() -> None:
    async with _client(CameraModel()) as client:
        response = await client.get("/cameras/cam-1/status", auth=httpx.DigestAuth("admin", "otra"))
    assert response.status_code == 401
    assert "algorithm=SHA-256" in response.headers["www-authenticate"]


async def test_no_credentials_get_a_challenge() -> None:
    async with _client(CameraModel()) as client:
        response = await client.get("/cameras/cam-1/status")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Digest ")


async def test_a_rebooting_camera_is_unavailable_and_refuses_a_second_reboot() -> None:
    async with _client(CameraModel()) as client:
        assert (await client.post("/cameras/cam-1/reboot", auth=AUTH)).status_code == 202
        assert (await client.post("/cameras/cam-1/reboot", auth=AUTH)).status_code == 409
        assert (await client.get("/cameras/cam-1/status", auth=AUTH)).status_code == 503
        assert (await client.get("/cameras/otra/status", auth=AUTH)).status_code == 404


def test_an_expired_nonce_is_stale_not_denied() -> None:
    now = [1_000.0]
    verifier = DigestVerifier("r", "u", "p", nonce_ttl_s=60, clock=lambda: now[0])
    header = _authorization(_nonce(verifier.challenge()), "/x")
    assert verifier.verify(header, "GET", "/x") is DigestResult.OK
    now[0] += 61
    assert verifier.verify(header, "GET", "/x") is DigestResult.STALE


def test_a_nonce_signed_by_another_server_is_denied() -> None:
    header = _authorization(_nonce(DigestVerifier("r", "u", "p").challenge()), "/x")
    assert DigestVerifier("r", "u", "p").verify(header, "GET", "/x") is DigestResult.DENIED


def test_the_digest_is_bound_to_the_uri_and_the_method() -> None:
    verifier = DigestVerifier("r", "u", "p")
    header = _authorization(_nonce(verifier.challenge()), "/x")
    assert verifier.verify(header, "GET", "/y") is DigestResult.DENIED
    assert verifier.verify(header, "POST", "/x") is DigestResult.DENIED
    assert verifier.verify(_authorization(_nonce(verifier.challenge()), "/x", password="q"), "GET", "/x") is (
        DigestResult.DENIED
    )
