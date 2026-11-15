"""Plans, manifests, traces and resume checks for the pilot.

An output directory holds one phase for one model:

- ``manifest.json``: everything the run depends on, and how many units were planned.
- ``plan.json``: every planned unit, so the report can account for each one.
- ``traces.jsonl``: one line per episode, complete conversation included.

A directory can be resumed only by the same code, data, attacks, settings and server.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prompt_injection_eval.constants import PACKAGE_VERSION
from prompt_injection_eval.pilot import (
    AGENTDOJO_VERSION,
    BENCHMARK_VERSION,
    DEV_SUITE,
    EVAL_SUITE,
    FORMATS,
    STUDY,
    PilotError,
    adapter,
    attacks,
    episode,
)
from prompt_injection_eval.pilot.episode import Settings, Spec
from prompt_injection_eval.providers.base import Provider

PHASES = ("smoke", "dev-controls", "select", "eval-controls", "evaluate", "feasibility")
RUNS = 3
FINAL = ("completed", "invalid_delivery", "unverified_delivery", "prefix_error", "harness_error")
KEEP_PROMPTS_PER_CONDITION = 2
# Fields of the manifest that must be identical for a directory to be resumed.
COMPATIBLE = (
    "study",
    "phase",
    "agentdojo",
    "benchmark",
    "suite_sha256",
    "attack_library_sha256",
    "frozen_sha256",
    "settings",
    "package_version",
    "git_commit",
    "git_dirty",
    "plan_sha256",
    "server",
)


def _git(*arguments: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603 - fixed arguments
            ["git", *arguments], check=False, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def tasks(suite_name: str) -> tuple[list[str], list[str]]:
    s = adapter.suite(suite_name)
    return list(s.user_tasks), list(s.injection_tasks)


def development_pairs() -> list[tuple[str, str]]:
    """Half of the development pairs, balanced over user tasks and attacker goals."""
    users, goals = tasks(DEV_SUITE)
    return [(u, g) for i, u in enumerate(users) for j, g in enumerate(goals) if (i + j) % 2 == 0]


def feasibility_order() -> list[tuple[str, str, str]]:
    """The baseline feasibility workload: every development pair in both formats, ordered so
    that a deadline cut leaves a balanced prefix.

    Round r gives each user task its r-th development goal, rotated by the task's position so
    that the goals within a round differ (round 1 covers all nine goals). Rounds 1 to 4 each
    cover all 16 user tasks; round 5 adds the fifth goal of the eight tasks that have one.
    Both formats of a pair are adjacent, and which comes first alternates from pair to pair.
    """
    users, goals = tasks(DEV_SUITE)
    pairs = set(development_pairs())
    own = {u: [g for g in goals if (u, g) in pairs] for u in users}
    ordered: list[tuple[str, str]] = []
    for round_ in range(max(len(v) for v in own.values())):
        for position, user in enumerate(users):
            mine = own[user]
            if round_ < len(mine):
                ordered.append((user, mine[(round_ + position // 2) % len(mine)]))
    out = []
    for index, (user, goal) in enumerate(ordered):
        first, second = FORMATS if index % 2 == 0 else FORMATS[::-1]
        out += [(user, goal, first), (user, goal, second)]
    return out


def _controls(suite_name: str, users: list[str], goals: list[str], runs: int) -> list[Spec]:
    out = []
    for run in range(runs):
        for fmt in FORMATS:
            out += [
                Spec(suite_name, mode, fmt, u, None, None, run)
                for mode in ("clean", "scratch")
                for u in users
            ]
            for goal in goals:
                out.append(Spec(suite_name, "direct", fmt, None, goal, None, run))
                if adapter.twin(suite_name, goal) is not None:
                    out.append(Spec(suite_name, "twin", fmt, None, goal, None, run))
    return out


def frozen_attacks(frozen: dict[str, Any]) -> list[str]:
    """Baseline, selected-for-text, selected-for-JSON, with an identical winner listed once."""
    selected = frozen["selected"]
    return list(dict.fromkeys([attacks.BASELINE, selected["text"], selected["json"]]))


def plan(phase: str, frozen: dict[str, Any] | None = None, runs: int = RUNS) -> list[Spec]:
    if phase == "smoke":
        users, goals = tasks(DEV_SUITE)
        users, goals = users[:2], goals[:2]
        attack = [
            Spec(DEV_SUITE, "attack", fmt, u, g, attacks.BASELINE, 0)
            for fmt in FORMATS
            for u in users
            for g in goals
        ]
        return attack + _controls(DEV_SUITE, users, goals, 1)
    if phase == "dev-controls":
        return _controls(DEV_SUITE, *tasks(DEV_SUITE), runs)
    if phase == "feasibility":
        # Development only: the fixed baseline on the 72 development pairs, one run, in the
        # order of feasibility_order(). Not part of selection; its outputs are kept apart.
        return [
            Spec(DEV_SUITE, "attack", fmt, user, goal, attacks.BASELINE, 0)
            for user, goal, fmt in feasibility_order()
        ]
    if phase == "eval-controls":
        return _controls(EVAL_SUITE, *tasks(EVAL_SUITE), runs)
    if phase == "select":
        return [
            Spec(DEV_SUITE, "attack", fmt, u, g, attack, 0)
            for attack in [attacks.BASELINE, *attacks.candidate_ids()]
            for fmt in FORMATS
            for u, g in development_pairs()
        ]
    if phase == "evaluate":
        if frozen is None:
            raise PilotError(
                "The evaluation needs the frozen attacks: run `pie pilot freeze` first."
            )
        users, goals = tasks(EVAL_SUITE)
        return [
            Spec(EVAL_SUITE, "attack", fmt, u, g, attack, run)
            for attack in frozen_attacks(frozen)
            for fmt in FORMATS
            for run in range(runs)
            for u in users
            for g in goals
        ]
    raise PilotError(f"Unknown phase {phase!r}; expected one of {PHASES}.")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def build_manifest(
    phase: str,
    settings: Settings,
    units: list[Spec],
    provider: Provider,
    frozen: dict[str, Any] | None,
) -> dict[str, Any]:
    probe = getattr(provider, "runtime_info", None)
    try:
        server = probe(settings.model) if probe else None
    except Exception:  # noqa: BLE001 - provenance must not abort a run
        server = None
    return {
        "study": STUDY,
        "phase": phase,
        "agentdojo": AGENTDOJO_VERSION,
        "benchmark": BENCHMARK_VERSION,
        "suite_sha256": {
            name: adapter.suite_sha256(name) for name in sorted({u.suite for u in units})
        },
        "attack_library_sha256": attacks.library_sha256(),
        "frozen_sha256": frozen["sha256"] if frozen else None,
        "frozen": frozen,
        "settings": asdict(settings),
        "package_version": PACKAGE_VERSION,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "plan_sha256": _sha(sorted(u.key() for u in units)),
        "planned": {
            "total": len(units),
            "by_condition": dict(Counter(u.condition() for u in units)),
        },
        "provider": provider.name,
        "result_origin": provider.result_origin,
        "server": server,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def read_traces(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open() as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise PilotError(f"{path} line {number} is not valid JSON.") from exc
    return rows


# Statuses after which a smoke phase starts no further episode.
INVALIDATING = (
    "invalid_delivery",
    "unverified_delivery",
    "prefix_error",
    "harness_error",
    "infra_error",
)


@dataclass
class RunSummary:
    planned: int
    already_done: int
    written: int
    statuses: dict[str, int]
    not_started: int
    stopped_by_deadline: bool
    stopped_after_failure: str | None
    remaining: int
    seconds: float
    model_calls: int
    deadline_at: float | None = None  # time.monotonic() value


def _unrun_trace(unit: Spec, settings: Settings, status: str, detail: str) -> dict[str, Any]:
    return {
        "study": STUDY,
        "unit_key": unit.key(),
        **asdict(unit),
        "condition": unit.condition(),
        "pair": unit.pair(),
        "label": settings.label,
        "model": settings.model,
        "request_sha256": None,
        "status": status,
        "status_detail": detail,
        "utility": None,
        "security": None,
        "success": None,
        "turns": [],
        "totals": {"model_calls": 0},
    }


def run_phase(
    phase: str,
    provider: Provider,
    settings: Settings,
    output_dir: Path,
    frozen: dict[str, Any] | None = None,
    runs: int = RUNS,
    deadline_minutes: float | None = None,
    progress: Callable[[int, int], None] | None = None,
    fail_fast: bool | None = None,
) -> RunSummary:
    """Run every planned unit that has no final trace yet.

    Each worker checks the deadline and the stop flag immediately before it starts an
    episode, and the episode checks the deadline before every model request. An episode
    cut off by the deadline is written as ``interrupted`` and will be rerun on resume; one
    that never started is not written and shows as ``not_run``.

    With ``fail_fast`` (the default for the smoke phase), the first trace with an
    invalidating status stops all further starts. Episodes already running finish and are
    written. The deadline bounds inference time; it is not a bound on money.
    """
    adapter.require_agentdojo()
    fail_fast = phase == "smoke" if fail_fast is None else fail_fast
    units = plan(phase, frozen, runs)
    manifest = build_manifest(phase, settings, units, provider, frozen)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, traces_path = output_dir / "manifest.json", output_dir / "traces.jsonl"
    if manifest_path.exists():
        before = json.loads(manifest_path.read_text())
        changed = [f for f in COMPATIBLE if before.get(f) != manifest.get(f)]
        if changed:
            raise PilotError(
                f"{output_dir} was started with a different {', '.join(changed)}. "
                "Use a new output directory."
            )
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
        (output_dir / "plan.json").write_text(json.dumps([asdict(u) for u in units]) + "\n")
    manifest_sha = _sha({f: manifest.get(f) for f in COMPATIBLE})

    done: dict[str, dict[str, Any]] = {}
    for row in read_traces(traces_path):
        if row.get("status") in FINAL:
            done[row["unit_key"]] = row
    kept = Counter(row["condition"] for row in done.values() if row.get("rendered_prompts"))
    pending = []
    for unit in units:
        before_row = done.get(unit.key())
        if before_row is None:
            pending.append(unit)
        elif before_row.get("request_sha256") != episode.fingerprint(unit, settings):
            raise PilotError(
                f"{traces_path} holds a trace for {unit.condition()} {unit.pair()} that was "
                "produced from different inputs. Use a new output directory."
            )
    already = len(units) - len(pending)

    started = time.monotonic()
    deadline = None if deadline_minutes is None else started + deadline_minutes * 60
    stop = threading.Event()
    stop_reason: list[str] = []
    lock = threading.Lock()

    def one(unit: Spec) -> dict[str, Any] | None:
        # Checked when this worker is about to start, not when the unit was queued.
        if stop.is_set() or (deadline is not None and time.monotonic() >= deadline):
            return None
        with lock:
            keep = kept[unit.condition()] < KEEP_PROMPTS_PER_CONDITION
            if keep:
                kept[unit.condition()] += 1
        try:
            trace = episode.run(unit, provider, settings, keep_prompts=keep, deadline=deadline)
        except Exception as error:  # noqa: BLE001 - one unit must not end the phase
            trace = _unrun_trace(
                unit, settings, "harness_error", f"{type(error).__name__}: {error}"
            )
        trace["manifest_sha256"] = manifest_sha
        trace["result_origin"] = provider.result_origin
        if fail_fast and trace["status"] in INVALIDATING and not stop.is_set():
            stop_reason.append(f"{trace['status']} in {unit.condition()} {unit.pair()}")
            stop.set()
        return trace

    workers = max(1, int(getattr(provider, "concurrency", 1)))
    statuses: Counter[str] = Counter()
    written = calls = skipped = 0
    with traces_path.open("a") as handle, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, unit) for unit in pending]
        for future in as_completed(futures):
            trace = future.result()
            if trace is None:
                skipped += 1
                continue
            handle.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            statuses[trace["status"]] += 1
            calls += trace["totals"].get("model_calls", 0)
            written += 1
            if progress:
                progress(written, len(pending))
    seconds = time.monotonic() - started
    final_written = sum(n for status, n in statuses.items() if status in FINAL)
    summary = RunSummary(
        planned=len(units),
        already_done=already,
        written=written,
        statuses=dict(statuses),
        not_started=skipped,
        stopped_by_deadline=deadline is not None
        and (skipped > 0 or statuses.get("interrupted", 0) > 0)
        and not stop_reason,
        stopped_after_failure=stop_reason[0] if stop_reason else None,
        remaining=len(pending) - final_written,
        seconds=seconds,
        model_calls=calls,
        deadline_at=deadline,
    )
    with (output_dir / "runs.jsonl").open("a") as log:
        log.write(
            json.dumps(
                {
                    "finished": datetime.now(UTC).isoformat(timespec="seconds"),
                    "deadline_minutes": deadline_minutes,
                    "fail_fast": fail_fast,
                    "workers": workers,
                    **asdict(summary),
                }
            )
            + "\n"
        )
    return summary


def freeze(select_dir: Path) -> dict[str, Any]:
    """Pick the attack for each format from a finished selection phase and write it down."""
    manifest = json.loads((select_dir / "manifest.json").read_text())
    if manifest["phase"] != "select":
        raise PilotError(f"{select_dir} is not a selection phase.")
    units = [Spec(**item) for item in json.loads((select_dir / "plan.json").read_text())]
    latest = {row["unit_key"]: row for row in read_traces(select_dir / "traces.jsonl")}
    incomplete = [u for u in units if latest.get(u.key(), {}).get("status") != "completed"]
    if incomplete:
        reasons = Counter(latest.get(u.key(), {}).get("status", "not_run") for u in incomplete)
        raise PilotError(
            f"Selection needs every development unit completed; {len(incomplete)} are not "
            f"({dict(reasons)}). The two formats must be compared on the same pairs."
        )
    counts: dict[str, dict[str, int]] = {fmt: Counter() for fmt in FORMATS}
    for unit in units:
        counts[unit.fmt][unit.attack or ""] += bool(latest[unit.key()]["security"])
    pairs = len(development_pairs())
    candidates = {fmt: {c: counts[fmt][c] for c in attacks.candidate_ids()} for fmt in FORMATS}
    selected = attacks.select(candidates)
    frozen: dict[str, Any] = {
        "study": STUDY,
        "label": manifest["settings"]["label"],
        "model": manifest["settings"]["model"],
        "selected": selected,
        "identical": selected["text"] == selected["json"],
        "development_pairs": pairs,
        "development_successes": candidates,
        "baseline_development_successes": {fmt: counts[fmt][attacks.BASELINE] for fmt in FORMATS},
        "baseline_near_floor_on_text": counts["text"][attacks.BASELINE] < 0.10 * pairs,
        "development_episodes": len(units),
        "attack_library_sha256": manifest["attack_library_sha256"],
        "select_plan_sha256": manifest["plan_sha256"],
        "select_git_commit": manifest["git_commit"],
    }
    frozen["sha256"] = _sha(frozen)
    (select_dir / "frozen_attacks.json").write_text(json.dumps(frozen, indent=2) + "\n")
    return frozen
