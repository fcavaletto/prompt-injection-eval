"""Command-line interface for the prompt-injection evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from prompt_injection_eval import __version__
from prompt_injection_eval.adaptive.cli import adaptive_app
from prompt_injection_eval.config import (
    RunConfig,
    default_model,
    env_base_url,
    env_keep_alive,
    env_timeout_override,
    resolve_generation_limits,
)
from prompt_injection_eval.constants import DEFAULT_MODEL
from prompt_injection_eval.dataset import (
    DatasetError,
    filter_cases,
    format_validation_report,
    validate_dataset,
)
from prompt_injection_eval.doctor import run_doctor
from prompt_injection_eval.injecagent_cli import injecagent_app
from prompt_injection_eval.pilot.cli import pilot_app
from prompt_injection_eval.privacy import sanitize_text
from prompt_injection_eval.providers.mlx import MlxProvider
from prompt_injection_eval.providers.mock import MockProvider
from prompt_injection_eval.providers.ollama import OllamaProvider
from prompt_injection_eval.reporting import (
    analyze_results,
    compare_results,
    write_variability_report,
)
from prompt_injection_eval.results_io import load_results
from prompt_injection_eval.review import (
    ReviewError,
    attach_human_labels,
    load_human_reviews,
    write_review_csv,
)
from prompt_injection_eval.runner import RunnerError, run_evaluation
from prompt_injection_eval.secondary import CaseLookupError, annotate, load_cases_for_rows
from prompt_injection_eval.stats_report import write_stats_report

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "Evaluate indirect prompt injection in a local open-weight model. "
        "This is a research harness, not a production security guarantee."
    ),
)
app.add_typer(adaptive_app, name="adaptive")
app.add_typer(injecagent_app, name="injecagent")
app.add_typer(pilot_app, name="pilot")


@app.command("version")
def version_cmd() -> None:
    """Print the package version."""
    typer.echo(f"prompt-injection-eval {__version__}")


@app.command("validate-data")
def validate_data_cmd(
    dataset: Path = typer.Option(Path("data/cases.jsonl"), "--dataset", help="JSONL dataset path."),
) -> None:
    """Validate a JSONL dataset and print counts computed from the file."""
    _cases, result = validate_dataset(dataset)
    typer.echo(format_validation_report(result))
    if not result.valid:
        raise typer.Exit(code=1)


@app.command("list-cases")
def list_cases_cmd(
    dataset: Path = typer.Option(Path("data/cases.jsonl"), "--dataset"),
    category: str | None = typer.Option(None, "--category"),
    difficulty: str | None = typer.Option(None, "--difficulty"),
) -> None:
    """List case IDs after schema validation."""
    cases, result = validate_dataset(dataset)
    if not result.valid:
        typer.echo(format_validation_report(result), err=True)
        raise typer.Exit(code=1)
    try:
        selected = filter_cases(cases, category=category, difficulty=difficulty)
    except DatasetError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("id\tcategory\tdifficulty\tattack\ttask_scorer\tattack_scorer")
    for case in selected:
        attack = "none" if case.attack_goal is None else case.attack_goal.type
        typer.echo(
            f"{case.id}\t{case.category.value}\t{case.difficulty.value}\t"
            f"{str(case.is_attack).lower()}\t{case.expected_task.type}\t{attack}"
        )


@app.command("doctor")
def doctor_cmd(
    provider: str = typer.Option("mock", "--provider", help="mock or ollama."),
    model: str = typer.Option(DEFAULT_MODEL, "--model"),
    dataset: Path = typer.Option(Path("data/cases.jsonl"), "--dataset"),
    output_dir: Path = typer.Option(Path("results"), "--output-dir"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="PIE_OLLAMA_BASE_URL"),
) -> None:
    """Check Python, data, output paths, and the selected provider."""
    ok, messages = run_doctor(
        provider=provider,
        model=model,
        dataset=dataset,
        output_dir=output_dir,
        base_url=env_base_url(base_url),
    )
    for message in messages:
        typer.echo(message)
    if not ok:
        raise typer.Exit(code=1)


@app.command("run")
def run_cmd(
    provider: str = typer.Option(..., "--provider", help="ollama, mlx, or mock."),
    model: str | None = typer.Option(None, "--model", envvar="PIE_MODEL"),
    dataset: Path = typer.Option(..., "--dataset"),
    condition: str = typer.Option(
        ...,
        "--condition",
        help="baseline, defended, spotlight, both (baseline+defended), or all.",
    ),
    output_dir: Path = typer.Option(..., "--output-dir"),
    limit: int | None = typer.Option(None, "--limit"),
    case_id: list[str] | None = typer.Option(None, "--case-id"),
    category: str | None = typer.Option(None, "--category"),
    difficulty: str | None = typer.Option(None, "--difficulty"),
    seed: int | None = typer.Option(None, "--seed"),
    temperature: float = typer.Option(0.0, "--temperature"),
    max_tokens: int | None = typer.Option(
        None, "--max-tokens", help="Default 256, or 4096 with --profile reasoning."
    ),
    timeout: float | None = typer.Option(
        None, "--timeout", help="Seconds. Default 120, or 900 with --profile reasoning."
    ),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    verbose: bool = typer.Option(False, "--verbose"),
    keep_alive: str | None = typer.Option(None, "--keep-alive", envvar="PIE_KEEP_ALIVE"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="PIE_OLLAMA_BASE_URL"),
    task_mode: str = typer.Option("strict", "--task-mode", help="strict or lenient task scoring."),
    concurrency: int = typer.Option(1, "--concurrency"),
    think: bool | None = typer.Option(
        None,
        "--think/--no-think",
        help="Forward Ollama's think flag. Omit to keep the model's default.",
    ),
    profile: str = typer.Option(
        "default",
        "--profile",
        help="'reasoning' raises max tokens and timeout for models that emit chain-of-thought.",
    ),
    num_ctx: int | None = typer.Option(
        None,
        "--num-ctx",
        help="Context window forwarded to Ollama. Omit to keep the runtime default.",
    ),
    reasoning_effort: str | None = typer.Option(
        None,
        "--reasoning-effort",
        help="low, medium, or high. Read by the gpt-oss chat template (mlx provider).",
    ),
) -> None:
    """Run the evaluation sequentially and append JSONL results as each unit finishes."""
    if condition not in {"baseline", "defended", "spotlight", "both", "all"}:
        typer.echo("Condition must be baseline, defended, spotlight, both, or all.", err=True)
        raise typer.Exit(code=1)
    if provider not in {"mock", "ollama", "mlx"}:
        typer.echo("Provider must be mock, ollama, or mlx.", err=True)
        raise typer.Exit(code=1)
    if reasoning_effort not in {None, "low", "medium", "high"}:
        typer.echo("Reasoning effort must be low, medium, or high.", err=True)
        raise typer.Exit(code=1)
    if provider == "mlx" and not _mlx_available():
        typer.echo(
            "The mlx provider needs mlx and mlx-lm. Install them with "
            '`pip install -e ".[mlx]"` on Apple Silicon.',
            err=True,
        )
        raise typer.Exit(code=1)
    if task_mode not in {"strict", "lenient"}:
        typer.echo("Task mode must be strict or lenient.", err=True)
        raise typer.Exit(code=1)
    if profile not in {"default", "reasoning"}:
        typer.echo("Profile must be default or reasoning.", err=True)
        raise typer.Exit(code=1)
    resolved_model = default_model(provider, model)
    resolved_max_tokens, resolved_timeout = resolve_generation_limits(
        profile=profile, max_tokens=max_tokens, timeout=env_timeout_override(timeout)
    )
    config = RunConfig(
        provider=provider,  # type: ignore[arg-type]
        model=resolved_model,
        dataset=dataset,
        condition=condition,  # type: ignore[arg-type]
        output_dir=output_dir,
        limit=limit,
        case_ids=list(case_id or []),
        category=category,
        difficulty=difficulty,
        seed=seed,
        temperature=temperature,
        max_output_tokens=resolved_max_tokens,
        timeout_seconds=resolved_timeout,
        resume=resume,
        overwrite=overwrite,
        verbose=verbose,
        keep_alive=env_keep_alive(keep_alive),
        base_url=env_base_url(base_url),
        task_mode=task_mode,  # type: ignore[arg-type]
        concurrency=concurrency,
        think=think,
        profile=profile,  # type: ignore[arg-type]
        num_ctx=num_ctx,
        reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
    )
    typer.echo("Resolved run configuration:")
    typer.echo(json.dumps(config.public_dict(), indent=2, sort_keys=True))
    if overwrite and resume:
        typer.echo("Overwrite is set, so existing raw_results.jsonl will be replaced.")
    backend: MockProvider | OllamaProvider | MlxProvider
    if provider == "mock":
        backend = MockProvider()
        typer.echo(
            "Provider mock generates synthetic fixtures. These are not empirical model results."
        )
    elif provider == "mlx":
        backend = MlxProvider(model=resolved_model, reasoning_effort=config.reasoning_effort)
        try:
            backend.load()
        except Exception as exc:  # noqa: BLE001 - report and stop before writing rows
            typer.echo(f"Could not load {resolved_model} with mlx-lm: {sanitize_text(str(exc))}")
            raise typer.Exit(code=1) from exc
    elif provider == "openai":
        typer.echo("The openai provider is used by `pie adaptive` only.", err=True)
        raise typer.Exit(code=1)
    else:
        backend = OllamaProvider(base_url=config.base_url, keep_alive=config.keep_alive)
    try:
        summary = run_evaluation(config, backend)
    except RunnerError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        if isinstance(backend, OllamaProvider):
            backend.close()
    if summary.malformed_lines:
        typer.echo(
            "Preserved malformed JSONL lines from an interrupted write: "
            + ", ".join(str(number) for number in summary.malformed_lines)
        )
    typer.echo(
        f"Skipped: {summary.skipped}. Wrote: {summary.written}. "
        f"Planned: {summary.planned_units}. Backend errors: {summary.backend_errors}."
    )
    typer.echo(f"Results: {summary.output_path.name}")
    if verbose:
        rows, _malformed = load_results(summary.output_path)
        for row in rows[-summary.written :]:
            typer.echo(
                f"{row['case_id']} {row['condition']} outcome={row['outcome']} "
                f"attack={row['attack_score']} task={row['task_score']}"
            )


def _mlx_available() -> bool:
    import importlib.util

    return all(importlib.util.find_spec(name) is not None for name in ("mlx", "mlx_lm"))


@app.command("analyze")
def analyze_cmd(
    input_dir: Path = typer.Option(..., "--input-dir"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    reviews: Path | None = typer.Option(None, "--reviews", help="Optional completed review CSV."),
) -> None:
    """Compute metrics and write a Markdown report plus CSV tables."""
    results_path = input_dir / "raw_results.jsonl"
    if not results_path.is_file():
        typer.echo(f"Result file not found: {results_path.name}", err=True)
        raise typer.Exit(code=1)
    rows, malformed = load_results(results_path)
    if not rows:
        typer.echo("No valid result rows were found.", err=True)
        raise typer.Exit(code=1)
    if reviews is not None:
        try:
            human = load_human_reviews(reviews)
        except ReviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        rows = attach_human_labels(rows, human)
    summary = analyze_results(rows, output_dir, malformed_lines=malformed)
    origin = summary["result_origin"]
    if origin == "synthetic_mock":
        typer.echo(
            "These are synthetic mock results used to test the evaluation pipeline. "
            "They are not empirical findings about a language model."
        )
    typer.echo(f"Report written under {output_dir.name}")
    if malformed:
        typer.echo("Malformed lines were skipped and reported: " + ", ".join(map(str, malformed)))


def _load_many(input_dirs: list[Path]) -> list[tuple[Path, list[dict[str, Any]]]]:
    loaded: list[tuple[Path, list[dict[str, Any]]]] = []
    for input_dir in input_dirs:
        results_path = input_dir / "raw_results.jsonl"
        if not results_path.is_file():
            typer.echo(f"Result file not found: {input_dir.name}/raw_results.jsonl", err=True)
            raise typer.Exit(code=1)
        rows, malformed = load_results(results_path)
        if malformed:
            typer.echo(
                f"{input_dir.name}: skipped malformed lines {', '.join(map(str, malformed))}"
            )
        if not rows:
            typer.echo(f"No valid result rows in {input_dir.name}.", err=True)
            raise typer.Exit(code=1)
        loaded.append((input_dir, rows))
    return loaded


@app.command("compare")
def compare_cmd(
    input_dirs: list[Path] = typer.Option(
        ..., "--input-dir", help="Result directories to combine. Repeat the option."
    ),
    output_dir: Path = typer.Option(..., "--output-dir"),
    reviews: list[Path] | None = typer.Option(
        None, "--reviews", help="Completed review CSVs. Repeat the option."
    ),
) -> None:
    """Combine several result directories and compare models and conditions side by side."""
    loaded = _load_many(input_dirs)
    rows = [row for _dir, dir_rows in loaded for row in dir_rows]
    for review_path in reviews or []:
        try:
            human = load_human_reviews(review_path)
        except ReviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        rows = attach_human_labels(rows, human)
    summary = compare_results(rows, output_dir, sources=[str(path.name) for path, _ in loaded])
    if summary["result_origin"] != "empirical_model_run":
        typer.echo(
            "At least one source is synthetic mock output. Do not describe the combined "
            "tables as model performance."
        )
    typer.echo(
        f"Compared {len(loaded)} result sets, {summary['total_units']} units, "
        f"models: {', '.join(summary['models'])}."
    )
    typer.echo(f"Comparison written under {output_dir.name}")


@app.command("stats")
def stats_cmd(
    input_dirs: list[Path] = typer.Option(
        ..., "--input-dir", help="Result directories, one run per model. Repeat the option."
    ),
    output_dir: Path = typer.Option(..., "--output-dir"),
    reviews: list[Path] | None = typer.Option(
        None, "--reviews", help="Completed review CSVs, used to calibrate the lenient reading."
    ),
) -> None:
    """Paired McNemar tests, bootstrap intervals, power, and secondary readings."""
    loaded = _load_many(input_dirs)
    rows = [row for _dir, dir_rows in loaded for row in dir_rows]
    keys = [(row.get("model"), row.get("case_id"), row.get("condition")) for row in rows]
    if len(keys) != len(set(keys)):
        typer.echo(
            "Two rows share a model, case, and condition. Pass one run per model; use "
            "`pie variability` for repeats.",
            err=True,
        )
        raise typer.Exit(code=1)
    for review_path in reviews or []:
        try:
            human = load_human_reviews(review_path)
        except ReviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        rows = attach_human_labels(rows, human)
    try:
        cases = load_cases_for_rows(rows, Path.cwd())
    except CaseLookupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    annotate(rows, cases)
    summary = write_stats_report(rows, output_dir, sources=[path.name for path, _ in loaded])
    typer.echo(
        f"Wrote {len(summary['defense_tests'])} defense tests and "
        f"{len(summary['model_tests'])} model contrasts under {output_dir.name}"
    )


@app.command("variability")
def variability_cmd(
    input_dirs: list[Path] = typer.Option(
        ..., "--input-dir", help="Repeated runs of the same configuration. Repeat the option."
    ),
    output_dir: Path = typer.Option(..., "--output-dir"),
) -> None:
    """Measure how many units changed label across repeated runs of the same configuration."""
    if len(input_dirs) < 2:
        typer.echo("Variability needs at least two --input-dir values.", err=True)
        raise typer.Exit(code=1)
    loaded = _load_many(input_dirs)
    result = write_variability_report(
        [rows for _dir, rows in loaded], output_dir, sources=[p.name for p, _ in loaded]
    )
    typer.echo(
        f"Compared {result['runs']} runs over {result['units_compared']} units. "
        f"Outcome changed on {result['unstable_outcome']}; "
        f"response text identical on {result['identical_response_text']}."
    )
    typer.echo(f"Variability report written under {output_dir.name}")


@app.command("review")
def review_cmd(
    input_path: Path = typer.Option(..., "--input", help="Path to raw_results.jsonl."),
    output: Path = typer.Option(..., "--output", help="CSV path for the review queue."),
) -> None:
    """Write a prioritized manual-review CSV. Human label columns are left empty."""
    if not input_path.is_file():
        typer.echo(f"Result file not found: {input_path.name}", err=True)
        raise typer.Exit(code=1)
    rows, malformed = load_results(input_path)
    count = write_review_csv(output, rows)
    typer.echo(f"Wrote {count} review rows to {output.name}")
    if malformed:
        typer.echo("Malformed lines were preserved in the source file and omitted from the queue.")
