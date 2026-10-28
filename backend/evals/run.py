"""Runs the explanation evals and writes a Markdown report.

    uv run python -m evals.run                         # the template: free and deterministic
    uv run python -m evals.run --narrator claude --yes # Claude: real calls, real cost (see the estimate)

The report shows what the operator would see: every narration goes through the same guard as the API.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from evals.cases import CASES, EvalCase
from evals.graders import Grade, grade
from kuntur.adapters.narrators.template import TemplateNarrator
from kuntur.application.explain import guard
from kuntur.application.ports import IncidentNarrator, Narration, NarratorUnavailable

INPUT_TOKENS_PER_CASE, OUTPUT_TOKENS_PER_CASE = 2_000, 600
"""Rough sizes for the cost estimate: the incident as JSON in, a short JSON answer (and thinking) out."""
PRICES_PER_MTOK = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00)}


@dataclass(frozen=True, slots=True)
class Result:
    case: EvalCase
    narration: Narration | None
    grades: list[Grade]
    seconds: float
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(g.passed for g in self.grades)


async def evaluate(narrator: IncidentNarrator, cases: tuple[EvalCase, ...] = CASES) -> list[Result]:
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            narration = guard(await narrator.explain(case.context), case.context)
        except NarratorUnavailable as exc:
            results.append(Result(case, None, [], time.perf_counter() - started, str(exc)))
            continue
        results.append(Result(case, narration, grade(case, narration), time.perf_counter() - started))
    return results


def report(results: list[Result], narrator: str) -> str:
    passed = sum(r.passed for r in results)
    checks = [g for r in results for g in r.grades]
    lines = [
        f"# Evaluación de explicaciones: `{narrator}`",
        "",
        f"Generado el {datetime.now(UTC):%Y-%m-%d %H:%M} UTC con `python -m evals.run`.",
        "",
        f"**{passed} de {len(results)} casos aprobados**, {sum(g.passed for g in checks)} de {len(checks)} "
        "verificaciones. Cada caso exige todas sus verificaciones.",
        "",
        "| Caso | Qué se espera | Resultado | Tiempo | Fuente |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        failed = [f"{g.grader} ({g.note})" for g in r.grades if not g.passed]
        outcome = "✅" if r.passed else "❌ " + (r.error or "; ".join(failed))
        source = r.narration.source if r.narration else "-"
        lines.append(f"| `{r.case.name}` | {r.case.goal} | {outcome} | {r.seconds:.2f} s | {source} |")
    lines += ["", "## Explicaciones", ""]
    for r in results:
        if r.narration is None:
            continue
        command = r.narration.suggested_command.value if r.narration.suggested_command else "ninguna"
        lines += [
            f"### `{r.case.name}`",
            "",
            f"> {r.narration.summary}",
            "",
            "Causas probables: " + "; ".join(r.narration.likely_causes) + ".",
            "",
            "Qué revisar: " + "; ".join(r.narration.checks) + ".",
            "",
            f"Orden sugerida: {command}.",
            "",
        ]
    return "\n".join(lines)


def _claude(model: str, effort: str) -> IncidentNarrator:
    import anthropic

    from kuntur.adapters.narrators.claude import ClaudeNarrator
    from kuntur.config import Settings

    settings = Settings()
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    client = anthropic.AsyncAnthropic(
        api_key=key, timeout=anthropic.Timeout(60.0, connect=5.0), max_retries=2
    )
    return ClaudeNarrator(client, model=model, effort=effort)  # type: ignore[arg-type]


def main() -> None:
    parser = argparse.ArgumentParser(prog="evals.run", description="Evalúa las explicaciones de alertas")
    parser.add_argument("--narrator", choices=["template", "claude"], default="template")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="low")
    parser.add_argument("--yes", action="store_true", help="confirma las llamadas pagadas a Claude")
    parser.add_argument("--out", type=Path, help="dónde escribir el informe en Markdown")
    args = parser.parse_args()

    narrator: IncidentNarrator = TemplateNarrator()
    name = "template"
    if args.narrator == "claude":
        price_in, price_out = PRICES_PER_MTOK.get(args.model, (4.00, 20.00))
        cost = len(CASES) * (INPUT_TOKENS_PER_CASE * price_in + OUTPUT_TOKENS_PER_CASE * price_out) / 1e6
        print(f"{len(CASES)} llamadas a {args.model} (esfuerzo {args.effort}), unos US$ {cost:.2f}")
        if not args.yes:
            raise SystemExit("Agrega --yes para ejecutarlas")
        narrator, name = _claude(args.model, args.effort), f"claude:{args.model}:{args.effort}"

    results = asyncio.run(evaluate(narrator))
    text = report(results, name)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    passed = sum(r.passed for r in results)
    print(f"{passed}/{len(results)} casos aprobados" + (f" -> {args.out}" if args.out else ""))
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
