"""`pie screen`: the OpenRouter feasibility screen. Paid calls need OPENROUTER_API_KEY and approval.

    pie screen plan --output-dir data/screen
    pie screen run --root results/screen --cap-usd 5 [--calibration-only]
    pie screen ledger --root results/screen
    pie screen report --root results/screen --output-dir results/screen/report

Order enforced on every launch, including resumes:

1. Open the durable spend ledger (`<root>/spend-ledger.jsonl`), exclusively.
2. Preflight: the key must carry a service-side credit limit no larger than the cap.
3. Run any unfinished calibration episode, then verify calibration from the stored traces.
   If verification fails, no screen request is made.
4. Run the screen one model at a time, reconciling the key's usage with the ledger after each.
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
LEDGER = "spend-ledger.jsonl"
MAX_CALLS = 1200


class CalibrationFailed(PilotError):
    """Calibration did not verify; the screen must not start."""


def _dir(root: Path, model: str, calibration: bool = False) -> Path:
    return root / ("calibration" if calibration else "screen") / model.replace("/", "__")


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


def verify_calibration(root: Path) -> list[str]:
    """Every calibration episode completed, with request integrity, the pinned provider and
    model observed on every call, and a usable reported cost on every call."""
    from prompt_injection_eval.pilot import screen
    from prompt_injection_eval.pilot.analysis import latest
    from prompt_injection_eval.pilot.runner import read_traces
    from prompt_injection_eval.providers.openrouter import ENDPOINTS

    problems = []
    for model in screen.MODELS:
        e = ENDPOINTS[model]
        rows = latest(read_traces(_dir(root, model, True) / "traces.jsonl"))
        for unit in screen.calibration():
            row = rows.get(unit.key())
            where = f"{model} {unit.condition()}"
            if row is None or row["status"] != "completed":
                problems.append(
                    f"{where}: not completed ({None if row is None else row['status']})"
                )
                continue
            if row["delivery_defects"]:
                problems.append(f"{where}: request integrity {row['delivery_defects']}")
            for k, turn in enumerate(row["turns"]):
                api = turn.get("api") or {}
                if api.get("reported_provider") != e.provider_name:
                    problems.append(f"{where} call {k}: provider {api.get('reported_provider')!r}")
                if api.get("reported_model") not in (e.model, e.canonical):
                    problems.append(f"{where} call {k}: model {api.get('reported_model')!r}")
                cost = (api.get("usage") or {}).get("cost")
                if not isinstance(cost, int | float) or isinstance(cost, bool):
                    problems.append(f"{where} call {k}: no usable reported cost")
    return problems


def run(
    root: Path,
    cap_usd: float,
    calibration_only: bool,
    client: Any = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    from prompt_injection_eval.pilot import runner, screen
    from prompt_injection_eval.providers.openrouter import OpenRouterProvider
    from prompt_injection_eval.providers.spend_ledger import SpendLedger

    if cap_usd > screen.CAP_USD:
        raise PilotError(f"The approved cap is at most {screen.CAP_USD} USD.")
    out: dict[str, Any] = {}
    with SpendLedger(root / LEDGER, cap_usd, MAX_CALLS) as ledger:
        out["ledger_at_start"] = ledger.state()
        backend = OpenRouterProvider(ledger, api_key=api_key, client=client)
        problems = backend.preflight()
        if problems:
            raise PilotError("Preflight failed: " + "; ".join(problems))
        for model in screen.MODELS:
            summary = runner.run_phase(
                "calibration",
                backend,
                settings(model),
                _dir(root, model, True),
                units=screen.calibration(),
                fail_fast=True,
            )
            out[f"calibration/{model}"] = asdict(summary)
        problems = verify_calibration(root)
        out["calibration_problems"] = problems
        out["reconcile_after_calibration"] = backend.reconcile()
        if problems:
            raise CalibrationFailed(
                "Calibration failed; no screen request was made: " + "; ".join(problems)
            )
        if not out["reconcile_after_calibration"]["consistent"]:
            raise PilotError("Key usage exceeds the ledger after calibration; stopped.")
        if not calibration_only:
            for model in screen.MODELS:
                summary = runner.run_phase(
                    "screen",
                    backend,
                    settings(model),
                    _dir(root, model),
                    units=screen.schedule(model),
                )
                out[f"screen/{model}"] = asdict(summary)
                rec = backend.reconcile()
                out[f"reconcile/{model}"] = rec
                if not rec["consistent"]:
                    raise PilotError(f"Key usage exceeds the ledger after {model}; stopped.")
        out["ledger_at_end"] = ledger.state()
    return out


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


@screen_app.command("run")
def run_cmd(
    root: Path = typer.Option(..., "--root"),
    cap_usd: float = typer.Option(..., "--cap-usd"),
    calibration_only: bool = typer.Option(False, "--calibration-only"),
) -> None:
    """Preflight, calibration (verified), then the screen. Spending is capped by the ledger."""
    try:
        out = run(root, cap_usd, calibration_only)
    except (PilotError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(out, indent=1, default=str))


@screen_app.command("ledger")
def ledger_cmd(root: Path = typer.Option(..., "--root")) -> None:
    """Show the ledger's state (opens it exclusively, so not while a run is active)."""
    from prompt_injection_eval.providers.spend_ledger import SpendLedger

    with SpendLedger(root / LEDGER, 0.0, 0) as ledger:
        typer.echo(json.dumps(ledger.state(), indent=1))


def matched(
    cells: dict[tuple[str, str], dict[str, bool]], family: str, cases: list[str]
) -> dict[str, Any]:
    """Text minus JSON over cases completed in both representations; missing listed."""
    t, j = cells.get((family, "text"), {}), cells.get((family, "json@text"), {})
    both = [c for c in cases if c in t and c in j]
    return {
        "matched_cases": both,
        "missing_counterpart": sorted((set(t) ^ set(j)) & set(cases)),
        "missing_both": sorted(set(cases) - set(t) - set(j)),
        "text_successes": sum(t[c] for c in both),
        "json_successes": sum(j[c] for c in both),
        "text_minus_json_pts": None
        if not both
        else 100 * (sum(t[c] for c in both) - sum(j[c] for c in both)) / len(both),
    }


def report(root: Path, output_dir: Path) -> dict[str, Any]:
    """Descriptive tables on matched cases only: five cases cannot support inference."""
    from prompt_injection_eval.pilot import rescore, screen, stage1
    from prompt_injection_eval.pilot.analysis import latest
    from prompt_injection_eval.pilot.runner import read_traces
    from prompt_injection_eval.providers.spend_ledger import LedgerBusy, SpendLedger

    try:
        with SpendLedger(root / LEDGER, 0.0, 0) as ledger:
            spend: dict[str, Any] = ledger.state()
    except LedgerBusy:
        spend = {"note": "ledger in use"}
    accepted = list(stage1.ACCEPTED_PATHWAYS)
    every = [f"F{i}" for i in range(1, len(stage1.PATHWAYS) + 1)]
    result: dict[str, Any] = {
        "stage": screen.STAGE,
        "status": "descriptive development screen; five cases; no inference",
        "delivery_verification": "request-level only; provider rendering unobserved",
        "spend": spend,
        "subsets": {"accepted": accepted, "all_with_F4_F5_exploratory": every},
        "models": {},
    }
    for model in screen.MODELS:
        rows = list(latest(read_traces(_dir(root, model) / "traces.jsonl")).values())
        cells: dict[tuple[str, str], dict[str, bool]] = defaultdict(dict)
        malformed = 0
        for r in rows:
            totals = r.get("totals") or {}
            malformed += totals.get("invalid_argument_json", 0) + totals.get("unknown_tool", 0)
            if r["status"] != "completed":
                continue
            fam = (
                "benign"
                if r["mode"] == "clean"
                else ("forged" if r["attack"] == screen.FORGED else "instruction")
            )
            pathway = next(
                p for p in stage1.PATHWAYS if (p.suite, p.user_task) == (r["suite"], r["user_task"])
            )
            case = stage1.pathway_id(pathway.suite, pathway.user_task, pathway.goal)
            cells[(fam, r["fmt"])][case] = bool(r["utility"] if fam == "benign" else r["security"])
        per_family = {
            fam: {"accepted": matched(cells, fam, accepted), "all": matched(cells, fam, every)}
            for fam in ("instruction", "forged", "benign")
        }

        def interaction(
            subset: str, cells: dict = cells, per_family: dict = per_family
        ) -> float | None:
            common = sorted(
                set(per_family["instruction"][subset]["matched_cases"])
                & set(per_family["forged"][subset]["matched_cases"])
            )
            if not common:
                return None
            ti, ji = cells[("instruction", "text")], cells[("instruction", "json@text")]
            tf, jf = cells[("forged", "text")], cells[("forged", "json@text")]
            return 100 * sum((ti[c] - ji[c]) - (tf[c] - jf[c]) for c in common) / len(common)

        with contextlib.redirect_stdout(io.StringIO()):
            replays = [
                rescore.replay(r)
                for r in rows
                if r["mode"] == "attack" and r["status"] == "completed"
            ]
        result["models"][model] = {
            "status": dict(Counter(r["status"] for r in rows)),
            "malformed_tool_calls": malformed,
            "case_level": {
                f"{fam}|{fmt}": dict(sorted(v.items())) for (fam, fmt), v in sorted(cells.items())
            },
            "matched": per_family,
            "instruction_minus_forged_format_effect_pts": {
                "accepted": interaction("accepted"),
                "all_exploratory": interaction("all"),
            },
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


def screen_models() -> tuple[str, ...]:
    from prompt_injection_eval.pilot import screen

    return screen.MODELS
