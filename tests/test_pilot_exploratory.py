"""Exploratory pilot analyses: the decomposition is exact and interactions are direct."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from prompt_injection_eval.pilot import analysis, exploratory

BUNDLE = Path(__file__).resolve().parents[1] / "results-published" / "pilot-2026-11-16"


def _rows(
    rates: dict[tuple[str, str], float], users: int = 21, goals: int = 5, seed: int = 0
) -> list[dict]:
    """First-run attack rows with Bernoulli outcomes at the given (attack, format) rates."""
    rng = np.random.default_rng(seed)
    rows = []
    for (attack, fmt), p in rates.items():
        for u in range(users):
            for g in range(goals):
                key = f"{attack}|{fmt}|{u}|{g}"
                rows.append(
                    {
                        "unit_key": key,
                        "condition": f"attack/{attack}/{fmt}",
                        "status": "completed",
                        "user_task": f"u{u}",
                        "injection_task": f"g{g}",
                        "run": 0,
                        "security": bool(rng.random() < p),
                        "utility": True,
                    }
                )
    return rows


def test_wording_plus_format_equals_the_primary_case_by_case() -> None:
    rows = _rows({("T", "text"): 0.9, ("T", "json"): 0.8, ("J", "text"): 0.6, ("J", "json"): 0.4})
    primary, wording, fmt, interaction = exploratory.decomposition(rows, "T", "J")
    assert primary.estimate == pytest.approx(wording.estimate + fmt.estimate)
    for goal in primary.per_goal:
        assert primary.per_goal[goal] == pytest.approx(wording.per_goal[goal] + fmt.per_goal[goal])
    # Interaction is the difference of the two same-attack format effects.
    t = analysis.contrast(
        "t",
        exploratory.first_runs(rows, "T", "text"),
        exploratory.first_runs(rows, "T", "json"),
        ("a", "b"),
        105,
        1,
        replicates=50,
    )
    j = analysis.contrast(
        "j",
        exploratory.first_runs(rows, "J", "text"),
        exploratory.first_runs(rows, "J", "json"),
        ("a", "b"),
        105,
        1,
        replicates=50,
    )
    assert t is not None and j is not None
    assert interaction.estimate == pytest.approx(t.difference - j.difference)


def test_a_two_term_linear_contrast_matches_the_registered_estimator() -> None:
    rows = _rows({("A", "text"): 0.7, ("A", "json"): 0.5}, seed=3)
    a_text, a_json = (
        exploratory.first_runs(rows, "A", "text"),
        exploratory.first_runs(rows, "A", "json"),
    )
    mine = exploratory.linear_contrast(
        "x", [(1.0, "a", a_text), (-1.0, "b", a_json)], replicates=2000
    )
    registered = analysis.contrast("x", a_text, a_json, ("a", "b"), 105, 1, replicates=2000)
    assert registered is not None
    assert mine.estimate == pytest.approx(registered.difference)
    for ours, theirs in zip(mine.task_interval, registered.task_interval, strict=True):
        assert abs(ours - theirs) < 2.0


def test_no_interaction_is_rarely_called_one() -> None:
    rates = {("T", "text"): 0.8, ("T", "json"): 0.7, ("J", "text"): 0.6, ("J", "json"): 0.5}
    excluded = 0
    for seed in range(60):
        found = exploratory.decomposition(_rows(rates, seed=seed), "T", "J")[3]
        excluded += found.task_interval[0] > 0 or found.task_interval[1] < 0
    assert excluded / 60 <= 0.15


def test_published_decomposition_reproduces_from_traces() -> None:
    pytest.importorskip("agentdojo")
    from prompt_injection_eval.pilot.runner import read_traces

    stored = json.loads((BUNDLE / "exploratory" / "exploratory.json").read_text())
    rows = read_traces(BUNDLE / "qwen3-32b" / "evaluate" / "traces.jsonl")
    primary, wording, fmt, _ = exploratory.decomposition(
        rows, "text_task_update", "neutral_baseline_one_line", "qwen3-32b"
    )
    assert primary.cases == wording.cases == fmt.cases == 105
    assert primary.estimate == pytest.approx(100 * 9 / 105)
    assert wording.estimate == pytest.approx(100 * 7.5 / 105)
    assert fmt.estimate == pytest.approx(100 * 1.5 / 105)
    published = {c["name"]: c for c in stored["contrasts"]["qwen3-32b"]}
    assert published[wording.name]["estimate"] == round(wording.estimate, 2)
    assert published[wording.name]["task_interval"] == [round(v, 2) for v in wording.task_interval]
