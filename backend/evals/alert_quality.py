"""How good are the alerts? Plays incidents with known ground truth on the running platform and checks
what the alert rules did: raised the right alert, raised nothing when nothing should be raised, and how
fast. Needs the whole platform up (docker compose up) and a viewer account.

    uv run python -m evals.alert_quality --out ../docs/calidad-de-alertas.md

It is a smoke test with ground truth, not a statistic: each scenario runs once. ``--judge-only``
rebuilds the report from the last run without replaying it.
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

ROUNDS: tuple[tuple[tuple[str, str], ...], ...] = (
    (
        ("ups-norte-01", "corte-de-energia"),
        ("ups-sur-01", "bateria-caliente"),
        ("barrera-norte-01", "equipo-caido"),
        ("barrera-norte-02", "perdida-aislada"),
        ("barrera-sur-01", "red-inestable"),
        ("camara-norte-01", "reloj-desfasado"),
        ("camara-sur-01", "sin-respuesta"),
    ),
    (
        ("ups-norte-01", "enlace-lento"),
        ("ups-sur-01", "sensor-sin-dato"),
        ("barrera-norte-01", "impacto"),
        ("barrera-norte-02", "sin-respuesta"),
        ("barrera-sur-01", "perdida-aislada"),
        ("camara-norte-01", "equipo-caido"),
        ("camara-sur-01", "perdida-aislada"),
    ),
)
GRACE = timedelta(seconds=60)
"""How long after an incident ends an alert still counts as caused by it (confirmation takes readings)."""
RECOVERY_S = 120


@dataclass(frozen=True, slots=True)
class Outcome:
    device_id: str
    scenario: str
    expected: str | None
    raised: tuple[str, ...]
    spans: tuple[tuple[float, float | None], ...]
    """Each alert with the expected code: seconds from the incident start, and how long it lasted
    (None while it is still active)."""

    @property
    def latency_s(self) -> float | None:
        return self.spans[0][0] if self.spans else None

    @property
    def verdict(self) -> str:
        if self.expected is None:
            return "VN" if not self.raised else "FP"
        return "VP" if self.expected in self.raised else "FN"

    @property
    def false_alarms(self) -> int:
        return sum(1 for code in self.raised if code != self.expected)


def _time(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(UTC)


class Platform:
    def __init__(self, api: str, simulator: str, username: str, password: str) -> None:
        self.api, self.simulator = api.rstrip("/"), simulator.rstrip("/")
        # Polls every 5 s, the same time uvicorn keeps an idle connection: a reused connection can be
        # closed by the server right as the request goes out. A fresh connection per request avoids it.
        self.http = httpx.Client(timeout=20, limits=httpx.Limits(max_keepalive_connections=0))
        token = self.http.post(
            f"{self.api}/api/v1/auth/token", json={"username": username, "password": password}
        )
        token.raise_for_status()
        self.headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

    def active_alerts(self) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"state": "ACTIVE", "limit": 100}
        return list(self.http.get(f"{self.api}/api/v1/alerts", params=params, headers=self.headers).json())

    def alerts(self, device_id: str) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"device_id": device_id, "limit": 200}
        return list(self.http.get(f"{self.api}/api/v1/alerts", params=params, headers=self.headers).json())

    def play(self, device_id: str, scenario: str) -> dict[str, Any]:
        response = self.http.post(f"{self.simulator}/sim/scenarios/{scenario}", json={"device_id": device_id})
        response.raise_for_status()
        return dict(response.json())

    def incidents(self) -> list[dict[str, Any]]:
        return list(self.http.get(f"{self.simulator}/sim/incidents").json())


def judge(platform: Platform, incident: dict[str, Any]) -> Outcome:
    start = _time(incident["started_at"])
    end = _time(incident["ended_at"]) + GRACE
    raised = [a for a in platform.alerts(incident["device_id"]) if start <= _time(a["raised_at"]) <= end]
    raised.sort(key=lambda a: a["raised_at"])
    expected = incident["expected_alert"]
    spans = tuple(
        (
            (_time(a["raised_at"]) - start).total_seconds(),
            (_time(a["resolved_at"]) - _time(a["raised_at"])).total_seconds() if a["resolved_at"] else None,
        )
        for a in raised
        if a["code"] == expected
    )
    codes = tuple(a["code"] for a in raised)
    return Outcome(incident["device_id"], incident["scenario"], expected, codes, spans)


def last_run(platform: Platform) -> list[dict[str, Any]]:
    """The incidents of the last complete run, in the order they were played. Judging them again
    rebuilds the report without replaying anything, e.g. after changing how it reads."""
    played = [pair for round_ in ROUNDS for pair in round_]
    incidents = platform.incidents()[-len(played) :]
    if [(i["device_id"], i["scenario"]) for i in incidents] != played:
        raise SystemExit("The simulator's last incidents are not a complete run: play it again")
    return incidents


def wait_quiet(platform: Platform, limit_s: float = 600) -> None:
    """Starts from a calm fleet: an alert left over from before would blur the picture."""
    deadline = time.monotonic() + limit_s
    while platform.active_alerts() and time.monotonic() < deadline:
        time.sleep(5)


def run(platform: Platform) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for number, round_ in enumerate(ROUNDS, start=1):
        wait_quiet(platform)
        print(f"Ronda {number}: {len(round_)} incidentes a la vez")
        ids = [platform.play(device_id, scenario) for device_id, scenario in round_]
        while True:
            current = {(i["device_id"], i["scenario"], i["started_at"]): i for i in platform.incidents()}
            mine = [current[(i["device_id"], i["scenario"], i["started_at"])] for i in ids]
            if all(i["ended_at"] for i in mine):
                break
            time.sleep(5)
        time.sleep(GRACE.total_seconds())
        outcomes += [judge(platform, incident) for incident in mine]
        time.sleep(RECOVERY_S)
    return outcomes


def report(outcomes: list[Outcome]) -> str:
    tp = sum(o.verdict == "VP" for o in outcomes)
    fn = sum(o.verdict == "FN" for o in outcomes)
    tn = sum(o.verdict == "VN" for o in outcomes)
    false_alarms = sum(o.false_alarms for o in outcomes)
    precision = tp / (tp + false_alarms) if tp + false_alarms else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    latencies = sorted(o.latency_s for o in outcomes if o.latency_s is not None)
    quiet = sum(o.expected is None for o in outcomes)
    lines = [
        "# Calidad de las alertas",
        "",
        f"Medido el {datetime.now(UTC):%Y-%m-%d} con `python -m evals.alert_quality` sobre la",
        "plataforma completa (docker compose): el simulador reproduce cada incidente y registra la",
        "verdad de terreno; el script compara con las alertas que levantó Kuntur. Cada escenario",
        "corrió una vez: es una prueba con verdad de terreno, no una estadística.",
        "",
        f"- **Precisión: {precision * 100:.0f} %** ({tp} alertas correctas, {false_alarms} falsas alarmas)",
        f"- **Recall: {recall * 100:.0f} %** ({tp} de {tp + fn} incidentes que debían alertar)",
        f"- **Silencio correcto: {tn} de {quiet}** incidentes que no debían alertar",
    ]
    if latencies:
        middle = latencies[len(latencies) // 2]
        lines.append(
            f"- **Detección:** mediana {middle:.0f} s, peor caso {latencies[-1]:.0f} s (lecturas cada 5 s)"
        )
    lines += [
        "",
        "| Equipo | Incidente | Alerta esperada | Alertas levantadas | Resultado | Detección |",
        "|---|---|---|---|---|---|",
    ]
    names = {"VP": "✅ alertó", "VN": "✅ no alertó", "FP": "❌ falsa alarma", "FN": "❌ no alertó"}
    for o in outcomes:
        raised = ", ".join(o.raised) or "ninguna"
        latency = f"{o.latency_s:.0f} s" if o.latency_s is not None else "-"
        expected = o.expected or "ninguna"
        lines.append(
            f"| `{o.device_id}` | `{o.scenario}` | {expected} | {raised} | {names[o.verdict]} | {latency} |"
        )
    flapping = [o for o in outcomes if o.scenario == "red-inestable"]
    if flapping:
        o = flapping[0]
        times = "vez" if len(o.spans) == 1 else "veces"
        spans = "; ".join(
            f"a los {at:.0f} s, por {length:.0f} s" if length is not None else f"a los {at:.0f} s, aún activa"
            for at, length in o.spans
        )
        lines += [
            "",
            "**Red inestable:** la conexión se cortó 3 veces en 2 minutos (20 s arriba, 20 s cortada) y la",
            f"alerta se levantó {len(o.spans)} {times}: {spans}. Una alerta dura al menos 30 s y no vuelve",
            "a levantarse antes de 30 s de resuelta, así que sigue activa entre cortes cercanos en vez de",
            "encenderse y apagarse con cada uno.",
        ]
    lines += [
        "",
        "Los incidentes que no deben alertar importan tanto como los otros: una pérdida aislada de",
        "4 s, un enlace lento que sigue dentro del tiempo de espera y un sensor que deja de dar valor",
        "(lectura parcial: el equipo se ve en amarillo, sin alarma).",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="evals.alert_quality", description=__doc__)
    parser.add_argument("--api", default=os.environ.get("KUNTUR_API", "http://127.0.0.1:8000"))
    parser.add_argument("--simulator", default=os.environ.get("KUNTUR_SIM_URL", "http://127.0.0.1:15000"))
    parser.add_argument("--username", default="visitante")
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--judge-only", action="store_true", help="judge the last complete run again instead of replaying it"
    )
    args = parser.parse_args()
    password = os.environ.get("KUNTUR_VIEWER_PASSWORD")
    if not password:
        raise SystemExit("Export KUNTUR_VIEWER_PASSWORD (the value docker compose uses)")
    platform = Platform(args.api, args.simulator, args.username, password)
    outcomes = [judge(platform, i) for i in last_run(platform)] if args.judge_only else run(platform)
    text = report(outcomes)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)


if __name__ == "__main__":
    main()
