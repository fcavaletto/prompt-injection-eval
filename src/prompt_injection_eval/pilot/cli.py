"""`pie pilot`: the serialization pilot. Design: docs/pilot-design.md."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import typer

from prompt_injection_eval.pilot import DEV_SUITE, EVAL_SUITE, FORMATS, PilotError
from prompt_injection_eval.providers.base import Provider

pilot_app = typer.Typer(
    help="Serialization pilot on AgentDojo tasks. Nothing here is run without a server you start.",
    no_args_is_help=True,
)

_PROVIDER = typer.Option(
    "openai", "--provider", help="openai (a vLLM server) or scripted (offline)."
)
_POLICY = typer.Option("benign", "--scripted-policy", help="benign, attacker, obedient or silent.")
_MODEL = typer.Option(..., "--model")
_LABEL = typer.Option(..., "--label", help="Short name for the model, used in reports.")
_OUTPUT = typer.Option(..., "--output-dir")
_THINK = typer.Option(None, "--think/--no-think")
_DEADLINE = typer.Option(
    None, "--deadline-minutes", help="Start no new episode after this many minutes. Resumable."
)


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def _provider(name: str, model: str, policy: str) -> Provider:
    if name == "scripted":
        from prompt_injection_eval.pilot.scripted import ScriptedProvider

        return ScriptedProvider(policy)
    if name != "openai":
        raise _fail("Use --provider openai (a vLLM server) or scripted.")
    from prompt_injection_eval.providers import provider_from_env

    try:
        remote = provider_from_env()
    except ValueError as exc:
        raise _fail(str(exc)) from exc
    issues = remote.health(model)
    if issues:
        raise _fail(" ".join(issues))
    return remote


def _progress(done: int, total: int) -> None:
    if done % 50 == 0 or done == total:
        typer.echo(f"  {done}/{total}")


@pilot_app.command("check")
def check_cmd() -> None:
    """Offline self-check: pinned AgentDojo, suites, serializers, twins, injection points."""
    from prompt_injection_eval.pilot import adapter, attacks, runner, serialize

    try:
        adapter.require_agentdojo()
    except PilotError as exc:
        raise _fail(str(exc)) from exc
    from agentdojo.functions_runtime import FunctionsRuntime

    problems = 0
    for name in (DEV_SUITE, EVAL_SUITE):
        s = adapter.suite(name)
        users, goals = runner.tasks(name)
        points: Counter[int] = Counter()
        records = 0
        for user in users:
            points[adapter.injection_plan(name, user).index] += 1
            task = s.user_tasks[user]
            env = task.init_environment(adapter.environment(name))
            runtime = FunctionsRuntime(s.tools)
            for call in task.ground_truth(env):
                result, _ = runtime.run_function(env, call.function, call.args, raise_on_error=True)
                records += 1
                problems += not serialize.round_trips(serialize.canonical(result))
        twins = sum(adapter.twin(name, goal) is not None for goal in goals)
        goal = s.injection_tasks[goals[0]].GOAL
        vectors = adapter.injection_plan(name, users[0]).vectors
        altered = adapter.yaml_loading_alters(
            name, dict.fromkeys(vectors, attacks.render(attacks.BASELINE, goal))
        )
        typer.echo(
            f"{name}: {len(users)} user tasks, {len(goals)} attacker goals, {len(users) * len(goals)} pairs, "
            f"suite {adapter.suite_sha256(name)[:12]}; injection point by reference-call index {dict(points)}; "
            f"{records} reference tool results round-trip in both formats; {twins}/{len(goals)} benign twins; "
            f"AgentDojo's own YAML loading would alter the baseline payload: {altered}"
        )
    typer.echo(
        f"attack library {attacks.library_sha256()[:12]}: baseline + {len(attacks.LIBRARY)} candidates"
    )
    if problems:
        raise _fail(f"{problems} tool results did not round-trip.")


@pilot_app.command("template-check")
def template_check_cmd(
    repository: str = typer.Option(
        ..., "--repository", help="Hugging Face repository of the model."
    ),
    revision: str | None = typer.Option(None, "--revision"),
    think: bool | None = _THINK,
) -> None:
    """Free pre-flight: does this model's chat template deliver the pilot's conversations?

    Renders reference-solution conversations for every development and pilot task in both
    formats with the model's own template and runs the delivery check on each prompt. It
    downloads tokenizer files only. It says nothing about what a server adds.
    """
    from prompt_injection_eval.pilot import attacks, episode, runner
    from prompt_injection_eval.pilot.scripted import ScriptedProvider, template_renderer

    try:
        backend = ScriptedProvider(
            "attacker", renderer=template_renderer(repository, revision, think)
        )
    except PilotError as exc:
        raise _fail(str(exc)) from exc
    settings = episode.Settings(model=repository, label="template-check", think=think)
    statuses: Counter[str] = Counter()
    defects: Counter[str] = Counter()
    for suite_name in (DEV_SUITE, EVAL_SUITE):
        users, goals = runner.tasks(suite_name)
        for position, user in enumerate(users):
            for fmt in FORMATS:
                goal = goals[position % len(goals)]
                attack = [attacks.BASELINE, *attacks.candidate_ids()][position % 9]
                for spec in (
                    episode.Spec(suite_name, "attack", fmt, user, goal, attack, 0),
                    episode.Spec(suite_name, "scratch", fmt, user, None, None, 0),
                ):
                    trace = episode.run(spec, backend, settings)
                    statuses[trace["status"]] += 1
                    defects.update(d.split(":")[0] for d in trace["delivery_defects"])
    typer.echo(f"{repository}: {dict(statuses)}; defects {dict(defects) or 'none'}")
    if set(statuses) != {"completed"}:
        raise _fail(
            "This template does not deliver the pilot's conversations. Do not run this model."
        )


@pilot_app.command("plan")
def plan_cmd(
    calls_per_second: float = typer.Option(3.5, help="Measured in the smoke run. 3.5 is a guess."),
    calls_per_episode: float = typer.Option(6.0, help="Measured in the smoke run. 6 is a guess."),
    dollars_per_hour: float = typer.Option(2.70),
) -> None:
    """Planned episodes per phase for one model, with a time and cost projection."""
    from prompt_injection_eval.pilot import runner

    placeholder = {"selected": dict.fromkeys(FORMATS, "x") | {"json": "y"}, "sha256": ""}
    total = 0
    for phase in runner.PHASES:
        units = runner.plan(phase, placeholder)
        hours = len(units) * calls_per_episode / calls_per_second / 3600
        total += len(units)
        typer.echo(
            f"{phase:14s} {len(units):5d} episodes  ~{hours:4.2f} h  ~${hours * dollars_per_hour:5.2f}"
        )
    hours = total * calls_per_episode / calls_per_second / 3600
    typer.echo(
        f"{'one model':14s} {total:5d} episodes  ~{hours:4.2f} h  ~${hours * dollars_per_hour:5.2f} (server start not included)"
    )


@pilot_app.command("run")
def run_cmd(
    phase: str = typer.Argument(
        ..., help="smoke, dev-controls, select, eval-controls or evaluate."
    ),
    model: str = _MODEL,
    label: str = _LABEL,
    output_dir: Path = _OUTPUT,
    provider: str = _PROVIDER,
    scripted_policy: str = _POLICY,
    think: bool | None = _THINK,
    frozen: Path | None = typer.Option(None, "--frozen", help="frozen_attacks.json, for evaluate."),
    deadline_minutes: float | None = _DEADLINE,
) -> None:
    """Run one phase. Exit code 3 means the deadline stopped it; rerun to resume."""
    from prompt_injection_eval.pilot import runner
    from prompt_injection_eval.pilot.episode import Settings

    backend = _provider(provider, model, scripted_policy)
    frozen_attacks = json.loads(frozen.read_text()) if frozen else None
    if frozen_attacks and frozen_attacks["label"] != label:
        raise _fail(f"{frozen} was frozen for {frozen_attacks['label']}, not {label}.")
    try:
        summary = runner.run_phase(
            phase,
            backend,
            Settings(model=model, label=label, think=think),
            output_dir,
            frozen=frozen_attacks,
            deadline_minutes=deadline_minutes,
            progress=_progress,
        )
    except PilotError as exc:
        raise _fail(str(exc)) from exc
    rate = summary.model_calls / summary.seconds if summary.seconds else 0.0
    per_episode = summary.model_calls / summary.written if summary.written else 0.0
    typer.echo(
        f"{phase}: planned {summary.planned}, already done {summary.already_done}, written {summary.written}, "
        f"remaining {summary.remaining}. Statuses: {summary.statuses}. "
        f"{summary.model_calls} model calls in {summary.seconds / 60:.1f} min "
        f"({rate:.2f} calls/s, {per_episode:.1f} calls per episode)."
    )
    not_valid = sum(n for status, n in summary.statuses.items() if status != "completed")
    if phase == "smoke" and not_valid:
        raise _fail(
            "Smoke test failed: some episodes are not valid measurements. Read the traces before spending more."
        )
    if summary.stopped_by_deadline:
        typer.echo(
            "Stopped by the deadline. Rerun the same command to resume, or stop here.", err=True
        )
        raise typer.Exit(code=3)


@pilot_app.command("freeze")
def freeze_cmd(select_dir: Path = typer.Option(..., "--select-dir")) -> None:
    """Choose the attack for each format from a finished selection phase."""
    from prompt_injection_eval.pilot import runner

    try:
        frozen = runner.freeze(select_dir)
    except PilotError as exc:
        raise _fail(str(exc)) from exc
    typer.echo(
        json.dumps(
            {
                k: frozen[k]
                for k in (
                    "selected",
                    "identical",
                    "baseline_development_successes",
                    "baseline_near_floor_on_text",
                    "sha256",
                )
            },
            indent=2,
        )
    )
    typer.echo(f"Written to {select_dir / 'frozen_attacks.json'}. Commit it before the evaluation.")


@pilot_app.command("report")
def report_cmd(
    phase_dir: list[Path] = typer.Option(
        ..., "--phase-dir", help="Repeat for each phase of one model."
    ),
    output_dir: Path = _OUTPUT,
) -> None:
    """Build the report for one model from stored traces."""
    from prompt_injection_eval.pilot import analysis

    summary = analysis.report(phase_dir, output_dir)
    typer.echo(json.dumps(summary, indent=2, default=str))
    typer.echo(f"Report written to {output_dir / 'report.md'}")
