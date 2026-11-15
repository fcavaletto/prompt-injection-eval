"""The analysis recovers planted effects on simulated data with shared tasks and goals."""

from __future__ import annotations

import numpy as np

from prompt_injection_eval.pilot import analysis

USERS, GOALS, RUNS = 21, 5, 3
EFFECT, FLIP = 0.20, 0.05
TRUTH = 100 * EFFECT * (1 - 2 * FLIP)  # run-level flips shrink the difference symmetrically


def _one(seed: int, effect: float = EFFECT) -> analysis.Contrast:
    first, second = analysis.simulate(
        USERS,
        GOALS,
        RUNS,
        base=0.45,
        effect=effect,
        sd_user=0.12,
        sd_goal=0.08,
        seed=seed,
        flip=FLIP,
    )
    found = analysis.contrast(
        "sim", first, second, ("a", "b"), USERS * GOALS, RUNS, replicates=400, seed=seed
    )
    assert found is not None
    return found


def test_estimator_is_unbiased_and_the_task_interval_covers() -> None:
    found = [_one(seed) for seed in range(150)]
    estimates = np.array([c.difference for c in found])
    assert abs(estimates.mean() - TRUTH) < 1.5
    covered = np.mean([c.task_interval[0] <= TRUTH <= c.task_interval[1] for c in found])
    # A percentile bootstrap over 21 tasks runs a little under its nominal 95%.
    assert covered >= 0.87
    wider = np.mean(
        [
            c.two_way_interval[1] - c.two_way_interval[0] >= c.task_interval[1] - c.task_interval[0]
            for c in found
        ]
    )
    assert wider >= 0.8


def test_no_effect_is_rarely_called_an_effect() -> None:
    found = [_one(seed, effect=0.0) for seed in range(150)]
    assert abs(np.mean([c.difference for c in found])) < 1.5
    false_alarms = np.mean([c.sign_flip_p < 0.05 for c in found])
    assert false_alarms <= 0.10
    excluded = np.mean([c.task_interval[0] > 0 or c.task_interval[1] < 0 for c in found])
    assert excluded <= 0.13


def test_incomplete_cases_are_bounded_and_flagged_not_dropped_silently() -> None:
    first, second = analysis.simulate(USERS, GOALS, RUNS, 0.45, EFFECT, 0.12, 0.08, seed=7)
    planned = USERS * GOALS
    complete = analysis.contrast("all", first, second, ("a", "b"), planned, RUNS, replicates=200)
    assert complete is not None and complete.interpretable and complete.invalid_share == 0
    assert complete.bound_low == complete.bound_high == complete.difference
    # Ten cases lose a run in one condition: they leave the estimate and enter the bounds.
    for case in list(first)[:10]:
        first[case] = first[case][:2]
    partial = analysis.contrast("partial", first, second, ("a", "b"), planned, RUNS, replicates=200)
    assert partial is not None and partial.cases == planned - 10
    assert not partial.interpretable and partial.invalid_share > analysis.INVALID_LIMIT
    assert partial.bound_low < partial.difference < partial.bound_high
    assert abs((partial.bound_high - partial.bound_low) - 2 * 100 * 10 / planned) < 1e-9


def test_sign_convention_is_first_minus_second() -> None:
    first = {("u0", "g0"): [1.0, 1.0, 1.0], ("u1", "g0"): [1.0, 1.0, 1.0]}
    second = {("u0", "g0"): [0.0, 0.0, 0.0], ("u1", "g0"): [1.0, 1.0, 1.0]}
    found = analysis.contrast("sign", first, second, ("text", "json"), 2, 3, replicates=50)
    assert found is not None and found.difference == 50.0
    assert found.rate_first == 100.0 and found.rate_second == 50.0
