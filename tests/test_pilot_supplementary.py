"""Supplementary (exploratory) pilot tables: definitions, denominators and published figures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_injection_eval.pilot import attacks, exploratory, supplementary
from prompt_injection_eval.pilot.runner import read_traces

BUNDLE = Path(__file__).resolve().parents[1] / "results-published" / "pilot-2026-11-16"
OUT = BUNDLE / "supplementary-2026-11-17"


def _row(attack, fmt, user, goal, security, run=0, limit=False, utility=True, payload="x"):
    return {
        "unit_key": f"{attack}|{fmt}|{user}|{goal}|{run}",
        "mode": "attack",
        "attack": attack,
        "fmt": fmt,
        "condition": f"attack/{attack}/{fmt}",
        "status": "completed",
        "user_task": user,
        "injection_task": goal,
        "run": run,
        "security": security,
        "utility": utility,
        "success": None,
        "payload": payload,
        "prefix_calls": [],
        "messages": [],
        "turns": [{"prompt_tokens": 10}],
        "totals": {
            "model_calls": 16 if limit else 2,
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "hit_round_limit": limit,
            "truncated_turns": 0,
            "schema_rejections": 0,
        },
    }


def test_multiline_is_judged_on_the_stripped_payload() -> None:
    assert supplementary.is_multiline("a\nb")
    assert not supplementary.is_multiline("\n\n one line \n\n")
    rendered = {c.id: c.render("GOAL") for c in attacks.LIBRARY}
    assert not supplementary.is_multiline(rendered["json_field_mimic"])
    assert not supplementary.is_multiline(rendered["neutral_baseline_one_line"])
    assert supplementary.is_multiline(rendered["text_fake_turn"])


def test_groups_list_json_field_mimic_with_and_without() -> None:
    shapes = {
        "a": {"multiline": True},
        "json_field_mimic": {"multiline": False},
        "b": {"multiline": False},
    }
    g = supplementary.groups(shapes)
    assert g["multiline"] == ["a"]
    assert g["one_line"] == ["json_field_mimic", "b"]
    assert g["one_line_without_json_field_mimic"] == ["b"]


def test_round_limit_episodes_stay_in_the_denominator() -> None:
    rows = [
        _row("A", "text", "u0", "g0", True, limit=True),
        _row("A", "text", "u1", "g0", False),
        _row("A", "text", "u1", "g0", True, run=1),
    ]
    first = supplementary.budget(rows, "m", "p", first_run_only=True)[0]
    every = supplementary.budget(rows, "m", "p", first_run_only=False)[0]
    assert (
        first["episodes"],
        first["round_limit"],
        first["round_limit_with_positive_outcome"],
    ) == (
        2,
        1,
        1,
    )
    assert every["episodes"] == 3  # all-runs denominator is separate and larger
    assert first["denominator"] != every["denominator"]


def test_superseded_traces_never_count_as_outcomes() -> None:
    stale = _row("A", "text", "u0", "g0", None) | {"status": "infra_error"}
    fresh = _row("A", "text", "u0", "g0", True)
    assert supplementary._count([stale, fresh], "A", "text", "security", 0) == (1, 1)


def test_twin_check_compares_words_not_bytes() -> None:
    rows = [
        _row(attacks.BASELINE, "text", "u", "g", True, payload="\n\nHello\n\nworld\n"),
        _row(supplementary.ONE_LINE_TWIN, "text", "u", "g", True, payload="Hello world"),
    ]
    check = supplementary.twin_payload_check(rows)
    assert check["equal_after_whitespace_normalization"] == 1
    assert check["byte_identical"] == 0


# Against the published bundle -----------------------------------------------------------


@pytest.fixture(scope="module")
def granite_select() -> list[dict]:
    return read_traces(BUNDLE / "granite-4.0-h-small" / "select" / "traces.jsonl")


def test_published_banking_counts(granite_select: list[dict]) -> None:
    count = supplementary._count
    assert count(granite_select, attacks.BASELINE, "text", "security", 0) == (47, 72)
    assert count(granite_select, attacks.BASELINE, "json", "security", 0) == (35, 72)
    assert count(granite_select, supplementary.ONE_LINE_TWIN, "text", "security", 0) == (20, 72)
    assert count(granite_select, supplementary.ONE_LINE_TWIN, "json", "security", 0) == (28, 72)
    check = supplementary.twin_payload_check(granite_select)
    assert check["matched_cases"] == check["equal_after_whitespace_normalization"] == 144


def test_registered_qwen_decomposition_is_unchanged() -> None:
    rows = read_traces(BUNDLE / "qwen3-32b" / "evaluate" / "traces.jsonl")
    primary, wording, fmt, _ = exploratory.decomposition(
        rows, "text_task_update", "neutral_baseline_one_line"
    )
    assert primary.estimate == pytest.approx(8.5714, abs=1e-3)
    assert wording.estimate == pytest.approx(7.1429, abs=1e-3)
    assert fmt.estimate == pytest.approx(1.4286, abs=1e-3)


def test_stored_supplementary_output_passes_its_checks() -> None:
    stored = json.loads((OUT / "analysis.json").read_text())
    assert all(v["match"] for v in stored["reproduction_checks"].values())
    assert stored["status"].startswith("exploratory")
