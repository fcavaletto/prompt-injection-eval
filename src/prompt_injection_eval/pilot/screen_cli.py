"""`pie screen`: the OpenRouter feasibility screen. Paid calls need OPENROUTER_API_KEY and approval.

    pie screen plan --output-dir data/screen
    pie screen run --root results/screen --cap-usd 5 [--calibration-only]
    pie screen report --root results/screen --output-dir results/screen/report

One spending guard covers calibration and both models. On resume it starts from the cost
already recorded in the root's traces, so the cap is cumulative across invocations.
"""

from __future__ import annotations

import contextlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer

from prompt_injection_eval.pilot import PilotError

screen_app = typer.Typer(help="OpenRouter feasibility screen.", no_args_is_help=True)


def _dir(root: Path, model: str, calibration: bool = False) -> Path:
    return root / ("calibration" if calibration else "screen") / model.replace("/", "__")


def recorded_spend(root: Path) -> float:
    """Every attempt's reported cost already in the root's traces (both kinds)."""
    from prompt_injection_eval.pilot.runner import read_traces

    total = 0.0
    for path in root.glob("*/*/traces.jsonl"):
        for row in read_traces(path):
            turns = list(row.get("turns") or [])
            failed = (row.get("failed_turn") or {}).get("api") or {}
            attempts = [a for t in turns for a in ((t.get("api") or {}).get("attempts") or [])]
            attempts += failed.get("attempts") or []
            total += sum(float(a.get("cost_usd") or 0.0) for a in attempts)
    return total


def settings(model: str) -> Any:
    from prompt_injection_eval.pilot import episode, screen

    return episode.Settings(
        model=model,
        label=model.split("/")[-1],
        profile="request",
        study=screen.STAGE,
        max_rounds=screen.MAX_ROUNDS,
        score_executed_calls_only=True,
        timeout_seconds=120.0,
    )


@screen_app.command("plan")
def plan_cmd(output_dir: Path = typer.Option(Path("data/screen"), "--output-dir")) -> None:
    from prompt_injection_eval.pilot import screen

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "design.json").write_text(json.dumps(screen.design(), indent=1) + "\n")
    typer.echo(
        json.dumps(
            {k: screen.design()[k] for k in ("episodes", "calibration_episodes", "eligibility")}
        )
    )


def run(root: Path, cap_usd: float, calibration_only: bool, provider: Any = None) -> dict[str, Any]:
    from prompt_injection_eval.pilot import runner, screen
    from prompt_injection_eval.providers.openrouter import OpenRouterProvider, SpendGuard

    if cap_usd > screen.CAP_USD:
        raise PilotError(f"The approved cap is at most {screen.CAP_USD} USD.")
    already = recorded_spend(root)
    guard = SpendGuard(cap_usd - already, max_calls=1200)
    backend = provider or OpenRouterProvider(guard)
    out: dict[str, Any] = {"spent_before_usd": already}
    phases = [(True, screen.calibration())] + ([] if calibration_only else [(False, None)])
    for is_calibration, fixed in phases:
        for model in screen.MODELS:
            units = fixed if fixed is not None else screen.schedule(model)
            summary = runner.run_phase(
                "calibration" if is_calibration else "screen",
                backend,
                settings(model),
                _dir(root, model, is_calibration),
                units=units,
                fail_fast=is_calibration,
            )
            out[f"{'calibration' if is_calibration else 'screen'}/{model}"] = asdict(summary)
    out["guard"] = guard.state()
    return out


@screen_app.command("run")
def run_cmd(
    root: Path = typer.Option(..., "--root"),
    cap_usd: float = typer.Option(..., "--cap-usd"),
    calibration_only: bool = typer.Option(False, "--calibration-only"),
) -> None:
    """Calibration (2 episodes per model), then the screen. Spending is capped cumulatively."""
    try:
        out = run(root, cap_usd, calibration_only)
    except (PilotError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(out, indent=1, default=str))


def report(root: Path, output_dir: Path) -> dict[str, Any]:
    """Descriptive tables only: five cases cannot support inference."""
    from prompt_injection_eval.pilot import rescore, screen
    from prompt_injection_eval.pilot.analysis import latest
    from prompt_injection_eval.pilot.runner import read_traces

    result: dict[str, Any] = {
        "stage": screen.STAGE,
        "delivery_verification": "request-level only; provider rendering unobserved",
        "spend_usd": recorded_spend(root),
        "models": {},
    }
    for model in screen.MODELS:
        rows = list(latest(read_traces(_dir(root, model) / "traces.jsonl")).values())
        status = Counter(r["status"] for r in rows)
        cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
        malformed = 0
        for r in rows:
            malformed += r.get("totals", {}).get("invalid_argument_json", 0) + r.get(
                "totals", {}
            ).get("unknown_tool", 0)
            if r["status"] != "completed":
                continue
            fam = (
                "benign"
                if r["mode"] == "clean"
                else ("forged" if r["attack"] == screen.FORGED else "instruction")
            )
            value = r["utility"] if fam == "benign" else r["security"]
            cells[(fam, r["fmt"])].append(bool(value))
        rate = {f"{fam}|{fmt}": (sum(v), len(v)) for (fam, fmt), v in sorted(cells.items())}

        def diff(fam: str, cells: dict[tuple[str, str], list[bool]] = cells) -> float | None:
            t, j = cells.get((fam, "text")), cells.get((fam, "json@text"))
            return None if not t or not j else 100 * (sum(t) / len(t) - sum(j) / len(j))

        with contextlib.redirect_stdout(io.StringIO()):
            replays = [
                rescore.replay(r)
                for r in rows
                if r["mode"] == "attack" and r["status"] == "completed"
            ]
        result["models"][model] = {
            "status": dict(status),
            "malformed_tool_calls": malformed,
            "successes_over_completed": rate,
            "text_minus_json_pts": {f: diff(f) for f in ("instruction", "forged", "benign")},
            "family_x_representation_pts": (
                None
                if diff("instruction") is None or diff("forged") is None
                else diff("instruction") - diff("forged")  # type: ignore[operator]
            ),
            "replay_state_verified": f"{sum(x.verified for x in replays)}/{len(replays)}",
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(result, indent=1) + "\n")
    return result


@screen_app.command("report")
def report_cmd(
    root: Path = typer.Option(..., "--root"),
    output_dir: Path = typer.Option(..., "--output-dir"),
) -> None:
    typer.echo(json.dumps(report(root, output_dir), indent=1))
