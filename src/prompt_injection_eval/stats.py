"""Paired tests, a paired bootstrap, and power for the defense and model comparisons.

Every comparison in this study is paired: the same case is run under two conditions, or
by two models. A paired test looks only at the cases where the two sides disagree. If
baseline was compromised and the defense was not, that is one discordant pair in the
defense's favour (b). The reverse is one against it (c). Cases where both sides agree say
nothing about the difference and drop out.

McNemar's exact test asks: if the two conditions were really equally likely to be
compromised, how surprising is a split of b against c? Under that null hypothesis each
discordant pair is a fair coin, so b follows Binomial(b + c, 1/2). The two-sided p-value
is the probability of a split at least as lopsided as the one observed.

What it does not answer: how large the effect is (use the bootstrap interval), whether it
holds on other documents (the cases were written by hand, not sampled), or whether the
defense is a security boundary (it is not).
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from prompt_injection_eval.metrics import wilson_interval


def binom_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * p**k * (1.0 - p) ** (n - k)


def mcnemar_exact(b: int, c: int) -> dict[str, Any]:
    """Exact two-sided McNemar test on discordant counts b and c."""
    if b < 0 or c < 0:
        raise ValueError("discordant counts must be non-negative")
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "discordant": 0, "p_value": 1.0}
    k = min(b, c)
    tail = sum(binom_pmf(i, n, 0.5) for i in range(k + 1))
    return {"b": b, "c": c, "discordant": n, "p_value": min(1.0, 2.0 * tail)}


def smallest_significant_split(alpha: float = 0.05) -> int:
    """Fewest discordant pairs, all in one direction, that reach p <= alpha.

    With alpha 0.05 this is 6: five pairs all favouring the defense give p = 0.0625.
    """
    n = 1
    while mcnemar_exact(n, 0)["p_value"] > alpha:
        n += 1
    return n


def mcnemar_power(n_pairs: int, p_b: float, p_c: float, *, alpha: float = 0.05) -> float:
    """Exact power of the two-sided McNemar test.

    p_b and p_c are the per-case probabilities of the two kinds of discordant pair.
    The number of discordant pairs is Binomial(n, p_b + p_c); given that number, b is
    Binomial(d, p_b / (p_b + p_c)). Power is the probability the test rejects.
    """
    if not 0.0 <= p_b <= 1.0 or not 0.0 <= p_c <= 1.0 or p_b + p_c > 1.0:
        raise ValueError("p_b and p_c must be probabilities with p_b + p_c <= 1")
    p_disc = p_b + p_c
    if p_disc == 0.0:
        return 0.0
    share = p_b / p_disc
    reject = {d: _rejection_set(d, alpha) for d in range(n_pairs + 1)}
    power = 0.0
    for d in range(n_pairs + 1):
        weight = binom_pmf(d, n_pairs, p_disc)
        if weight == 0.0 or not reject[d]:
            continue
        power += weight * sum(binom_pmf(b, d, share) for b in reject[d])
    return min(1.0, power)


def _rejection_set(d: int, alpha: float) -> list[int]:
    return [b for b in range(d + 1) if mcnemar_exact(b, d - b)["p_value"] <= alpha]


def paired_bootstrap(
    first: Sequence[int],
    second: Sequence[int],
    *,
    reps: int = 10_000,
    seed: int = 20261104,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Percentile bootstrap of mean(second) - mean(first), resampling cases.

    Each case keeps its pair together. With few discordant pairs the bootstrap
    distribution is lumpy and the interval should be read as rough.
    """
    if len(first) != len(second):
        raise ValueError("paired samples must have the same length")
    n = len(first)
    if n == 0:
        return {"difference": None, "low": None, "high": None, "reps": reps, "seed": seed}
    diffs = [y - x for x, y in zip(first, second, strict=True)]
    rng = random.Random(seed)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    tail = (1.0 - confidence) / 2.0
    low = means[int(math.floor(tail * (reps - 1)))]
    high = means[int(math.ceil((1.0 - tail) * (reps - 1)))]
    return {
        "difference": sum(diffs) / n,
        "low": low,
        "high": high,
        "reps": reps,
        "seed": seed,
    }


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjustment. Controls the chance of any false positive in a family."""
    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    m = len(p_values)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def _indicator(row: dict[str, Any], field: str, *, uncertain_as: int) -> int:
    label = row.get(field)
    if label == "success":
        return 1
    if label == "uncertain":
        return uncertain_as
    return 0


def _errored(row: dict[str, Any]) -> bool:
    return row.get("outcome") == "backend_error" or bool(row.get("error_type"))


def paired_test(
    pairs: Iterable[tuple[dict[str, Any], dict[str, Any]]],
    *,
    field: str,
    uncertain_as: int = 0,
) -> dict[str, Any]:
    """2x2 table, McNemar, and bootstrap for one binary field over paired rows.

    `first` is the reference side (baseline, or the first model). A positive difference
    means the second side has the higher rate.
    """
    first: list[int] = []
    second: list[int] = []
    excluded = 0
    for left, right in pairs:
        if _errored(left) or _errored(right):
            excluded += 1
            continue
        first.append(_indicator(left, field, uncertain_as=uncertain_as))
        second.append(_indicator(right, field, uncertain_as=uncertain_as))
    both = sum(1 for x, y in zip(first, second, strict=True) if x and y)
    only_first = sum(1 for x, y in zip(first, second, strict=True) if x and not y)
    only_second = sum(1 for x, y in zip(first, second, strict=True) if y and not x)
    neither = len(first) - both - only_first - only_second
    n = len(first)
    return {
        "field": field,
        "uncertain_counted_as": "success" if uncertain_as else "not success",
        "pairs": n,
        "excluded_backend_errors": excluded,
        "first_successes": sum(first),
        "second_successes": sum(second),
        "first_rate": sum(first) / n if n else None,
        "second_rate": sum(second) / n if n else None,
        "both": both,
        "only_first": only_first,
        "only_second": only_second,
        "neither": neither,
        "mcnemar": mcnemar_exact(only_first, only_second),
        "bootstrap": paired_bootstrap(first, second),
    }


def _index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (str(row.get("model")), str(row.get("case_id")), str(row.get("condition"))): row
        for row in rows
    }


CONDITION_CONTRASTS = (
    ("baseline", "defended"),
    ("baseline", "spotlight"),
    ("defended", "spotlight"),
)


def defense_tests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each pair of conditions within each model, on attack and task success.

    Baseline against each defense answers "does the defense help"; defended against
    spotlight answers "does datamarking add anything over the generic rule".
    """
    index = _index(rows)
    models = sorted({key[0] for key in index})
    results: list[dict[str, Any]] = []
    for model in models:
        for reference, other in CONDITION_CONTRASTS:
            for field, attack_only in (("attack_score", True), ("task_score", False)):
                pairs = [
                    (index[(model, case, reference)], index[(model, case, other)])
                    for (m, case, condition) in index
                    if m == model
                    and condition == reference
                    and (model, case, other) in index
                    and (not attack_only or bool(index[(m, case, condition)].get("is_attack")))
                ]
                if not pairs:
                    continue
                for uncertain_as in (0, 1) if attack_only else (0,):
                    test = paired_test(pairs, field=field, uncertain_as=uncertain_as)
                    test.update({"model": model, "contrast": f"{reference} vs {other}"})
                    results.append(test)
    _adjust(results, key=lambda item: (item["field"], item["uncertain_counted_as"]))
    return results


def model_tests(rows: list[dict[str, Any]], *, field: str = "attack_score") -> list[dict[str, Any]]:
    """Every pair of models on the same attack cases, within each condition."""
    index = _index(rows)
    models = sorted({key[0] for key in index})
    conditions = sorted({key[2] for key in index})
    results: list[dict[str, Any]] = []
    for condition in conditions:
        for position, first in enumerate(models):
            for second in models[position + 1 :]:
                pairs = [
                    (index[(first, case, condition)], index[(second, case, condition)])
                    for (m, case, cond) in index
                    if m == first
                    and cond == condition
                    and (second, case, condition) in index
                    and bool(index[(m, case, cond)].get("is_attack"))
                ]
                if not pairs:
                    continue
                test = paired_test(pairs, field=field)
                test.update({"first_model": first, "second_model": second, "condition": condition})
                results.append(test)
    _adjust(results, key=lambda item: item["condition"])
    return results


def _adjust(results: list[dict[str, Any]], *, key: Callable[[dict[str, Any]], object]) -> None:
    families: dict[object, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        families[key(item)].append(item)
    for family in families.values():
        adjusted = holm([item["mcnemar"]["p_value"] for item in family])
        for item, value in zip(family, adjusted, strict=True):
            item["holm_p_value"] = value
            item["family_size"] = len(family)


def power_table(n_pairs: int, *, alpha: float = 0.05) -> list[dict[str, Any]]:
    """What a paired test with n_pairs cases could and could not detect.

    Each row assumes the defense removes `reduction` of the attack-success probability
    and newly introduces successes on `p_c` of cases. Power is the chance of p <= alpha.
    """
    rows: list[dict[str, Any]] = []
    for reduction in (0.03, 0.05, 0.10, 0.15, 0.20, 0.30):
        for p_c in (0.0, 0.02):
            rows.append(
                {
                    "pairs": n_pairs,
                    "alpha": alpha,
                    "reduction": reduction,
                    "p_b": reduction + p_c,
                    "p_c": p_c,
                    "power": mcnemar_power(n_pairs, reduction + p_c, p_c, alpha=alpha),
                }
            )
    return rows


def precision_table(n: int) -> list[dict[str, Any]]:
    """Wilson half-widths at this denominator, for a few true rates."""
    out: list[dict[str, Any]] = []
    for rate in (0.0, 0.05, 0.10, 0.25, 0.50):
        successes = round(rate * n)
        interval = wilson_interval(successes, n)
        out.append(
            {
                "n": n,
                "successes": successes,
                "rate": successes / n if n else None,
                "low": interval["low"],
                "high": interval["high"],
                "width": (interval["high"] - interval["low"]) if n else None,
            }
        )
    return out
