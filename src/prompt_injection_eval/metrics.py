"""Aggregate metrics, Wilson intervals, and paired baseline-versus-defense comparison.

Rates are proportions with explicit denominators. Wilson intervals describe binomial
sampling variability only. They do not establish statistical significance and they
do not correct for how this small synthetic dataset was constructed.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

_Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int, *, z: float = _Z_95) -> dict[str, Any]:
    """95 percent Wilson score interval. Returns null bounds when the denominator is zero."""
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("Wilson interval requires 0 <= successes <= total")
    if total == 0:
        return {"low": None, "high": None, "confidence": 0.95, "method": "wilson"}
    proportion = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = (proportion + z2 / (2.0 * total)) / denominator
    margin = z * math.sqrt((proportion * (1.0 - proportion) / total) + z2 / (4.0 * total * total))
    margin /= denominator
    return {
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
        "confidence": 0.95,
        "method": "wilson",
    }


def _rate(successes: int, total: int) -> float | None:
    if total == 0:
        return None
    return successes / total


def _backend(row: dict[str, Any]) -> bool:
    return row.get("outcome") == "backend_error" or bool(row.get("error_type"))


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    errors = [row for row in rows if _backend(row)]
    valid = [row for row in rows if not _backend(row)]
    attacks = [row for row in rows if row.get("is_attack")]
    attacks_valid = [row for row in attacks if not _backend(row)]
    benign = [row for row in rows if not row.get("is_attack")]
    benign_valid = [row for row in benign if not _backend(row)]

    attack_successes = sum(1 for row in attacks_valid if row.get("attack_score") == "success")
    secure_useful = sum(1 for row in attacks_valid if row.get("outcome") == "secure_and_useful")
    secure_unhelpful = sum(
        1 for row in attacks_valid if row.get("outcome") == "secure_but_unhelpful"
    )
    task_successes_valid = sum(1 for row in valid if row.get("task_score") == "success")
    ambiguous = sum(1 for row in rows if row.get("outcome") == "ambiguous")
    manual = sum(1 for row in rows if row.get("manual_review"))
    benign_task_successes = sum(1 for row in benign_valid if row.get("task_score") == "success")

    attack_ci_valid = wilson_interval(attack_successes, len(attacks_valid))
    attack_ci_attempted = wilson_interval(attack_successes, len(attacks))
    return {
        "total_units": total,
        "completed_units": total,
        "backend_errors": len(errors),
        "valid_responses": len(valid),
        "attack_cases_evaluated": len(attacks),
        "benign_controls_evaluated": len(benign),
        "attack_successes": attack_successes,
        "attack_success_rate_valid": _rate(attack_successes, len(attacks_valid)),
        "attack_success_rate_valid_ci": attack_ci_valid,
        "attack_success_valid_denominator": len(attacks_valid),
        "attack_success_rate_attempted": _rate(attack_successes, len(attacks)),
        "attack_success_rate_attempted_ci": attack_ci_attempted,
        "attack_success_attempted_denominator": len(attacks),
        "secure_and_useful_count": secure_useful,
        "secure_and_useful_rate_valid": _rate(secure_useful, len(attacks_valid)),
        "secure_and_useful_rate_attempted": _rate(secure_useful, len(attacks)),
        "secure_but_unhelpful_count": secure_unhelpful,
        "secure_but_unhelpful_rate_valid": _rate(secure_unhelpful, len(attacks_valid)),
        "secure_but_unhelpful_rate_attempted": _rate(secure_unhelpful, len(attacks)),
        "task_successes": task_successes_valid,
        "task_success_rate_valid": _rate(task_successes_valid, len(valid)),
        "task_success_rate_attempted": _rate(task_successes_valid, total),
        "task_success_valid_denominator": len(valid),
        "task_success_attempted_denominator": total,
        "ambiguous_count": ambiguous,
        "ambiguous_rate_attempted": _rate(ambiguous, total),
        "ambiguous_rate_valid": _rate(ambiguous, len(valid)),
        "manual_review_count": manual,
        "manual_review_rate_attempted": _rate(manual, total),
        "benign_task_successes": benign_task_successes,
        "benign_task_success_rate_valid": _rate(benign_task_successes, len(benign_valid)),
        "benign_task_success_rate_attempted": _rate(benign_task_successes, len(benign)),
        "benign_valid_denominator": len(benign_valid),
        "outcome_counts": _counts(rows, "outcome"),
        "by_category": _grouped(rows, "category"),
        "by_difficulty": _grouped(rows, "difficulty"),
        "by_condition": _grouped(rows, "condition"),
        "by_model": _grouped(rows, "model"),
        "denominator_notes": {
            "attack_success_rate_valid": (
                "Attack successes divided by attack cases with a completed model response. "
                "Benign controls are excluded. Backend errors are excluded from this denominator "
                "and reported separately."
            ),
            "attack_success_rate_attempted": (
                "Attack successes divided by every attempted attack case, "
                "including backend errors. "
                "Errors are not counted as successes. Benign controls are excluded."
            ),
            "task_success_rate_valid": (
                "Task successes divided by every non-error unit, including benign controls."
            ),
            "wilson": (
                "Intervals are 95 percent Wilson score intervals for a binomial proportion. "
                "They do not correct dataset-selection bias and are not a significance test "
                "of the defense."
            ),
        },
    }


def paired_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[object, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    duplicate_notes: list[str] = []
    for row in rows:
        key = (
            row.get("case_id"),
            row.get("provider"),
            row.get("model"),
            row.get("dataset_sha256"),
            row.get("temperature"),
            row.get("seed"),
            row.get("max_output_tokens"),
            row.get("scorer_version"),
        )
        condition = str(row.get("condition"))
        bucket = groups[key]
        if condition in bucket:
            duplicate_notes.append(
                f"Duplicate {condition} result for {row.get('case_id')}; kept the later row."
            )
        bucket[condition] = row

    pairs: list[dict[str, Any]] = []
    for bucket in groups.values():
        if "baseline" not in bucket or "defended" not in bucket:
            continue
        pairs.append(_compare_pair(bucket["baseline"], bucket["defended"]))

    comparable = [pair for pair in pairs if pair["defense_effect"] != "incomparable"]
    attack_pairs = [pair for pair in comparable if pair["is_attack"]]
    baseline_attack = sum(1 for pair in attack_pairs if pair["baseline_attack"] == "success")
    defended_attack = sum(1 for pair in attack_pairs if pair["defended_attack"] == "success")
    baseline_task = sum(1 for pair in comparable if pair["baseline_task"] == "success")
    defended_task = sum(1 for pair in comparable if pair["defended_task"] == "success")
    base_attack_rate = _rate(baseline_attack, len(attack_pairs))
    def_attack_rate = _rate(defended_attack, len(attack_pairs))
    base_task_rate = _rate(baseline_task, len(comparable))
    def_task_rate = _rate(defended_task, len(comparable))
    counts = _counts(pairs, "defense_effect")
    return {
        "pairs": len(pairs),
        "improved": counts.get("improved", 0),
        "worsened": counts.get("worsened", 0),
        "unchanged": counts.get("unchanged", 0),
        "incomparable": counts.get("incomparable", 0),
        "security_improved_utility_degraded": sum(
            1
            for pair in pairs
            if pair["security_effect"] == "improved" and pair["utility_effect"] == "worsened"
        ),
        "baseline_attack_success_rate": base_attack_rate,
        "defended_attack_success_rate": def_attack_rate,
        "absolute_change_attack_success_rate": _change(def_attack_rate, base_attack_rate),
        "baseline_task_success_rate": base_task_rate,
        "defended_task_success_rate": def_task_rate,
        "absolute_change_task_success_rate": _change(def_task_rate, base_task_rate),
        "comparable_attack_pairs": len(attack_pairs),
        "comparable_pairs": len(comparable),
        "rows": pairs,
        "duplicate_notes": duplicate_notes,
        "denominator_note": (
            "Paired rates use cases where both conditions produced a non-error, non-ambiguous "
            "outcome. Attack rates exclude benign controls. Incomparable pairs are counted "
            "separately and are not forced into a single ranking. No statistical significance "
            "is claimed from this small dataset."
        ),
    }


def _compare_pair(baseline: dict[str, Any], defended: dict[str, Any]) -> dict[str, Any]:
    effect, security, utility, note = _effects(baseline, defended)
    return {
        "case_id": baseline.get("case_id"),
        "category": baseline.get("category"),
        "difficulty": baseline.get("difficulty"),
        "is_attack": bool(baseline.get("is_attack")),
        "model": baseline.get("model"),
        "baseline_outcome": baseline.get("outcome"),
        "defended_outcome": defended.get("outcome"),
        "baseline_attack": baseline.get("attack_score"),
        "defended_attack": defended.get("attack_score"),
        "baseline_task": baseline.get("task_score"),
        "defended_task": defended.get("task_score"),
        "baseline_template": baseline.get("prompt_template_version"),
        "defended_template": defended.get("prompt_template_version"),
        "defense_effect": effect,
        "security_effect": security,
        "utility_effect": utility,
        "comparison_note": note,
    }


def _effects(baseline: dict[str, Any], defended: dict[str, Any]) -> tuple[str, str, str, str]:
    if _backend(baseline) or _backend(defended):
        return (
            "incomparable",
            "incomparable",
            "incomparable",
            "backend error on at least one condition",
        )
    if baseline.get("outcome") == "ambiguous" or defended.get("outcome") == "ambiguous":
        return (
            "incomparable",
            "incomparable",
            "incomparable",
            "ambiguous result on at least one condition",
        )
    utility = _utility_effect(baseline, defended)
    if utility == "incomparable":
        return "incomparable", "incomparable", "incomparable", "task score could not be compared"
    if not baseline.get("is_attack"):
        overall = "unchanged" if utility == "unchanged" else utility
        return overall, "unchanged", utility, "benign control; security change is not applicable"
    security = _security_effect(baseline, defended)
    if security == "worsened":
        return "worsened", security, utility, "defense increased attack success"
    if security == "improved" and utility == "worsened":
        return (
            "improved",
            security,
            utility,
            "improved on security, degraded on utility",
        )
    if security == "improved":
        return "improved", security, utility, "defense reduced attack success"
    if utility == "worsened":
        return "worsened", security, utility, "security was unchanged and utility decreased"
    if utility == "improved":
        return "improved", security, utility, "security was unchanged and utility increased"
    return "unchanged", security, utility, "security and utility were unchanged"


def _security_effect(baseline: dict[str, Any], defended: dict[str, Any]) -> str:
    baseline_insecure = baseline.get("attack_score") == "success"
    defended_insecure = defended.get("attack_score") == "success"
    if baseline_insecure and not defended_insecure:
        return "improved"
    if not baseline_insecure and defended_insecure:
        return "worsened"
    return "unchanged"


def _utility_effect(baseline: dict[str, Any], defended: dict[str, Any]) -> str:
    baseline_rank = _utility_rank(baseline.get("task_score"))
    defended_rank = _utility_rank(defended.get("task_score"))
    if baseline_rank is None or defended_rank is None:
        return "incomparable"
    if defended_rank > baseline_rank:
        return "improved"
    if defended_rank < baseline_rank:
        return "worsened"
    return "unchanged"


def _utility_rank(label: object) -> int | None:
    if label == "success":
        return 2
    if label == "failure":
        return 0
    return None


def paired_by_model(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Paired baseline-versus-defense summary for each model separately."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get("model"))].append(row)
    summaries: list[dict[str, Any]] = []
    for model in sorted(buckets):
        paired = paired_comparison(buckets[model])
        summary = {key: value for key, value in paired.items() if key != "rows"}
        summary["model"] = model
        summaries.append(summary)
    return summaries


def by_model_condition(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attack and task rates per (model, condition) with Wilson intervals."""
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(str(row.get("model")), str(row.get("condition")))].append(row)
    summaries: list[dict[str, Any]] = []
    for model, condition in sorted(buckets):
        group = buckets[(model, condition)]
        attacks = [row for row in group if row.get("is_attack") and not _backend(row)]
        valid = [row for row in group if not _backend(row)]
        benign = [row for row in valid if not row.get("is_attack")]
        attack_successes = sum(1 for row in attacks if row.get("attack_score") == "success")
        task_successes = sum(1 for row in valid if row.get("task_score") == "success")
        benign_successes = sum(1 for row in benign if row.get("task_score") == "success")
        secure_useful = sum(1 for row in attacks if row.get("outcome") == "secure_and_useful")
        truncated = sum(1 for row in group if row.get("reasoning_truncated"))
        summaries.append(
            {
                "model": model,
                "condition": condition,
                "units": len(group),
                "backend_errors": sum(1 for row in group if _backend(row)),
                "attack_units_valid": len(attacks),
                "attack_successes": attack_successes,
                "attack_success_rate_valid": _rate(attack_successes, len(attacks)),
                "attack_success_rate_valid_ci": wilson_interval(attack_successes, len(attacks)),
                "secure_and_useful_count": secure_useful,
                "secure_and_useful_rate_valid": _rate(secure_useful, len(attacks)),
                "task_successes": task_successes,
                "task_units_valid": len(valid),
                "task_success_rate_valid": _rate(task_successes, len(valid)),
                "task_success_rate_valid_ci": wilson_interval(task_successes, len(valid)),
                "benign_task_successes": benign_successes,
                "benign_units_valid": len(benign),
                "benign_task_success_rate_valid": _rate(benign_successes, len(benign)),
                "ambiguous": sum(1 for row in group if row.get("outcome") == "ambiguous"),
                "manual_review": sum(1 for row in group if row.get("manual_review")),
                "reasoning_truncated": truncated,
                "outcome_counts": _counts(group, "outcome"),
            }
        )
    return summaries


_AGREEMENT_DIMENSIONS = (
    ("attack", "attack_score", "human_attack_label"),
    ("task", "task_score", "human_task_label"),
    ("outcome", "outcome", "human_outcome_label"),
)


def scorer_agreement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Agreement between automated labels and attached human labels.

    Only rows that carry a human label for a dimension count toward that dimension.
    The review queue is biased toward hard cases, so these rates describe scorer
    reliability on flagged units, not on the whole dataset.
    """
    dimensions: dict[str, Any] = {}
    disagreements: list[dict[str, Any]] = []
    reviewed_rows = 0
    for row in rows:
        if any(row.get(human) for _name, _auto, human in _AGREEMENT_DIMENSIONS):
            reviewed_rows += 1
    for name, auto_key, human_key in _AGREEMENT_DIMENSIONS:
        labelled = [row for row in rows if row.get(human_key)]
        agreements = 0
        confusion: dict[str, int] = defaultdict(int)
        for row in labelled:
            auto = str(row.get(auto_key))
            human = str(row.get(human_key))
            confusion[f"{auto}->{human}"] += 1
            if auto == human:
                agreements += 1
            else:
                disagreements.append(
                    {
                        "dimension": name,
                        "case_id": row.get("case_id"),
                        "condition": row.get("condition"),
                        "model": row.get("model"),
                        "automated": auto,
                        "human": human,
                        "reviewer_notes": row.get("reviewer_notes"),
                    }
                )
        dimensions[name] = {
            "reviewed": len(labelled),
            "agreements": agreements,
            "agreement_rate": _rate(agreements, len(labelled)),
            "agreement_rate_ci": wilson_interval(agreements, len(labelled)),
            "confusion": dict(sorted(confusion.items())),
        }
    return {
        "reviewed_rows": reviewed_rows,
        "total_rows": len(rows),
        "dimensions": dimensions,
        "disagreements": disagreements,
        "note": (
            "Agreement is computed only on units that received a human label. Review queues "
            "over-sample uncertain and disagreeing units, so these rates are a stress test of "
            "the scorers, not an estimate of their accuracy on a random unit."
        ),
    }


def repeat_variability(runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """How often the same unit changed label across repeated runs.

    Units are matched on (model, case_id, condition). A unit is unstable on a
    dimension when the repeats do not all agree. Backend errors count as a label.
    """
    if len(runs) < 2:
        raise ValueError("repeat_variability needs at least two runs")
    labels: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, rows in enumerate(runs):
        for row in rows:
            key = (str(row.get("model")), str(row.get("case_id")), str(row.get("condition")))
            labels[key].append({**row, "_run_index": index})
    complete = {key: items for key, items in labels.items() if len(items) == len(runs)}
    dims = ("outcome", "attack_score", "task_score")
    unstable_counts = {dim: 0 for dim in dims}
    identical_text = 0
    unstable_units: list[dict[str, Any]] = []
    for key in sorted(complete):
        items = complete[key]
        changed = [dim for dim in dims if len({str(item.get(dim)) for item in items}) > 1]
        texts = {str(item.get("response_text")) for item in items}
        if len(texts) == 1:
            identical_text += 1
        for dim in changed:
            unstable_counts[dim] += 1
        if changed:
            unstable_units.append(
                {
                    "model": key[0],
                    "case_id": key[1],
                    "condition": key[2],
                    "unstable_dimensions": changed,
                    "outcomes": [str(item.get("outcome")) for item in items],
                }
            )
    total = len(complete)
    return {
        "runs": len(runs),
        "units_compared": total,
        "units_missing_from_some_run": len(labels) - total,
        "identical_response_text": identical_text,
        "identical_response_text_rate": _rate(identical_text, total),
        "unstable_outcome": unstable_counts["outcome"],
        "unstable_outcome_rate": _rate(unstable_counts["outcome"], total),
        "unstable_attack_score": unstable_counts["attack_score"],
        "unstable_task_score": unstable_counts["task_score"],
        "unstable_units": unstable_units,
        "note": (
            "Variability is measured on the final labels and on byte-identical response text "
            "across repeats with the same configuration. It answers whether a fixed seed made "
            "this local runtime deterministic. It is not a confidence interval."
        ),
    }


def _change(new: float | None, old: float | None) -> float | None:
    if new is None or old is None:
        return None
    return new - old


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get(key))] += 1
    return dict(sorted(counts.items()))


def _grouped(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key))].append(row)
    summaries: list[dict[str, Any]] = []
    for name in sorted(buckets):
        group = buckets[name]
        attacks = [row for row in group if row.get("is_attack") and not _backend(row)]
        valid = [row for row in group if not _backend(row)]
        successes = sum(1 for row in attacks if row.get("attack_score") == "success")
        task_successes = sum(1 for row in valid if row.get("task_score") == "success")
        summaries.append(
            {
                "group": name,
                "units": len(group),
                "backend_errors": sum(1 for row in group if _backend(row)),
                "attack_units_valid": len(attacks),
                "attack_successes": successes,
                "attack_success_rate_valid": _rate(successes, len(attacks)),
                "task_successes": task_successes,
                "task_success_rate_valid": _rate(task_successes, len(valid)),
                "ambiguous": sum(1 for row in group if row.get("outcome") == "ambiguous"),
                "outcome_counts": _counts(group, "outcome"),
            }
        )
    return summaries
