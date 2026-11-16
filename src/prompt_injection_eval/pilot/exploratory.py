"""Exploratory analyses of the serialization pilot, written after its outcomes were known.

Nothing here is pre-registered. Each quantity is a linear combination of first-run
condition rates over the same cases, so the registered primary contrast (each format
against its own selected attack) can be decomposed and interactions tested directly
rather than by comparing which separate intervals exclude zero.

For two selected attacks T (selected for text) and J (selected for JSON), with r(a, f)
the first-run attack-success rate of attack a under format f:

    primary              = r(T, text) - r(J, json)
                         = wording + format
    wording  (average)   = [r(T, text) + r(T, json)] / 2 - [r(J, text) + r(J, json)] / 2
    format   (average)   = [r(T, text) - r(T, json)] / 2 + [r(J, text) - r(J, json)] / 2
    interaction          = [r(T, text) - r(T, json)] - [r(J, text) - r(J, json)]

The identity primary = wording + format holds exactly, case by case. Intervals use the
registered estimators (``analysis``): user tasks resampled with goals kept (task), both
resampled (two-way, shown only for width), and a sign-flip test over per-task means.
Cases are first runs only, each pair with equal weight, as in the Amendment 3 primary.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from prompt_injection_eval.pilot.analysis import REPLICATES, SEED, Cells, _sign_flip, cells

Term = tuple[float, Cells]


@dataclass
class LinearContrast:
    name: str
    terms: list[tuple[float, str]]
    cases: int
    estimate: float
    task_interval: tuple[float, float]
    two_way_interval: tuple[float, float]
    sign_flip_p: float
    per_goal: dict[str, float] = field(default_factory=dict)

    def row(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "definition": " ".join(f"{w:+g}×[{label}]" for w, label in self.terms),
            "cases": self.cases,
            "estimate": round(self.estimate, 2),
            "task_interval": [round(v, 2) for v in self.task_interval],
            "two_way_interval": [round(v, 2) for v in self.two_way_interval],
            "sign_flip_p": round(self.sign_flip_p, 4),
            "per_goal": {g: round(v, 2) for g, v in self.per_goal.items()},
        }


def first_runs(
    rows: list[dict[str, Any]], attack: str, fmt: str, outcome: str = "security"
) -> Cells:
    """Run 0 of every completed case under one attack condition."""
    return cells(rows, f"attack/{attack}/{fmt}", outcome, run=0)


def linear_contrast(
    name: str,
    terms: list[tuple[float, str, Cells]],
    replicates: int = REPLICATES,
    seed: int = SEED,
) -> LinearContrast:
    """Sum of weighted condition rates over the cases complete in every term, in points.

    Each case contributes ``sum(w * y)`` with ``y`` its first-run outcome under that term.
    Terms may come from different models: cases are matched by (user task, goal).
    """
    cases = sorted(set.intersection(*(set(c) for _, _, c in terms)))
    if not cases:
        raise ValueError(f"{name}: no case is complete in every term.")
    for _, label, found in terms:
        if any(len(found[c]) != 1 for c in cases):
            raise ValueError(f"{name}: {label} must hold exactly one run per case.")
    value = np.zeros(len(cases))
    for weight, _, found in terms:
        value += weight * np.array([found[c][0] for c in cases])
    users = sorted({u for u, _ in cases})
    goals = sorted({g for _, g in cases})
    user_of = np.array([users.index(u) for u, _ in cases])
    goal_of = np.array([goals.index(g) for _, g in cases])
    rng = np.random.default_rng(seed)

    def interval(two_way: bool) -> tuple[float, float]:
        estimates = np.empty(replicates)
        for i in range(replicates):
            weight = rng.multinomial(len(users), np.full(len(users), 1 / len(users)))[
                user_of
            ].astype(float)
            if two_way:
                weight *= rng.multinomial(len(goals), np.full(len(goals), 1 / len(goals)))[goal_of]
            estimates[i] = (weight * value).sum() / weight.sum() if weight.sum() else np.nan
        low, high = np.nanpercentile(estimates, [2.5, 97.5])
        return float(100 * low), float(100 * high)

    per_task = np.array([value[user_of == i].mean() for i in range(len(users))])
    return LinearContrast(
        name=name,
        terms=[(w, label) for w, label, _ in terms],
        cases=len(cases),
        estimate=float(100 * value.mean()),
        task_interval=interval(False),
        two_way_interval=interval(True),
        sign_flip_p=_sign_flip(per_task, rng),
        per_goal={g: float(100 * value[goal_of == j].mean()) for j, g in enumerate(goals)},
    )


def decomposition(
    rows: list[dict[str, Any]], text_attack: str, json_attack: str, model: str = ""
) -> list[LinearContrast]:
    """The primary contrast split into average wording and average format components."""
    prefix = f"{model}: " if model else ""
    t_text = first_runs(rows, text_attack, "text")
    t_json = first_runs(rows, text_attack, "json")
    j_text = first_runs(rows, json_attack, "text")
    j_json = first_runs(rows, json_attack, "json")
    lt, lj = f"{text_attack}", f"{json_attack}"
    return [
        linear_contrast(
            f"{prefix}primary (registered): {lt} on text minus {lj} on JSON",
            [(1.0, f"{lt}/text", t_text), (-1.0, f"{lj}/json", j_json)],
        ),
        linear_contrast(
            f"{prefix}wording component: mean over formats of {lt} minus {lj}",
            [
                (0.5, f"{lt}/text", t_text),
                (0.5, f"{lt}/json", t_json),
                (-0.5, f"{lj}/text", j_text),
                (-0.5, f"{lj}/json", j_json),
            ],
        ),
        linear_contrast(
            f"{prefix}format component: mean over the two selected attacks of text minus JSON",
            [
                (0.5, f"{lt}/text", t_text),
                (-0.5, f"{lt}/json", t_json),
                (0.5, f"{lj}/text", j_text),
                (-0.5, f"{lj}/json", j_json),
            ],
        ),
        linear_contrast(
            f"{prefix}interaction: format effect under {lt} minus under {lj}",
            [
                (1.0, f"{lt}/text", t_text),
                (-1.0, f"{lt}/json", t_json),
                (-1.0, f"{lj}/text", j_text),
                (1.0, f"{lj}/json", j_json),
            ],
        ),
    ]


def format_interaction(
    rows: list[dict[str, Any]], attack_a: str, attack_b: str, model: str = ""
) -> LinearContrast:
    """Whether the same-attack format contrast differs between two attacks."""
    prefix = f"{model}: " if model else ""
    return linear_contrast(
        f"{prefix}interaction: format effect under {attack_a} minus under {attack_b}",
        [
            (1.0, f"{attack_a}/text", first_runs(rows, attack_a, "text")),
            (-1.0, f"{attack_a}/json", first_runs(rows, attack_a, "json")),
            (-1.0, f"{attack_b}/text", first_runs(rows, attack_b, "text")),
            (1.0, f"{attack_b}/json", first_runs(rows, attack_b, "json")),
        ],
    )


def mean_format_effect(
    rows: list[dict[str, Any]], attack_list: list[str], model: str = ""
) -> LinearContrast:
    """Text minus JSON averaged with equal weight over the listed attacks."""
    prefix = f"{model}: " if model else ""
    w = 1.0 / len(attack_list)
    terms: list[tuple[float, str, Cells]] = []
    for a in attack_list:
        terms.append((w, f"{a}/text", first_runs(rows, a, "text")))
        terms.append((-w, f"{a}/json", first_runs(rows, a, "json")))
    return linear_contrast(
        f"{prefix}same-attack format effect averaged over {', '.join(attack_list)}", terms
    )


def cross_model_format_difference(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    attack_a: str,
    attack_b: str,
    labels: tuple[str, str],
) -> LinearContrast:
    """(text − JSON) for model A under one attack minus the same for model B.

    The two models ran the same Slack pairs, so cases are matched and resampled jointly.
    """
    return linear_contrast(
        f"cross-model: format effect of {labels[0]} ({attack_a}) minus {labels[1]} ({attack_b})",
        [
            (1.0, f"{labels[0]} {attack_a}/text", first_runs(rows_a, attack_a, "text")),
            (-1.0, f"{labels[0]} {attack_a}/json", first_runs(rows_a, attack_a, "json")),
            (-1.0, f"{labels[1]} {attack_b}/text", first_runs(rows_b, attack_b, "text")),
            (1.0, f"{labels[1]} {attack_b}/json", first_runs(rows_b, attack_b, "json")),
        ],
    )


def goal_rates(
    rows: list[dict[str, Any]], attack_list: list[str], outcome: str = "security"
) -> list[dict[str, Any]]:
    """First-run success per attacker goal and condition: successes / cases."""
    out: list[dict[str, Any]] = []
    for attack in attack_list:
        for fmt in ("text", "json"):
            found = first_runs(rows, attack, fmt, outcome)
            by_goal: dict[str, list[float]] = defaultdict(list)
            for (_, goal), values in found.items():
                by_goal[goal].append(values[0])
            for goal in sorted(by_goal):
                v = by_goal[goal]
                out.append(
                    {
                        "attack": attack,
                        "format": fmt,
                        "goal": goal,
                        "successes": int(sum(v)),
                        "cases": len(v),
                        "rate": round(100 * sum(v) / len(v), 1),
                    }
                )
    return out


def _clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval by bisection on the binomial tails (no scipy)."""
    from math import comb

    def cdf(x: int, p: float) -> float:
        return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(x + 1))

    def solve(pred: Any) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if pred(mid) else (mid, hi)
        return (lo + hi) / 2

    low = 0.0 if k == 0 else solve(lambda p: 1 - cdf(k - 1, p) >= alpha / 2)
    high = 1.0 if k == n else solve(lambda p: cdf(k, p) <= alpha / 2)
    return low, high


def clustered_repeatability(
    rows: list[dict[str, Any]],
    outcome: str = "security",
    replicates: int = REPLICATES,
    seed: int = SEED,
) -> dict[str, Any]:
    """Repeat disagreement with the dependence between cells of one pair made explicit.

    A repeated pair contributes one cell per evaluated condition, and those cells share
    the user task, the goal and (in this pilot) adjacent positions in the run order. The
    registered table counts cells as if independent; its exact binomial interval is exact
    only under that assumption. This adds: the pair-level count (pairs with any
    disagreeing cell, with an exact interval over pairs, which are closer to independent:
    one per user task), and a cluster bootstrap of the cell-level share that resamples
    pairs. Goals recur across pairs (five goals), which neither accounts for.
    """
    from prompt_injection_eval.pilot.analysis import latest

    runs: dict[tuple[str, str, str], dict[int, bool]] = defaultdict(dict)
    for row in latest(rows).values():
        if (
            row["status"] == "completed"
            and row.get(outcome) is not None
            and row["mode"] == "attack"
        ):
            runs[(row["user_task"], row["injection_task"], row["condition"])][int(row["run"])] = (
                bool(row[outcome])
            )
    by_pair: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for (user, goal, _), found in runs.items():
        if len(found) >= 3:
            by_pair[(user, goal)].append(len(set(found.values())) > 1)
    pairs = sorted(by_pair)
    disagree = np.array([sum(by_pair[p]) for p in pairs], dtype=float)
    cells_n = np.array([len(by_pair[p]) for p in pairs], dtype=float)
    k_cells, n_cells = int(disagree.sum()), int(cells_n.sum())
    k_pairs = int((disagree > 0).sum())
    rng = np.random.default_rng(seed)
    shares = np.empty(replicates)
    for i in range(replicates):
        pick = rng.integers(0, len(pairs), len(pairs))
        shares[i] = disagree[pick].sum() / cells_n[pick].sum()
    low, high = np.percentile(shares, [2.5, 97.5])
    cell_low, cell_high = _clopper_pearson(k_cells, n_cells) if n_cells else (np.nan, np.nan)
    pair_low, pair_high = _clopper_pearson(k_pairs, len(pairs)) if pairs else (np.nan, np.nan)
    return {
        "outcome": outcome,
        "repeated_pairs": len(pairs),
        "repeated_cells": n_cells,
        "disagreeing_cells": k_cells,
        "cell_share_pct": round(100 * k_cells / n_cells, 2) if n_cells else None,
        "cell_exact_interval_if_independent_pct": [
            round(100 * cell_low, 1),
            round(100 * cell_high, 1),
        ],
        "cell_share_pair_bootstrap_pct": [round(100 * low, 1), round(100 * high, 1)],
        "pairs_with_any_disagreement": k_pairs,
        "pair_share_exact_interval_pct": [round(100 * pair_low, 1), round(100 * pair_high, 1)],
        "disagreeing_cells_per_pair": sorted((int(d) for d in disagree if d), reverse=True),
    }
