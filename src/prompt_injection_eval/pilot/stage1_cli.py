"""`pie stage1`: the Stage 1 diagnostic (Amendment 4). Nothing runs without a server you start.

    pie stage1 plan --output-dir data/stage1
    pie stage1 run --batch 0 --provider openai --model ibm-granite/granite-4.0-h-small \
        --output-dir results/stage1/batch-0 --deadline-minutes 75
    pie stage1 report --batch-dir results/stage1/batch-0 --batch-dir results/stage1/batch-1 \
        --output-dir results/stage1/report
"""

from __future__ import annotations

import contextlib
import io
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer

from prompt_injection_eval.pilot import PilotError

stage1_app = typer.Typer(help="Stage 1 diagnostic (Amendment 4).", no_args_is_help=True)


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def settings(model: str, label: str, provider: str) -> Any:
    from prompt_injection_eval.pilot import episode, stage1

    return episode.Settings(
        model=model,
        label=label,
        profile="scripted" if provider == "scripted" else stage1.PROFILE,
        study=stage1.STAGE,
        score_executed_calls_only=True,
    )


@stage1_app.command("plan")
def plan_cmd(output_dir: Path = typer.Option(Path("data/stage1"), "--output-dir")) -> None:
    """Write the frozen episode manifest (one line per unit, in batch run order)."""
    from prompt_injection_eval.pilot import stage1

    output_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for batch in (0, 1):
        for position, unit in enumerate(stage1.schedule(batch)):
            lines.append(
                {
                    "batch": batch,
                    "position": position,
                    "family": stage1.family(unit),
                    **asdict(unit),
                }
            )
    (output_dir / "manifest.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    (output_dir / "design.json").write_text(
        json.dumps(stage1.design(), indent=1, ensure_ascii=False) + "\n"
    )
    typer.echo(json.dumps(stage1.counts()))


@stage1_app.command("run")
def run_cmd(
    batch: int = typer.Option(..., "--batch", min=0, max=1),
    provider: str = typer.Option(
        "openai", "--provider", help="openai (a vLLM server) or scripted."
    ),
    model: str = typer.Option("ibm-granite/granite-4.0-h-small", "--model"),
    label: str = typer.Option("granite-4.0-h-small", "--label"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    deadline_minutes: float | None = typer.Option(None, "--deadline-minutes"),
    policy: str = typer.Option("benign", "--scripted-policy"),
) -> None:
    """Run one batch in its frozen order. Resumable; reruns only units with no final trace."""
    from prompt_injection_eval.pilot import runner, stage1
    from prompt_injection_eval.pilot.cli import _provider

    if provider == "openai" and model != stage1.MODEL:
        raise _fail(f"Stage 1 is frozen to {stage1.MODEL}.")
    backend = _provider(provider, model, policy)
    try:
        summary = runner.run_phase(
            f"stage1-batch-{batch}",
            backend,
            settings(model, label, provider),
            output_dir,
            deadline_minutes=deadline_minutes,
            units=stage1.schedule(batch),
            fail_fast=False,
        )
    except PilotError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(json.dumps(asdict(summary), default=str))
    if summary.stopped_by_deadline:
        raise typer.Exit(code=3)


MANIFEST = Path("data/stage1/manifest.jsonl")


def report(batch_dirs: list[Path], output_dir: Path, manifest: Path = MANIFEST) -> dict[str, Any]:
    """Every Amendment 4 quantity from stored traces, against the frozen manifest. No model call."""
    from prompt_injection_eval.pilot import rescore, stage1
    from prompt_injection_eval.pilot import stage1_analysis as sa
    from prompt_injection_eval.pilot.analysis import latest
    from prompt_injection_eval.pilot.runner import read_traces

    rows = [r for d in batch_dirs for r in read_traces(d / "traces.jsonl")]
    final = list(latest(rows).values())
    planned = sa.load_manifest(manifest)
    instruction = [r for r in rows if r.get("attack") in stage1.INSTRUCTION_TWINS]
    estimates = sa.contrasts(instruction, planned=sa.planned_pairs(planned))
    ctrl = sa.controls(rows, planned)
    batch = sa.batches(instruction)
    forged = sa.forged(rows)
    accounting = sa.accounting(planned, rows)
    invalid = sum(r["status"] in ("invalid_delivery", "unverified_delivery") for r in final)
    scored_clean = all(not r["delivery_defects"] for r in final if r["status"] == "completed")
    delivery_ok = scored_clean and invalid <= sa.MISSING_LIMIT * len(planned)
    with contextlib.redirect_stdout(io.StringIO()):  # some AgentDojo tools print
        rescored = [rescore.replay(r) for r in final if r["mode"] == "attack"]
    out: dict[str, Any] = {
        "stage": stage1.STAGE,
        "batch_dirs": [str(d) for d in batch_dirs],
        "accounting": accounting,
        "delivery": {
            "invalid_or_unverified_rows": invalid,
            "every_scored_request_passed_contract_check": scored_clean,
            "verification": "contract check on the prompt the server returned (template profile)",
        },
        "contrasts": [e.row() for e in estimates],
        "controls": ctrl,
        "security_utility": sa.security_utility(rows, ctrl),
        "batches": batch,
        "forged": forged,
        "termination": sa.termination(rows),
        "exploratory_per_round": sa.per_round(rescored),
        "rescoring": {
            "attack_episodes": len(rescored),
            "state_verified": sum(r.verified for r in rescored),
            "archived_disagrees": sum(r.archived_agrees is False for r in rescored),
        },
        "progression": sa.progression(estimates, ctrl, batch, forged, delivery_ok),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    lines = [
        "# Stage 1 report",
        "",
        "| Contrast | Tier | Pairs complete in both batches | Estimate | 95% interval | Missing-outcome bounds | Threshold |",
        "|---|---|---:|---:|---|---|---:|",
    ]
    for e in out["contrasts"]:
        iv = e["interval_pts"]
        lines.append(
            f"| {e['name']} | {e['tier']} | {e['cases_complete_in_all_batches']}/{e['planned_cases']} | {e['estimate_pts']} | "
            f"{'' if iv is None else f'{iv[0]} to {iv[1]}'} | "
            f"{e['missing_outcome_bounds_pts'][0]} to {e['missing_outcome_bounds_pts'][1]} | {e['threshold_pts']} |"
        )
    lines += ["", "## Progression (Amendment 4)", ""]
    lines += [
        f"- {k}: **{'pass' if v else 'fail'}**" for k, v in out["progression"]["rules"].items()
    ]
    lines += ["", out["progression"]["note"]]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")
    return out


@stage1_app.command("report")
def report_cmd(
    batch_dir: list[Path] = typer.Option(..., "--batch-dir"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    manifest: Path = typer.Option(MANIFEST, "--manifest"),
) -> None:
    """Write report.json and report.md for the given batch directories."""
    out = report(batch_dir, output_dir, manifest)
    typer.echo(json.dumps(out["progression"], indent=1))
