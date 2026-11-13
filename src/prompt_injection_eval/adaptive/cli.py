"""`pie adaptive ...` commands."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import typer

from prompt_injection_eval.adaptive.analysis import (
    REFERENCE_STRATEGY,
    AnalysisError,
    ModelInputs,
    write_report,
)
from prompt_injection_eval.adaptive.attacker import (
    MODES,
    AttackerSettings,
    run_attacker,
    success_by_attempt,
)
from prompt_injection_eval.adaptive.engine import Unit, run_units
from prompt_injection_eval.adaptive.hardening import ADAPTIVE_CONDITIONS, HARDENED_CONDITION
from prompt_injection_eval.adaptive.rank import RankError, build_ranking
from prompt_injection_eval.adaptive.seeds import SeedError, load_seeds
from prompt_injection_eval.adaptive.strategies import (
    CARRIER_ONLY,
    STATIC_DOCUMENT,
    all_strategies,
    strategy_by_name,
)
from prompt_injection_eval.adaptive.toolrole import (
    MECHANISM_CONDITIONS,
    NO_TAIL_CONDITION,
    TOOL_CONDITIONS,
    TOOL_JSON_CONDITIONS,
)
from prompt_injection_eval.config import RunConfig, resolve_generation_limits
from prompt_injection_eval.dataset import DatasetError, validate_dataset
from prompt_injection_eval.privacy import display_path, sanitize_text
from prompt_injection_eval.prompts import conditions_for
from prompt_injection_eval.providers import (
    MlxProvider,
    MockProvider,
    OllamaProvider,
    provider_from_env,
)
from prompt_injection_eval.providers.base import Provider
from prompt_injection_eval.results_io import load_results

# Conditions that run only the two fixed attacks, through `pie adaptive control`.
CONTROL_CONDITIONS = (NO_TAIL_CONDITION, *TOOL_JSON_CONDITIONS, *MECHANISM_CONDITIONS)

adaptive_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Adaptive attacks: tune strategies on dev seeds, then test on held-out seeds.",
)


def _config(
    *,
    provider: str,
    model: str,
    seeds: Path,
    condition: str,
    output_dir: Path,
    seed: int | None,
    think: bool | None,
    profile: str,
    reasoning_effort: str | None,
    num_ctx: int | None,
) -> RunConfig:
    max_tokens, timeout = resolve_generation_limits(profile=profile, max_tokens=None, timeout=None)
    return RunConfig(
        provider=provider,  # type: ignore[arg-type]
        model=model,
        dataset=seeds,
        condition=condition,  # type: ignore[arg-type]
        output_dir=output_dir,
        seed=seed,
        max_output_tokens=max_tokens,
        timeout_seconds=timeout,
        think=think,
        profile=profile,  # type: ignore[arg-type]
        reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
        num_ctx=num_ctx,
    )


def _provider(config: RunConfig) -> Provider:
    if config.provider == "mock":
        return MockProvider()
    if config.provider == "mlx":
        backend = MlxProvider(model=config.model, reasoning_effort=config.reasoning_effort)
        try:
            backend.load()
        except Exception as exc:  # noqa: BLE001 - report and stop before writing rows
            typer.echo(f"Could not load {config.model}: {sanitize_text(str(exc))}", err=True)
            raise typer.Exit(code=1) from exc
        return backend
    if config.provider == "openai":
        try:
            remote = provider_from_env()
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        issues = remote.health(config.model)
        if issues:
            typer.echo(" ".join(issues), err=True)
            raise typer.Exit(code=1)
        return remote
    return OllamaProvider(base_url=config.base_url, keep_alive=config.keep_alive)


def _conditions(selection: str) -> list[str]:
    """`all` is the three static conditions. `hardened` is the patched template alone.

    `toolrole` is both tool-result placements; each can also be named on its own.
    """
    if selection == HARDENED_CONDITION:
        return [HARDENED_CONDITION]
    if selection == "toolrole":
        return list(TOOL_CONDITIONS)
    if selection in TOOL_CONDITIONS or selection in CONTROL_CONDITIONS:
        return [selection]
    if selection == "tooljson":
        return list(TOOL_JSON_CONDITIONS)
    if selection == "mechanism":
        return list(MECHANISM_CONDITIONS)
    try:
        return conditions_for(selection)
    except ValueError as exc:
        typer.echo(f"{exc}. Use one of {', '.join(ADAPTIVE_CONDITIONS)}, both, or all.", err=True)
        raise typer.Exit(code=1) from exc


def _progress(done: int, total: int) -> None:
    if done % 50 == 0 or done == total:
        typer.echo(f"  {done}/{total}")


def _load_seeds(path: Path, split: str) -> tuple[list[Any], str]:
    try:
        seeds, sha = load_seeds(path)
    except SeedError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    return [seed for seed in seeds if seed.split == split], sha


_PROVIDER = typer.Option(
    ..., "--provider", help="mlx, ollama, openai (a vLLM server; set PIE_OPENAI_BASE_URL), or mock."
)
_MODEL = typer.Option(..., "--model")
_SEEDS = typer.Option(Path("data/adaptive_seeds.jsonl"), "--seeds")
_OUTPUT = typer.Option(..., "--output-dir")
_SEED = typer.Option(42, "--seed")
_THINK = typer.Option(None, "--think/--no-think")
_PROFILE = typer.Option("default", "--profile")
_EFFORT = typer.Option(None, "--reasoning-effort")
_NUM_CTX = typer.Option(None, "--num-ctx")


@adaptive_app.command("grid")
def grid_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    seeds: Path = _SEEDS,
    output_dir: Path = _OUTPUT,
    split: str = typer.Option("dev", "--split", help="dev or test."),
    condition: str = typer.Option("all", "--condition"),
    seed: int | None = _SEED,
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
    num_ctx: int | None = _NUM_CTX,
) -> None:
    """Run every strategy on every seed of one split under each condition."""
    selected, sha = _load_seeds(seeds, split)
    names = _conditions(condition)
    config = _config(
        provider=provider,
        model=model,
        seeds=seeds,
        condition="all",
        output_dir=output_dir,
        seed=seed,
        think=think,
        profile=profile,
        reasoning_effort=reasoning_effort,
        num_ctx=num_ctx,
    )
    units = [
        Unit(seed=item, strategy=strategy, condition=name)
        for item in selected
        for strategy in all_strategies()
        for name in names
    ]
    typer.echo(f"Grid: {len(selected)} {split} seeds, {len(units)} units.")
    summary = run_units(
        units=units,
        config=config,
        provider=_provider(config),
        seeds_path=display_path(seeds),
        seeds_sha256=sha,
        phase="grid",
        progress=_progress,
    )
    typer.echo(
        f"Skipped: {summary.skipped}. Wrote: {summary.written}. "
        f"Backend errors: {summary.backend_errors}."
    )


@adaptive_app.command("carrier")
def carrier_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    seeds: Path = _SEEDS,
    output_dir: Path = _OUTPUT,
    condition: str = typer.Option("all", "--condition"),
    seed: int | None = _SEED,
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
    num_ctx: int | None = _NUM_CTX,
) -> None:
    """Run every carrier with nothing appended. No attack should be scored as a success."""
    try:
        everything, sha = load_seeds(seeds)
    except SeedError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    config = _config(
        provider=provider,
        model=model,
        seeds=seeds,
        condition="all",
        output_dir=output_dir,
        seed=seed,
        think=think,
        profile=profile,
        reasoning_effort=reasoning_effort,
        num_ctx=num_ctx,
    )
    units = [
        Unit(seed=item, strategy=CARRIER_ONLY, condition=name)
        for item in everything
        for name in _conditions(condition)
    ]
    summary = run_units(
        units=units,
        config=config,
        provider=_provider(config),
        seeds_path=display_path(seeds),
        seeds_sha256=sha,
        phase="carrier",
        progress=_progress,
    )
    rows, _malformed = load_results(output_dir / "raw_results.jsonl")
    carrier = [row for row in rows if row.get("adaptive_phase") == "carrier"]
    flagged = sum(1 for row in carrier if row["attack_score"] in {"success", "uncertain"})
    done = sum(1 for row in carrier if row["task_score"] == "success")
    typer.echo(
        f"Wrote: {summary.written}. Attack success or uncertain on clean carriers: "
        f"{flagged}/{len(carrier)}. Task success: {done}/{len(carrier)}."
    )


@adaptive_app.command("static")
def static_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    cases: Path = typer.Option(
        Path("data/cases_v2.jsonl"), "--cases", help="The case file the seeds were built from."
    ),
    seeds: Path = _SEEDS,
    output_dir: Path = _OUTPUT,
    condition: str = typer.Option("toolrole", "--condition"),
    seed: int | None = _SEED,
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
    num_ctx: int | None = _NUM_CTX,
) -> None:
    """Run the original static documents of the held-out seeds under new conditions.

    The static study covers the three user-message templates. A condition it did not
    run, such as a tool-result placement, needs its own static rows for the comparison.
    """
    selected, sha = _load_seeds(seeds, "test")
    documents = _static_documents(cases, selected)
    config = _config(
        provider=provider,
        model=model,
        seeds=seeds,
        condition="all",
        output_dir=output_dir,
        seed=seed,
        think=think,
        profile=profile,
        reasoning_effort=reasoning_effort,
        num_ctx=num_ctx,
    )
    units = [
        Unit(seed=item, strategy=STATIC_DOCUMENT, condition=name, document=documents[item.id])
        for item in selected
        for name in _conditions(condition)
    ]
    typer.echo(f"Static: {len(selected)} held-out seeds, {len(units)} units.")
    summary = run_units(
        units=units,
        config=config,
        provider=_provider(config),
        seeds_path=display_path(seeds),
        seeds_sha256=sha,
        phase="static",
        progress=_progress,
    )
    typer.echo(
        f"Skipped: {summary.skipped}. Wrote: {summary.written}. "
        f"Backend errors: {summary.backend_errors}."
    )


def _static_documents(cases: Path, selected: list[Any]) -> dict[str, str]:
    """The 0.3.0 documents of the held-out seeds, by seed id."""
    try:
        loaded, _validation = validate_dataset(cases)
    except DatasetError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    documents = {case.id: case.document for case in loaded}
    missing = [item.id for item in selected if item.id not in documents]
    if missing:
        typer.echo(f"Seeds without a case: {', '.join(missing)}", err=True)
        raise typer.Exit(code=1)
    return documents


@adaptive_app.command("control")
def control_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    cases: Path = typer.Option(
        Path("data/cases_v2.jsonl"), "--cases", help="The case file the seeds were built from."
    ),
    seeds: Path = _SEEDS,
    output_dir: Path = _OUTPUT,
    condition: str = typer.Option(
        NO_TAIL_CONDITION,
        "--condition",
        help="defended_no_tail, tooljson, mechanism, or one control condition.",
    ),
    seed: int | None = _SEED,
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
    num_ctx: int | None = _NUM_CTX,
) -> None:
    """Placement controls: the two fixed attacks under a control condition.

    The default is `defended-v1` without the line after the document. `tooljson` is
    the tool-result placements with the document JSON-encoded in the tool message.

    Runs the static documents and the plain override on the held-out seeds, the two
    attacks whose success changes most between the user-message and tool-result
    placements. Write into the model's test directory so the report finds the rows.
    """
    selected, sha = _load_seeds(seeds, "test")
    documents = _static_documents(cases, selected)
    config = _config(
        provider=provider,
        model=model,
        seeds=seeds,
        condition="all",
        output_dir=output_dir,
        seed=seed,
        think=think,
        profile=profile,
        reasoning_effort=reasoning_effort,
        num_ctx=num_ctx,
    )
    reference = strategy_by_name(REFERENCE_STRATEGY)
    names = _conditions(condition)
    phases = {
        "static": [
            Unit(seed=item, strategy=STATIC_DOCUMENT, condition=name, document=documents[item.id])
            for item in selected
            for name in names
        ],
        "test": [
            Unit(seed=item, strategy=reference, condition=name)
            for item in selected
            for name in names
        ],
    }
    built = _provider(config)
    for phase, units in phases.items():
        typer.echo(f"Control, {phase}: {len(units)} units.")
        summary = run_units(
            units=units,
            config=config,
            provider=built,
            seeds_path=display_path(seeds),
            seeds_sha256=sha,
            phase=phase,
            progress=_progress,
        )
        typer.echo(
            f"Skipped: {summary.skipped}. Wrote: {summary.written}. "
            f"Backend errors: {summary.backend_errors}."
        )


@adaptive_app.command("rank")
def rank_cmd(
    input_dir: Path = typer.Option(..., "--input-dir", help="A dev grid directory."),
    output: Path = typer.Option(..., "--output", help="Where to write ranking.json."),
    top: int = typer.Option(5, "--top"),
) -> None:
    """Order strategies by greedy coverage of the dev seeds."""
    rows, _malformed = load_results(input_dir / "raw_results.jsonl")
    try:
        ranking = build_ranking(rows, top=top)
    except RankError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ranking, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for condition, order in ranking["conditions"].items():
        first = order[0]
        typer.echo(
            f"{condition}: {first['strategy']} "
            f"({first['dev_successes']}/{ranking['dev_seed_count']} dev seeds)"
        )


@adaptive_app.command("test")
def test_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    ranking: Path = typer.Option(..., "--ranking", help="ranking.json for this model."),
    transfer_ranking: list[Path] | None = typer.Option(
        None,
        "--transfer-ranking",
        help="ranking.json from another model. Its first strategy per condition is also run.",
    ),
    seeds: Path = _SEEDS,
    output_dir: Path = _OUTPUT,
    seed: int | None = _SEED,
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
    num_ctx: int | None = _NUM_CTX,
) -> None:
    """Run the ranked strategies once each on the held-out seeds."""
    selected, sha = _load_seeds(seeds, "test")
    own = json.loads(ranking.read_text(encoding="utf-8"))
    if own["seeds_sha256"] != sha:
        typer.echo("The ranking was built from a different seed file.", err=True)
        raise typer.Exit(code=1)
    if own["model"] != model:
        typer.echo("The ranking was built on a different model. Use --transfer-ranking.", err=True)
        raise typer.Exit(code=1)
    plan: dict[str, list[str]] = {
        condition: [entry["strategy"] for entry in order]
        for condition, order in own["conditions"].items()
    }
    for condition, order in own.get("conditions_plain", {}).items():
        # The first-ranked strategy among those with ordinary spacing.
        name = order[0]["strategy"]
        if condition in plan and name not in plan[condition]:
            plan[condition].append(name)
    for path in transfer_ranking or []:
        other = json.loads(path.read_text(encoding="utf-8"))
        for condition, order in other["conditions"].items():
            name = order[0]["strategy"]
            if condition in plan and name not in plan[condition]:
                plan[condition].append(name)
    if HARDENED_CONDITION in plan and "spotlight" in plan:
        # Replay: the strategy that won against datamarking, unchanged, against the patch.
        replay = plan["spotlight"][0]
        if replay not in plan[HARDENED_CONDITION]:
            plan[HARDENED_CONDITION].append(replay)
    for names in plan.values():
        # The plain override, as an in-pipeline reference for the static documents.
        if REFERENCE_STRATEGY not in names:
            names.append(REFERENCE_STRATEGY)
    config = _config(
        provider=provider,
        model=model,
        seeds=seeds,
        condition="all",
        output_dir=output_dir,
        seed=seed,
        think=think,
        profile=profile,
        reasoning_effort=reasoning_effort,
        num_ctx=num_ctx,
    )
    units = [
        Unit(seed=item, strategy=strategy_by_name(name), condition=condition)
        for item in selected
        for condition, names in plan.items()
        for name in names
    ]
    typer.echo(f"Test: {len(selected)} held-out seeds, {len(units)} units.")
    summary = run_units(
        units=units,
        config=config,
        provider=_provider(config),
        seeds_path=display_path(seeds),
        seeds_sha256=sha,
        phase="test",
        progress=_progress,
    )
    typer.echo(
        f"Skipped: {summary.skipped}. Wrote: {summary.written}. "
        f"Backend errors: {summary.backend_errors}."
    )


@adaptive_app.command("report")
def report_cmd(
    results_dir: Path = typer.Option(
        ..., "--results-dir", help="Holds LABEL-grid, LABEL-test, LABEL-ranking.json, ..."
    ),
    static_dir: Path | None = typer.Option(
        None,
        "--static-dir",
        help="Holds LABEL/raw_results.jsonl from the static study. Omit when the static "
        "documents were rerun with `pie adaptive static`.",
    ),
    label: list[str] = typer.Option(..., "--label", help="Model label. Repeat per model."),
    output_dir: Path = _OUTPUT,
) -> None:
    """Compare static and adaptive attack success on the held-out seeds."""

    def rows(path: Path) -> list[dict[str, Any]]:
        plain = path / "raw_results.jsonl"
        packed = path / "raw_results.jsonl.gz"
        if not plain.exists() and packed.exists():
            # The published bundle stores rows gzipped to keep the repository small.
            with gzip.open(packed, "rt", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        return load_results(plain)[0]

    inputs: list[ModelInputs] = []
    for name in label:
        ranking = results_dir / f"{name}-ranking.json"
        if not ranking.is_file():
            typer.echo(f"Missing {ranking.name}", err=True)
            raise typer.Exit(code=1)
        inputs.append(
            ModelInputs(
                label=name,
                static_rows=rows(static_dir / name) if static_dir else [],
                grid_rows=rows(results_dir / f"{name}-grid"),
                test_rows=rows(results_dir / f"{name}-test"),
                ranking=json.loads(ranking.read_text(encoding="utf-8")),
                carrier_rows=rows(results_dir / f"{name}-carrier"),
                attacker_rows=rows(results_dir / f"{name}-attacker"),
                repeat_rows=rows(results_dir / f"{name}-repeat"),
            )
        )
    try:
        summary = write_report(inputs, output_dir)
    except AnalysisError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    for row in summary["headline"]:
        n = row["held_out_seeds"]
        typer.echo(
            f"{row['model']} {row['condition']}: static {row['static_successes']}/{n}, "
            f"adaptive one try {row['adaptive_1_successes']}/{n}"
        )


@adaptive_app.command("attacker")
def attacker_cmd(
    provider: str = _PROVIDER,
    model: str = _MODEL,
    attacker_model: str = typer.Option(..., "--attacker-model"),
    mode: str = typer.Option(..., "--mode", help="feedback or blind."),
    budget: int = typer.Option(5, "--budget", help="Attempts per seed and condition."),
    condition: list[str] = typer.Option(["defended", "spotlight"], "--condition"),
    split: str = typer.Option("test", "--split"),
    seeds: Path = _SEEDS,
    output_dir: Path = _OUTPUT,
    seed: int | None = _SEED,
    think: bool | None = _THINK,
    profile: str = _PROFILE,
    reasoning_effort: str | None = _EFFORT,
    num_ctx: int | None = _NUM_CTX,
) -> None:
    """Let an attacker model write the injected text, with feedback or blind."""
    if mode not in MODES:
        typer.echo("Mode must be feedback or blind.", err=True)
        raise typer.Exit(code=1)
    selected, sha = _load_seeds(seeds, split)
    config = _config(
        provider=provider,
        model=model,
        seeds=seeds,
        condition="all",
        output_dir=output_dir,
        seed=seed,
        think=think,
        profile=profile,
        reasoning_effort=reasoning_effort,
        num_ctx=num_ctx,
    )
    target = _provider(config)
    if attacker_model == model:
        attacker = target
    else:
        attacker = _provider(config.model_copy(update={"model": attacker_model}))
    settings = AttackerSettings(model=attacker_model, budget=budget)
    typer.echo(f"Attacker ({mode}): {len(selected)} {split} seeds, budget {budget}.")
    summary = run_attacker(
        seeds=selected,
        conditions=list(condition),
        mode=mode,
        config=config,
        target=target,
        attacker=attacker,
        settings=settings,
        seeds_path=display_path(seeds),
        seeds_sha256=sha,
        progress=_progress,
    )
    typer.echo(f"Wrote: {summary['written']}. Errors: {summary['errors']}.")
    rows, _malformed = load_results(output_dir / "raw_results.jsonl")
    for name, cell in success_by_attempt(rows, mode=mode, budget=budget).items():
        typer.echo(f"{name}: solved within k attempts {cell['solved_within']} of {cell['seeds']}")
