"""`pie injecagent`: Study B of docs/preregistration.md."""

from __future__ import annotations

import gzip
import json
import random
from pathlib import Path
from typing import Any

import typer

from prompt_injection_eval.config import resolve_generation_limits
from prompt_injection_eval.injecagent import (
    CONDITIONS,
    InjecAgentError,
    Settings,
    load_cases,
    load_tools,
    run,
    smoke_summary,
    write_report,
)
from prompt_injection_eval.providers import MockProvider, provider_from_env
from prompt_injection_eval.providers.base import Provider
from prompt_injection_eval.results_io import load_results

injecagent_app = typer.Typer(help="InjecAgent placement study (Study B).", no_args_is_help=True)

_PROVIDER = typer.Option("openai", "--provider", help="openai (a vLLM server) or mock.")
_MODEL = typer.Option(..., "--model")
_OUTPUT = typer.Option(..., "--output-dir")
_THINK = typer.Option(None, "--think/--no-think")
_PROFILE = typer.Option("default", "--profile")
_EFFORT = typer.Option(None, "--reasoning-effort")
SMOKE_CASES = 3
SMOKE_SEED = 20261113


def _provider(name: str, model: str) -> Provider:
    if name == "mock":
        return MockProvider()
    if name != "openai":
        typer.echo("Use --provider openai (a vLLM server) or mock.", err=True)
        raise typer.Exit(code=1)
    try:
        remote = provider_from_env()
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    issues = remote.health(model)
    if issues:
        typer.echo(" ".join(issues), err=True)
        raise typer.Exit(code=1)
    return remote


def _settings(
    model: str, think: bool | None, profile: str, reasoning_effort: str | None
) -> Settings:
    tokens, timeout = resolve_generation_limits(profile=profile, max_tokens=None, timeout=None)
    return Settings(
        model=model,
        max_output_tokens=tokens,
        timeout_seconds=timeout,
        think=think,
        reasoning_effort=reasoning_effort,
    )


def _conditions(selection: str) -> list[str]:
    if selection == "all":
        return list(CONDITIONS)
    names = [name.strip() for name in selection.split(",")]
    unknown = [name for name in names if name not in CONDITIONS]
    if unknown:
        typer.echo(f"Unknown conditions: {', '.join(unknown)}", err=True)
        raise typer.Exit(code=1)
    return names


def _progress(done: int, total: int) -> None:
    if done % 500 == 0 or done == total:
        typer.echo(f"  {done}/{total}")


@injecagent_app.command("smoke")
def smoke_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    output_dir: Path = _OUTPUT,
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
) -> None:
    """Check that tool calls parse, on benign tool responses. Shows no attack outcome."""
    try:
        cases = load_cases()
        tools = load_tools()
    except InjecAgentError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    picked = random.Random(SMOKE_SEED).sample(cases, SMOKE_CASES)
    summary = run(
        cases=[case.benign() for case in picked],
        conditions=CONDITIONS,
        tools=tools,
        provider=_provider(provider, model),
        settings=_settings(model, think, profile, reasoning_effort),
        output_dir=output_dir,
        phase="smoke",
    )
    rows, _ = load_results(output_dir / "raw_results.jsonl")
    typer.echo(f"Smoke: wrote {summary.written}, backend errors {summary.backend_errors}.")
    typer.echo(json.dumps(smoke_summary(rows), sort_keys=True))


@injecagent_app.command("run")
def run_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    output_dir: Path = _OUTPUT,
    condition: str = typer.Option("all", "--condition", help="all, or a comma-separated list."),
    limit: int | None = typer.Option(None, "--limit", help="First N cases only, for checks."),
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
) -> None:
    """Run the InjecAgent cases under the placement conditions. Resumable."""
    try:
        cases = load_cases()
        tools = load_tools()
    except InjecAgentError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if limit is not None:
        cases = cases[:limit]
    names = _conditions(condition)
    typer.echo(f"InjecAgent: {len(cases)} cases x {len(names)} conditions.")
    summary = run(
        cases=cases,
        conditions=names,
        tools=tools,
        provider=_provider(provider, model),
        settings=_settings(model, think, profile, reasoning_effort),
        output_dir=output_dir,
        progress=_progress,
    )
    typer.echo(
        f"Skipped: {summary.skipped}. Wrote: {summary.written}. "
        f"Backend errors: {summary.backend_errors}."
    )


@injecagent_app.command("report")
def report_cmd(
    results_dir: Path = typer.Option(..., "--results-dir", help="Holds one directory per label."),
    label: list[str] = typer.Option(..., "--label", help="Model label. Repeat per model."),
    output_dir: Path = _OUTPUT,
) -> None:
    """Tables, the pre-registered B1 verdict, and parse diagnostics, from stored rows."""

    def rows(path: Path) -> list[dict[str, Any]]:
        plain, packed = path / "raw_results.jsonl", path / "raw_results.jsonl.gz"
        if not plain.exists() and packed.exists():
            with gzip.open(packed, "rt", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        return load_results(plain)[0]

    results = {name: rows(results_dir / name) for name in label}
    summary = write_report(results, output_dir)
    verdict = summary["verdict"]
    typer.echo(
        f"B1: higher in tool result on {verdict['higher_in_tool_result']}/{verdict['models']}, "
        f"significant on {verdict['significant']}: "
        f"{'replicates' if verdict['replicates'] else 'does not replicate'}."
    )
