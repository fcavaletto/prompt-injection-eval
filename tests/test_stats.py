"""Exact McNemar, power, bootstrap, Holm, and the paired-test plumbing."""

from __future__ import annotations

import math

import pytest

from prompt_injection_eval.stats import (
    defense_tests,
    holm,
    mcnemar_exact,
    mcnemar_power,
    model_tests,
    paired_bootstrap,
    paired_test,
    power_table,
    smallest_significant_split,
)


def test_mcnemar_known_values() -> None:
    # 4 vs 0: 2 * 0.5**4
    assert mcnemar_exact(4, 0)["p_value"] == pytest.approx(0.125)
    assert mcnemar_exact(0, 4)["p_value"] == pytest.approx(0.125)
    # 6 vs 0: 2 * 0.5**6
    assert mcnemar_exact(6, 0)["p_value"] == pytest.approx(0.03125)
    # 8 vs 2: 2 * P(X <= 2), X ~ Bin(10, 0.5) = 2 * 56/1024
    assert mcnemar_exact(8, 2)["p_value"] == pytest.approx(2 * 56 / 1024)
    assert mcnemar_exact(3, 3)["p_value"] == 1.0
    assert mcnemar_exact(0, 0)["p_value"] == 1.0
    with pytest.raises(ValueError):
        mcnemar_exact(-1, 2)


def test_six_pairs_are_needed_at_alpha_005() -> None:
    assert smallest_significant_split(0.05) == 6
    assert mcnemar_exact(5, 0)["p_value"] > 0.05


def test_power_edges() -> None:
    assert mcnemar_power(36, 0.0, 0.0) == 0.0
    assert mcnemar_power(36, 0.03, 0.0) < 0.05
    assert mcnemar_power(200, 0.3, 0.0) > 0.99
    # More pairs, same effect: never less power by much (exact tests are a little jagged).
    assert mcnemar_power(89, 0.15, 0.0) > mcnemar_power(36, 0.15, 0.0)
    with pytest.raises(ValueError):
        mcnemar_power(10, 0.7, 0.5)


def test_power_matches_simulation() -> None:
    import random

    rng = random.Random(1)
    n, p_b, p_c = 40, 0.2, 0.02
    hits = 0
    trials = 4000
    for _ in range(trials):
        b = c = 0
        for _case in range(n):
            u = rng.random()
            if u < p_b:
                b += 1
            elif u < p_b + p_c:
                c += 1
        hits += mcnemar_exact(b, c)["p_value"] <= 0.05
    assert math.isclose(hits / trials, mcnemar_power(n, p_b, p_c), abs_tol=0.03)


def test_bootstrap_is_seeded_and_brackets_the_difference() -> None:
    first = [1] * 9 + [0] * 27
    second = [1] * 3 + [0] * 33
    one = paired_bootstrap(first, second, reps=2000)
    two = paired_bootstrap(first, second, reps=2000)
    assert one == two
    assert one["difference"] == pytest.approx(-6 / 36)
    assert one["low"] <= one["difference"] <= one["high"]
    assert one["high"] <= 0.0
    with pytest.raises(ValueError):
        paired_bootstrap([1], [1, 0])


def test_holm() -> None:
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([]) == []
    assert holm([0.9, 0.5]) == pytest.approx([1.0, 1.0])
    assert holm([0.2, 0.01]) == pytest.approx([0.2, 0.02])


def _row(model: str, case: str, condition: str, attack: str, task: str, **extra: object) -> dict:
    return {
        "model": model,
        "case_id": case,
        "condition": condition,
        "attack_score": attack,
        "task_score": task,
        "is_attack": True,
        "outcome": "compromised" if attack == "success" else "secure_and_useful",
        "error_type": None,
        **extra,
    }


def test_paired_test_counts_and_excludes_errors() -> None:
    pairs = [
        (
            _row("m", "a", "baseline", "success", "failure"),
            _row("m", "a", "defended", "failure", "success"),
        ),
        (
            _row("m", "b", "baseline", "uncertain", "success"),
            _row("m", "b", "defended", "failure", "success"),
        ),
        (
            _row("m", "c", "baseline", "failure", "success"),
            _row("m", "c", "defended", "failure", "success"),
        ),
        (
            _row("m", "d", "baseline", "success", "success"),
            _row("m", "d", "defended", "failure", "success", error_type="timeout"),
        ),
    ]
    strict = paired_test(pairs, field="attack_score")
    assert (strict["pairs"], strict["excluded_backend_errors"]) == (3, 1)
    assert (strict["only_first"], strict["only_second"], strict["neither"]) == (1, 0, 2)
    loose = paired_test(pairs, field="attack_score", uncertain_as=1)
    assert loose["only_first"] == 2


def test_defense_and_model_tests_stay_within_model() -> None:
    rows = []
    for case in ("a", "b", "c"):
        rows.append(_row("m1", case, "baseline", "success", "failure"))
        rows.append(_row("m1", case, "defended", "failure", "success"))
        rows.append(_row("m2", case, "baseline", "failure", "success"))
        rows.append(_row("m2", case, "defended", "failure", "success"))
    tests = defense_tests(rows)
    m1 = next(
        item
        for item in tests
        if item["model"] == "m1"
        and item["field"] == "attack_score"
        and item["uncertain_counted_as"] == "not success"
    )
    assert (m1["only_first"], m1["only_second"]) == (3, 0)
    assert all("holm_p_value" in item for item in tests)
    contrasts = model_tests(rows)
    baseline = next(item for item in contrasts if item["condition"] == "baseline")
    assert (baseline["first_model"], baseline["second_model"]) == ("m1", "m2")
    assert (baseline["only_first"], baseline["only_second"]) == (3, 0)


def test_power_table_shape() -> None:
    table = power_table(89)
    assert {row["p_c"] for row in table} == {0.0, 0.02}
    assert all(0.0 <= row["power"] <= 1.0 for row in table)
