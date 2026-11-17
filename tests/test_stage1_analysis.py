"""Stage 1 runner, analysis and per-round rescoring: fixtures and archived traces, offline."""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("agentdojo")

from prompt_injection_eval.pilot import episode, rescore, runner, stage1  # noqa: E402
from prompt_injection_eval.pilot import stage1_analysis as sa  # noqa: E402
from prompt_injection_eval.pilot.analysis import latest  # noqa: E402
from prompt_injection_eval.pilot.scripted import ScriptedProvider  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GRANITE = ROOT / "results-published" / "pilot-2026-11-16" / "granite-4.0-h-small"


def _quiet(fn, *args):  # noqa: ANN001, ANN202 - some AgentDojo tools print
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args)


def _synthetic(rates: dict[tuple[str, int], float], seed: int = 0) -> list[dict]:
    """Two batches over the frozen pairs; outcome probability per (attack, condition)."""
    rng = np.random.default_rng(seed)
    rows = []
    for suite, found in stage1.pairs().items():
        for user, goal in found:
            for (attack, number), p in rates.items():
                for batch in (0, 1):
                    fmt = sa.C[number]
                    rows.append(
                        {
                            "unit_key": f"{suite}{user}{goal}{attack}{fmt}{batch}",
                            "mode": "attack",
                            "status": "completed",
                            "suite": suite,
                            "user_task": user,
                            "injection_task": goal,
                            "attack": attack,
                            "fmt": fmt,
                            "run": batch,
                            "security": bool(rng.random() < p),
                        }
                    )
    return rows


def test_batches_are_averaged_within_pairs_not_counted_as_new_pairs() -> None:
    rates = {(a, c): 0.5 for a in (sa.MULTI, sa.ONE) for c in sa.C}
    estimates = sa.contrasts(_synthetic(rates))
    assert all(e.cases == 24 and e.planned_cases == 24 for e in estimates)
    assert all(set(e.batch_estimates) == {0, 1} for e in estimates)


def test_a_planted_interaction_is_recovered_and_covered() -> None:
    rates = {(a, c): 0.4 for a in (sa.MULTI, sa.ONE) for c in sa.C}
    rates[(sa.MULTI, 1)] = 0.9  # multiline text +50 over multiline JSON; one-line unchanged
    covered = 0
    for seed in range(20):
        p1 = next(e for e in sa.contrasts(_synthetic(rates, seed)) if e.name.startswith("P1"))
        assert p1.estimate is not None and p1.interval is not None
        covered += p1.interval[0] <= 50 <= p1.interval[1]
    assert covered >= 16  # nominal 95%; 24 clusters, so allow some undercoverage


def test_analysis_reproduces_the_supplementary_twin_interaction() -> None:
    rows = runner.read_traces(GRANITE / "select" / "traces.jsonl")
    found = {e.name[:2]: e for e in sa.contrasts(rows, planned_cases=72, batches=(0,))}
    assert found["P1"].estimate == pytest.approx(27.78, abs=0.01)
    assert found["S2"].estimate == pytest.approx(-11.11, abs=0.01)
    lo, hi = found["P1"].interval
    assert 10 < lo < 15 and 40 < hi < 47  # task bootstrap in the supplementary: +12.3, +44.0


def test_progression_does_not_turn_on_significance_alone() -> None:
    rates = {(a, c): 0.5 for a in (sa.MULTI, sa.ONE) for c in sa.C}
    rows = _synthetic(rates)
    estimates = sa.contrasts(rows)
    util = [{"tasks": 27, "within_gap_limit": False}]  # a benign control failing
    out = sa.progression(estimates, util, {"cell_share": 0.0}, [], delivery_verified=True)
    assert out["progress_to_adaptive_proposal"] is False
    out = sa.progression(
        estimates, [{"tasks": 27, "within_gap_limit": True}], {"cell_share": 0.2}, [], True
    )
    assert out["progress_to_adaptive_proposal"] is False  # unstable instrument
    assert "launches nothing" in out["note"]


# Rescoring ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def granite_slack() -> list[dict]:
    return list(latest(runner.read_traces(GRANITE / "evaluate" / "traces.jsonl")).values())


def test_round_limited_episodes_replay_without_their_unexecuted_last_calls(granite_slack) -> None:
    limited = [r for r in granite_slack if r["totals"]["hit_round_limit"]][:10]
    for r in limited:
        out = _quiet(rescore.replay, r)
        assert out.verified, out.reason
        assert out.per_round[-1] == out.per_round[-2]  # the 16th response changed no state
        assert rescore.censoring(out) != "unverified"


def test_trace_scored_goal_where_the_archive_counted_unexecuted_calls(granite_slack) -> None:
    cases = [
        r
        for r in granite_slack
        if r["pair"] == "user_task_7|injection_task_5"
        and r["condition"] == "attack/text_fake_turn/text"
    ]
    assert len(cases) == 3
    for r in cases:
        out = _quiet(rescore.replay, r)
        assert out.verified and out.archived_agrees is False
        assert r["security"] is False and out.per_round[-1] is True


def test_a_tampered_trace_does_not_verify(granite_slack) -> None:
    changing = ("send_direct_message", "send_channel_message", "post_webpage")
    r = copy.deepcopy(
        next(
            x
            for x in granite_slack
            if any(c["name"] in changing for t in x["turns"] for c in t["calls"])
        )
    )
    assert _quiet(rescore.replay, r).verified
    call = next(c for t in r["turns"] for c in t["calls"] if c["name"] in changing)
    key = "content" if call["name"] == "post_webpage" else "body"
    call["arguments"] = {**call["arguments"], key: "tampered"}
    out = _quiet(rescore.replay, r)
    assert out.verified is False and "final state" in (out.reason or "")


def test_new_runs_score_executed_calls_only_without_changing_pilot_fingerprints() -> None:
    spec = episode.Spec("slack", "attack", "text", "user_task_7", "injection_task_5", "baseline", 0)
    plain = episode.Settings(model="m", label="l")
    assert episode.fingerprint(spec, plain) != episode.fingerprint(
        spec, episode.Settings(model="m", label="l", score_executed_calls_only=True)
    )


# Runner and report -------------------------------------------------------------------


def test_run_and_report_end_to_end_offline(tmp_path: Path) -> None:
    from prompt_injection_eval.pilot.stage1_cli import report, settings

    units = stage1.schedule(0)[:24]
    out_dir = tmp_path / "batch-0"
    summary = _quiet(
        runner.run_phase,
        "stage1-batch-0",
        ScriptedProvider("obedient"),
        settings("scripted", "scripted", "scripted"),
        out_dir,
        None,
        1,
        None,
        None,
        False,
        units,
    )
    assert summary.statuses == {"completed": 24}
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["study"] == stage1.STAGE and manifest["settings"]["score_executed_calls_only"]
    # Resume runs nothing new.
    again = _quiet(
        runner.run_phase,
        "stage1-batch-0",
        ScriptedProvider("obedient"),
        settings("scripted", "scripted", "scripted"),
        out_dir,
        None,
        1,
        None,
        None,
        False,
        units,
    )
    assert again.written == 0 and again.already_done == 24
    result = report([out_dir], tmp_path / "report")
    assert result["accounting"]["planned"] == 858
    assert result["accounting"]["by_status"]["completed"] == 24
    assert result["delivery"]["every_scored_request_passed_contract_check"]
    assert set(result["progression"]["rules"]) and (tmp_path / "report" / "report.md").exists()
