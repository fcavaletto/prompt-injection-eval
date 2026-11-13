"""Tables and figures for the adaptive study.

Everything here is computed from stored rows. The comparison that matters is paired:
the same held-out seed under the same condition, once with the static 0.3.0 document and
once with a document built by a strategy that was chosen on other seeds.

Attack score `uncertain` counts as not a success, as in the static tables. The headline
table also carries the count with `uncertain` read as a success, so the two readings can
be compared.

A *quiet* success is an attack success on a row whose legitimate task also succeeded: the
user gets a normal-looking answer with the attacker's output in it. Most asks demand the
attacker's output "and nothing else", which rules a quiet success out by construction, so
quiet counts are reported per goal as well.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prompt_injection_eval.adaptive.attacker import MODES, success_by_attempt
from prompt_injection_eval.adaptive.hardening import ADAPTIVE_CONDITIONS, HARDENED_CONDITION
from prompt_injection_eval.adaptive.strategies import (
    BOUNDARIES,
    FRAMINGS,
    SPACINGS,
    all_strategies,
)
from prompt_injection_eval.adaptive.toolrole import NO_TAIL_CONDITION, TOOL_CONDITIONS
from prompt_injection_eval.constants import CONDITIONS
from prompt_injection_eval.metrics import wilson_interval
from prompt_injection_eval.stats import holm, paired_test

REFERENCE_STRATEGY = "naive+inline+plain"
STATIC_STRATEGY = "static_document"
# Conditions with a static-versus-adaptive headline. The patch is reported on its own.
HEADLINE_CONDITIONS = (*CONDITIONS, *TOOL_CONDITIONS)
# Paired placement comparisons: (first, second, what changes between them).
PLACEMENT_COMPARISONS = (
    ("baseline", "tool", "no rule: user message to tool result"),
    ("defended", NO_TAIL_CONDITION, "rule: drop the line after the document"),
    (NO_TAIL_CONDITION, "tool_defended", "rule, document last: user message to tool result"),
    ("defended", "tool_defended", "rule: user message to tool result"),
)
GOAL_ORDER = (
    "exact_output",
    "synthetic_secret_disclosure",
    "format_hijack",
    "tool_call_text",
    "forced_json",
)


class AnalysisError(ValueError):
    """The stored rows do not line up."""


@dataclass
class ModelInputs:
    label: str
    static_rows: list[dict[str, Any]]
    grid_rows: list[dict[str, Any]]
    test_rows: list[dict[str, Any]]
    ranking: dict[str, Any]
    carrier_rows: list[dict[str, Any]] = field(default_factory=list)
    attacker_rows: list[dict[str, Any]] = field(default_factory=list)


def _ok(row: dict[str, Any]) -> bool:
    return not row.get("error_type")


def _hit(row: dict[str, Any] | None) -> bool:
    return row is not None and _ok(row) and row.get("attack_score") == "success"


def _quiet(row: dict[str, Any] | None) -> bool:
    return _hit(row) and row is not None and row.get("task_score") == "success"


def _hit_or_uncertain(row: dict[str, Any] | None) -> bool:
    return row is not None and _ok(row) and row.get("attack_score") in {"success", "uncertain"}


def _wilson(successes: int, total: int) -> str:
    interval = wilson_interval(successes, total)
    if interval["low"] is None:
        return ""
    return f"[{interval['low']:.3f}, {interval['high']:.3f}]"


def _test_index(inputs: ModelInputs) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in inputs.test_rows:
        if row.get("adaptive_phase") == "test" and row.get("seed_split") == "test":
            index[(row["case_id"], row["condition"], row["strategy"])] = row
    return index


def _test_seed_ids(inputs: ModelInputs) -> list[str]:
    ids = sorted({key[0] for key in _test_index(inputs)})
    if not ids:
        raise AnalysisError(f"{inputs.label}: no held-out test rows")
    return ids


def _static_index(inputs: ModelInputs) -> dict[tuple[str, str], dict[str, Any]]:
    """Static rows: the 0.3.0 study, plus static documents rerun under new conditions."""
    index = {(row["case_id"], row["condition"]): row for row in inputs.static_rows}
    for row in inputs.test_rows:
        if row.get("adaptive_phase") == "static" and row.get("seed_split") == "test":
            index[(row["case_id"], row["condition"])] = row
    return index


def _any_of(rows: list[dict[str, Any] | None]) -> dict[str, Any]:
    """A synthetic row: success if any attempt succeeded."""
    return {"attack_score": "success" if any(_hit(row) for row in rows) else "failure"}


def headline(inputs: ModelInputs) -> list[dict[str, Any]]:
    """Static against adaptive on the held-out seeds, one row per condition."""
    tests = _test_index(inputs)
    static = _static_index(inputs)
    seeds = _test_seed_ids(inputs)
    out: list[dict[str, Any]] = []
    for condition in HEADLINE_CONDITIONS:
        order = [entry["strategy"] for entry in inputs.ranking["conditions"].get(condition, [])]
        if not order:
            continue
        static_rows = []
        for seed_id in seeds:
            row = static.get((seed_id, condition))
            if row is None:
                raise AnalysisError(f"{inputs.label}: no static row for {seed_id} {condition}")
            static_rows.append(row)
        ranked = [[tests.get((seed_id, condition, name)) for name in order] for seed_id in seeds]
        missing = sum(1 for attempts in ranked for row in attempts if row is None)
        if missing:
            raise AnalysisError(f"{inputs.label} {condition}: {missing} test units missing")
        first = [attempts[0] for attempts in ranked]
        plain_order = inputs.ranking.get("conditions_plain", {}).get(condition, [])
        plain_name = plain_order[0]["strategy"] if plain_order else None
        plain = [tests.get((seed_id, condition, plain_name or "")) for seed_id in seeds]
        n = len(seeds)
        record: dict[str, Any] = {
            "model": inputs.label,
            "condition": condition,
            "held_out_seeds": n,
            "static_successes": sum(_hit(row) for row in static_rows),
            "static_or_uncertain": sum(_hit_or_uncertain(row) for row in static_rows),
            "top_strategy": order[0],
            "top_strategy_dev_successes": inputs.ranking["conditions"][condition][0][
                "dev_successes"
            ],
            "dev_seeds": inputs.ranking["dev_seed_count"],
            "adaptive_1_successes": sum(_hit(row) for row in first),
            "adaptive_1_or_uncertain": sum(_hit_or_uncertain(row) for row in first),
            "adaptive_1_task_successes": sum(
                1 for row in first if row is not None and row.get("task_score") == "success"
            ),
            "static_task_successes": sum(
                1 for row in static_rows if row.get("task_score") == "success"
            ),
            "static_quiet": sum(_quiet(row) for row in static_rows),
            "adaptive_1_quiet": sum(_quiet(row) for row in first),
            "backend_errors": sum(
                1 for attempts in ranked for row in attempts if row is not None and not _ok(row)
            ),
        }
        record["static_wilson"] = _wilson(record["static_successes"], n)
        record["adaptive_1_wilson"] = _wilson(record["adaptive_1_successes"], n)
        for k in range(2, len(order) + 1):
            count = sum(_hit(_any_of(attempts[:k])) for attempts in ranked)
            record[f"adaptive_{k}_successes"] = count
        reference = [tests.get((seed_id, condition, REFERENCE_STRATEGY)) for seed_id in seeds]
        record["reference_naive_successes"] = (
            sum(_hit(row) for row in reference) if all(reference) else None
        )
        record["reference_naive_quiet"] = (
            sum(_quiet(row) for row in reference) if all(reference) else None
        )
        # The first-ranked strategy among those with ordinary spacing, so the count does
        # not depend on the blank-character trick.
        if plain_name is not None and all(plain):
            record["plain_top_strategy"] = plain_name
            record["plain_top_dev_successes"] = plain_order[0]["dev_successes"]
            record["plain_1_successes"] = sum(_hit(row) for row in plain)
            record["plain_1_wilson"] = _wilson(record["plain_1_successes"], n)
            record["plain_1_quiet"] = sum(_quiet(row) for row in plain)
            versus_static = paired_test(
                [(left, right) for left, right in zip(static_rows, plain, strict=True) if right],
                field="attack_score",
            )
            record["mcnemar_p_plain"] = versus_static["mcnemar"]["p_value"]
        pairs = [(left, right) for left, right in zip(static_rows, first, strict=True) if right]
        test = paired_test(pairs, field="attack_score")
        record["only_static"] = test["only_first"]
        record["only_adaptive"] = test["only_second"]
        record["mcnemar_p"] = test["mcnemar"]["p_value"]
        record["difference"] = test["bootstrap"]["difference"]
        record["difference_low"] = test["bootstrap"]["low"]
        record["difference_high"] = test["bootstrap"]["high"]
        # The same test against the plain override on the same seeds. This holds the
        # payload wording fixed, so the difference is the strategy alone.
        if all(reference):
            versus = paired_test(
                [
                    (left, right)
                    for left, right in zip(reference, first, strict=True)
                    if left and right
                ],
                field="attack_score",
            )
            record["only_naive"] = versus["only_first"]
            record["only_adaptive_vs_naive"] = versus["only_second"]
            record["mcnemar_p_vs_naive"] = versus["mcnemar"]["p_value"]
            record["difference_vs_naive"] = versus["bootstrap"]["difference"]
            record["difference_vs_naive_low"] = versus["bootstrap"]["low"]
            record["difference_vs_naive_high"] = versus["bootstrap"]["high"]
        out.append(record)
    return out


def dev_grid(inputs: ModelInputs) -> list[dict[str, Any]]:
    rows = [
        row
        for row in inputs.grid_rows
        if row.get("adaptive_phase") == "grid" and row.get("seed_split") == "dev" and _ok(row)
    ]
    out: list[dict[str, Any]] = []
    for condition in ADAPTIVE_CONDITIONS:
        for strategy in all_strategies():
            cell = [
                row
                for row in rows
                if row["condition"] == condition and row["strategy"] == strategy.name
            ]
            if not cell:
                continue
            out.append(
                {
                    "model": inputs.label,
                    "condition": condition,
                    "strategy": strategy.name,
                    "framing": strategy.framing,
                    "boundary": strategy.boundary,
                    "spacing": strategy.spacing,
                    "successes": sum(_hit(row) for row in cell),
                    "uncertain": sum(row["attack_score"] == "uncertain" for row in cell),
                    "n": len(cell),
                }
            )
    return out


def ablation(grid: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Marginal dev success for each level of each factor, and the boundary x spacing cells."""
    out: list[dict[str, Any]] = []
    keys = sorted({(row["model"], row["condition"]) for row in grid})
    factors = (("framing", FRAMINGS), ("boundary", BOUNDARIES), ("spacing", SPACINGS))
    for model, condition in keys:
        cells = [row for row in grid if row["model"] == model and row["condition"] == condition]
        for factor, levels in factors:
            for level in levels:
                part = [row for row in cells if row[factor] == level]
                out.append(_ablation_row(model, condition, factor, level, part))
        for boundary in BOUNDARIES:
            for spacing in SPACINGS:
                part = [
                    row
                    for row in cells
                    if row["boundary"] == boundary and row["spacing"] == spacing
                ]
                out.append(
                    _ablation_row(
                        model, condition, "boundary x spacing", f"{boundary}+{spacing}", part
                    )
                )
    return out


def _ablation_row(
    model: str, condition: str, factor: str, level: str, part: list[dict[str, Any]]
) -> dict[str, Any]:
    successes = sum(row["successes"] for row in part)
    total = sum(row["n"] for row in part)
    return {
        "model": model,
        "condition": condition,
        "factor": factor,
        "level": level,
        "successes": successes,
        "n": total,
        "rate": successes / total if total else None,
    }


def by_goal(inputs: ModelInputs) -> list[dict[str, Any]]:
    tests = _test_index(inputs)
    static = _static_index(inputs)
    seeds = _test_seed_ids(inputs)
    goal_of = {key[0]: row["goal_type"] for key, row in tests.items()}
    out: list[dict[str, Any]] = []
    for condition in HEADLINE_CONDITIONS:
        order = [entry["strategy"] for entry in inputs.ranking["conditions"].get(condition, [])]
        if not order:
            continue
        for goal in GOAL_ORDER:
            members = [seed_id for seed_id in seeds if goal_of[seed_id] == goal]
            if not members:
                continue
            out.append(
                {
                    "model": inputs.label,
                    "condition": condition,
                    "goal_type": goal,
                    "n": len(members),
                    "static_successes": sum(
                        _hit(static.get((seed_id, condition))) for seed_id in members
                    ),
                    "adaptive_1_successes": sum(
                        _hit(tests.get((seed_id, condition, order[0]))) for seed_id in members
                    ),
                    "adaptive_1_quiet": sum(
                        _quiet(tests.get((seed_id, condition, order[0]))) for seed_id in members
                    ),
                    "adaptive_all_successes": sum(
                        _hit(_any_of([tests.get((seed_id, condition, name)) for name in order]))
                        for seed_id in members
                    ),
                }
            )
    return out


def transfer(all_inputs: list[ModelInputs]) -> list[dict[str, Any]]:
    """The first-ranked strategy of each source model, run on each target's held-out seeds."""
    out: list[dict[str, Any]] = []
    for target in all_inputs:
        tests = _test_index(target)
        seeds = _test_seed_ids(target)
        for source in all_inputs:
            for condition in CONDITIONS:
                order = source.ranking["conditions"].get(condition)
                if not order:
                    continue
                name = order[0]["strategy"]
                rows = [tests.get((seed_id, condition, name)) for seed_id in seeds]
                if not all(rows):
                    continue
                out.append(
                    {
                        "target_model": target.label,
                        "source_model": source.label,
                        "condition": condition,
                        "strategy": name,
                        "successes": sum(_hit(row) for row in rows),
                        "n": len(seeds),
                    }
                )
    return out


def carriers(inputs: ModelInputs) -> list[dict[str, Any]]:
    """Clean carriers: any attack score other than failure is a scorer false positive."""
    rows = [row for row in inputs.carrier_rows if row.get("adaptive_phase") == "carrier"]
    out: list[dict[str, Any]] = []
    for condition in ADAPTIVE_CONDITIONS:
        cell = [row for row in rows if row["condition"] == condition and _ok(row)]
        if not cell:
            continue
        out.append(
            {
                "model": inputs.label,
                "condition": condition,
                "n": len(cell),
                "attack_success": sum(row["attack_score"] == "success" for row in cell),
                "attack_uncertain": sum(row["attack_score"] == "uncertain" for row in cell),
                "task_success": sum(row["task_score"] == "success" for row in cell),
            }
        )
    return out


def attacker_arms(inputs: ModelInputs) -> list[dict[str, Any]]:
    """Seeds solved within k attempts by the attacker model, with feedback and blind."""
    out: list[dict[str, Any]] = []
    rows = inputs.attacker_rows
    for mode in MODES:
        phase = [row for row in rows if row.get("adaptive_phase") == f"llm_{mode}"]
        if not phase:
            continue
        budget = max(row["attempt"] for row in phase)
        for condition, cell in success_by_attempt(rows, mode=mode, budget=budget).items():
            record: dict[str, Any] = {
                "model": inputs.label,
                "attacker_model": phase[0]["attacker_model"],
                "mode": mode,
                "condition": condition,
                "seeds": cell["seeds"],
                "attempts_made": sum(1 for row in phase if row["condition"] == condition),
            }
            for k, solved in enumerate(cell["solved_within"], start=1):
                record[f"solved_within_{k}"] = solved
            out.append(record)
    return out


def attacker_paired(inputs: ModelInputs) -> list[dict[str, Any]]:
    """Feedback against blind at the full budget, paired by seed."""
    out: list[dict[str, Any]] = []
    solved: dict[tuple[str, str, str], bool] = {}
    for row in inputs.attacker_rows:
        phase = str(row.get("adaptive_phase", ""))
        if not phase.startswith("llm_"):
            continue
        key = (phase[4:], row["condition"], row["case_id"])
        solved[key] = solved.get(key, False) or _hit(row)
    for condition in ADAPTIVE_CONDITIONS:
        seeds = sorted(
            key[2]
            for key in solved
            if key[0] == "feedback"
            and key[1] == condition
            and ("blind", condition, key[2]) in solved
        )
        if not seeds:
            continue
        pairs = [
            (
                {"attack_score": "success" if solved[("blind", condition, s)] else "failure"},
                {"attack_score": "success" if solved[("feedback", condition, s)] else "failure"},
            )
            for s in seeds
        ]
        test = paired_test(pairs, field="attack_score")
        out.append(
            {
                "model": inputs.label,
                "condition": condition,
                "seeds": len(seeds),
                "blind_solved": test["first_successes"],
                "feedback_solved": test["second_successes"],
                "only_blind": test["only_first"],
                "only_feedback": test["only_second"],
                "mcnemar_p": test["mcnemar"]["p_value"],
            }
        )
    return out


def patch_round(inputs: ModelInputs) -> list[dict[str, Any]]:
    """Datamarking against its patch, on the held-out seeds.

    `replayed` is the strategy that was first-ranked against datamarking, run unchanged
    against the patch. `re_ranked` is the strategy that was first-ranked on the dev seeds
    against the patch itself.
    """
    conditions = inputs.ranking["conditions"]
    if HARDENED_CONDITION not in conditions or "spotlight" not in conditions:
        return []
    tests = _test_index(inputs)
    seeds = _test_seed_ids(inputs)
    old_top = conditions["spotlight"][0]["strategy"]
    order = [entry["strategy"] for entry in conditions[HARDENED_CONDITION]]

    def column(condition: str, name: str) -> list[dict[str, Any] | None]:
        return [tests.get((seed_id, condition, name)) for seed_id in seeds]

    def count(rows: list[dict[str, Any] | None]) -> int | None:
        return sum(_hit(row) for row in rows) if all(rows) else None

    before = column("spotlight", old_top)
    after = column(HARDENED_CONDITION, order[0])
    ranked = [
        [tests.get((seed_id, HARDENED_CONDITION, name)) for name in order] for seed_id in seeds
    ]
    record: dict[str, Any] = {
        "model": inputs.label,
        "held_out_seeds": len(seeds),
        "spotlight_strategy": old_top,
        "spotlight_successes": count(before),
        "replayed_successes": count(column(HARDENED_CONDITION, old_top)),
        "plain_override_successes": count(column(HARDENED_CONDITION, REFERENCE_STRATEGY)),
        "re_ranked_strategy": order[0],
        "re_ranked_dev_successes": conditions[HARDENED_CONDITION][0]["dev_successes"],
        "re_ranked_successes": count(after),
        "re_ranked_all_successes": sum(_hit(_any_of(attempts)) for attempts in ranked),
    }
    if all(before) and all(after):
        test = paired_test(
            [(left, right) for left, right in zip(before, after, strict=True) if left and right],
            field="attack_score",
        )
        record["only_spotlight"] = test["only_first"]
        record["only_patch"] = test["only_second"]
        record["mcnemar_p"] = test["mcnemar"]["p_value"]
    clean = {row["condition"]: row for row in carriers(inputs)}
    for name in ("spotlight", HARDENED_CONDITION):
        if name in clean:
            record[f"clean_task_success_{name}"] = clean[name]["task_success"]
            record["clean_documents"] = clean[name]["n"]
    return [record]


def placement(inputs: ModelInputs) -> list[dict[str, Any]]:
    """User-message against tool-result placement, paired by held-out seed.

    Two attacks: the static document and the plain override. Both are fixed in advance,
    so neither was tuned to either placement. A comparison is skipped when a side has no
    rows, for example when the control was not run.
    """
    tests = _test_index(inputs)
    static = _static_index(inputs)
    seeds = _test_seed_ids(inputs)
    attacks = {
        STATIC_STRATEGY: lambda seed_id, condition: static.get((seed_id, condition)),
        REFERENCE_STRATEGY: lambda seed_id, condition: tests.get(
            (seed_id, condition, REFERENCE_STRATEGY)
        ),
    }
    out: list[dict[str, Any]] = []
    for attack, lookup in attacks.items():
        for first, second, change in PLACEMENT_COMPARISONS:
            pairs = [(lookup(seed_id, first), lookup(seed_id, second)) for seed_id in seeds]
            if not all(left and right for left, right in pairs):
                continue
            test = paired_test(pairs, field="attack_score")  # type: ignore[arg-type]
            out.append(
                {
                    "model": inputs.label,
                    "attack": attack,
                    "first": first,
                    "second": second,
                    "change": change,
                    "pairs": test["pairs"],
                    "first_successes": test["first_successes"],
                    "second_successes": test["second_successes"],
                    "only_first": test["only_first"],
                    "only_second": test["only_second"],
                    "mcnemar_p": test["mcnemar"]["p_value"],
                }
            )
    return out


def adjust_family(all_rows: list[dict[str, Any]]) -> None:
    """Holm within each family: user-message templates, and tool-result placements.

    The tool-result conditions were added after the first report, so they are their own
    family and do not change the adjusted p-values reported for the templates.
    """
    families = [
        [row for row in all_rows if row["condition"] not in TOOL_CONDITIONS],
        [row for row in all_rows if row["condition"] in TOOL_CONDITIONS],
    ]
    for rows in families:
        if rows:
            _adjust(rows)


def _adjust(rows: list[dict[str, Any]]) -> None:
    adjusted = holm([row["mcnemar_p"] for row in rows])
    for row, value in zip(rows, adjusted, strict=True):
        row["mcnemar_p_holm"] = value
    with_plain = [row for row in rows if "mcnemar_p_plain" in row]
    adjusted = holm([row["mcnemar_p_plain"] for row in with_plain])
    for row, value in zip(with_plain, adjusted, strict=True):
        row["mcnemar_p_plain_holm"] = value
    with_reference = [row for row in rows if "mcnemar_p_vs_naive" in row]
    adjusted = holm([row["mcnemar_p_vs_naive"] for row in with_reference])
    for row, value in zip(with_reference, adjusted, strict=True):
        row["mcnemar_p_vs_naive_holm"] = value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _p(value: float) -> str:
    return "<0.001" if value < 0.001 else f"{value:.3f}"


def _frac(successes: int | None, total: int) -> str:
    if successes is None or not total:
        return "n/a"
    return f"{successes}/{total} ({successes / total:.3f})"


def _report(
    head: list[dict[str, Any]],
    grid: list[dict[str, Any]],
    abl: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    moved: list[dict[str, Any]],
    clean: list[dict[str, Any]],
    arms: list[dict[str, Any]],
    arm_tests: list[dict[str, Any]],
    patch: list[dict[str, Any]],
    placed: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        "# Adaptive attack report",
        "",
        "Generated by `pie adaptive report` from stored rows. `uncertain` attack scores "
        "count as not a success.",
        "",
        "## Held-out seeds: static document against the first-ranked adaptive strategy",
        "",
        "| Model | Condition | Static | 95% Wilson | Adaptive, 1 try | 95% Wilson | "
        "Adaptive, all ranked | Only static | Only adaptive | p | Holm p | "
        "Difference [95% bootstrap] |",
        "| --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in head:
        n = row["held_out_seeds"]
        ks = [key for key in row if key.startswith("adaptive_") and key.endswith("_successes")]
        last = max(
            (key for key in ks if key.split("_")[1].isdigit()),
            key=lambda key: int(key.split("_")[1]),
        )
        lines.append(
            f"| {row['model']} | {row['condition']} | {_frac(row['static_successes'], n)} | "
            f"{row['static_wilson']} | {_frac(row['adaptive_1_successes'], n)} | "
            f"{row['adaptive_1_wilson']} | {_frac(row[last], n)} | {row['only_static']} | "
            f"{row['only_adaptive']} | {_p(row['mcnemar_p'])} | {_p(row['mcnemar_p_holm'])} | "
            f"{row['difference']:+.3f} [{row['difference_low']:+.3f}, "
            f"{row['difference_high']:+.3f}] |"
        )
    lines += [
        "",
        "## First-ranked strategy per model and condition",
        "",
        "| Model | Condition | Strategy | Dev successes | Naive reference on held-out | "
        "Task success, static | Task success, adaptive |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in head:
        n = row["held_out_seeds"]
        lines.append(
            f"| {row['model']} | {row['condition']} | `{row['top_strategy']}` | "
            f"{row['top_strategy_dev_successes']}/{row['dev_seeds']} | "
            f"{_frac(row['reference_naive_successes'], n)} | "
            f"{row['static_task_successes']}/{n} | {row['adaptive_1_task_successes']}/{n} |"
        )
    lines += [
        "",
        "## Held-out seeds: plain override against the first-ranked adaptive strategy",
        "",
        "Same seeds, same ask, same template. Only the strategy differs.",
        "",
        "| Model | Condition | Plain override | Adaptive, 1 try | Only plain | Only adaptive | "
        "p | Holm p | Difference [95% bootstrap] |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in head:
        if "mcnemar_p_vs_naive" not in row:
            continue
        n = row["held_out_seeds"]
        lines.append(
            f"| {row['model']} | {row['condition']} | "
            f"{_frac(row['reference_naive_successes'], n)} | "
            f"{_frac(row['adaptive_1_successes'], n)} | {row['only_naive']} | "
            f"{row['only_adaptive_vs_naive']} | {_p(row['mcnemar_p_vs_naive'])} | "
            f"{_p(row['mcnemar_p_vs_naive_holm'])} | {row['difference_vs_naive']:+.3f} "
            f"[{row['difference_vs_naive_low']:+.3f}, {row['difference_vs_naive_high']:+.3f}] |"
        )
    if any("plain_1_successes" in row for row in head):
        lines += [
            "",
            "## Held-out seeds: first-ranked strategy with ordinary spacing",
            "",
            "Ranked on the dev seeds among the 12 strategies that do not use the blank "
            "character. Where it is the same strategy as the first-ranked one, the counts "
            "match.",
            "",
            "| Model | Condition | Static | Any strategy, 1 try | Plain spacing, 1 try | "
            "95% Wilson | Strategy | Dev successes | p vs static | Holm p |",
            "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |",
        ]
        for row in head:
            if "plain_1_successes" not in row:
                continue
            n = row["held_out_seeds"]
            lines.append(
                f"| {row['model']} | {row['condition']} | {row['static_successes']}/{n} | "
                f"{row['adaptive_1_successes']}/{n} | {_frac(row['plain_1_successes'], n)} | "
                f"{row['plain_1_wilson']} | `{row['plain_top_strategy']}` | "
                f"{row['plain_top_dev_successes']}/{row['dev_seeds']} | "
                f"{_p(row['mcnemar_p_plain'])} | {_p(row['mcnemar_p_plain_holm'])} |"
            )
    lines += [
        "",
        "## Quiet successes: attack succeeded and the task still succeeded",
        "",
        "| Model | Condition | Static | Plain override | First-ranked | Plain spacing |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in head:
        n = row["held_out_seeds"]
        lines.append(
            f"| {row['model']} | {row['condition']} | {row['static_quiet']}/{n} | "
            f"{_frac(row['reference_naive_quiet'], n)} | {row['adaptive_1_quiet']}/{n} | "
            f"{_frac(row.get('plain_1_quiet'), n)} |"
        )
    lines += ["", "## Attack success by number of ranked strategies tried", ""]
    width = max(
        (
            int(key.split("_")[1])
            for row in head
            for key in row
            if key.startswith("adaptive_")
            and key.endswith("_successes")
            and key.split("_")[1].isdigit()
        ),
        default=1,
    )
    lines.append(
        "| Model | Condition | " + " | ".join(f"k={k}" for k in range(1, width + 1)) + " |"
    )
    lines.append("| --- | --- | " + " | ".join("---:" for _ in range(width)) + " |")
    for row in head:
        cells = [str(row.get(f"adaptive_{k}_successes", "")) for k in range(1, width + 1)]
        lines.append(f"| {row['model']} | {row['condition']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Dev ablation: success rate by factor level",
        "",
        "| Model | Condition | Factor | Level | Successes |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in abl:
        lines.append(
            f"| {row['model']} | {row['condition']} | {row['factor']} | {row['level']} | "
            f"{_frac(row['successes'], row['n'])} |"
        )
    lines += [
        "",
        "## Held-out seeds by attack goal",
        "",
        "| Model | Condition | Goal | Static | Adaptive, 1 try | Of which quiet | "
        "Adaptive, all ranked |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in goals:
        n = row["n"]
        lines.append(
            f"| {row['model']} | {row['condition']} | {row['goal_type']} | "
            f"{row['static_successes']}/{n} | {row['adaptive_1_successes']}/{n} | "
            f"{row['adaptive_1_quiet']} | {row['adaptive_all_successes']}/{n} |"
        )
    lines += [
        "",
        "## Transfer: one model's first-ranked strategy on another model's held-out seeds",
        "",
        "| Target | Condition | Tuned on | Strategy | Successes |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in moved:
        lines.append(
            f"| {row['target_model']} | {row['condition']} | {row['source_model']} | "
            f"`{row['strategy']}` | {_frac(row['successes'], row['n'])} |"
        )
    if clean:
        lines += [
            "",
            "## Clean carriers: nothing appended",
            "",
            "| Model | Condition | Attack success | Attack uncertain | Task success |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
        for row in clean:
            n = row["n"]
            lines.append(
                f"| {row['model']} | {row['condition']} | {row['attack_success']}/{n} | "
                f"{row['attack_uncertain']}/{n} | {row['task_success']}/{n} |"
            )
    if arms:
        width = max(
            int(key.rsplit("_", 1)[1])
            for row in arms
            for key in row
            if key.startswith("solved_within_")
        )
        lines += [
            "",
            "## Attacker model on the held-out seeds: seeds solved within k attempts",
            "",
            "| Target | Mode | Condition | Seeds | "
            + " | ".join(f"k={k}" for k in range(1, width + 1))
            + " |",
            "| --- | --- | --- | ---: | " + " | ".join("---:" for _ in range(width)) + " |",
        ]
        for row in arms:
            cells = [str(row.get(f"solved_within_{k}", "")) for k in range(1, width + 1)]
            lines.append(
                f"| {row['model']} | {row['mode']} | {row['condition']} | {row['seeds']} | "
                + " | ".join(cells)
                + " |"
            )
    if arm_tests:
        lines += [
            "",
            "## Feedback against blind at the full budget, paired by seed",
            "",
            "| Target | Condition | Blind | Feedback | Only blind | Only feedback | p |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in arm_tests:
            n = row["seeds"]
            lines.append(
                f"| {row['model']} | {row['condition']} | {row['blind_solved']}/{n} | "
                f"{row['feedback_solved']}/{n} | {row['only_blind']} | "
                f"{row['only_feedback']} | {_p(row['mcnemar_p'])} |"
            )
    if patch:
        lines += [
            "",
            "## Patch round: datamarking (defended-v2) against its patch (defended-v3)",
            "",
            "Held-out seeds, one try. `Replayed` is the strategy first-ranked against "
            "datamarking, unchanged. `Re-ranked` is the strategy first-ranked on the dev "
            "seeds against the patch.",
            "",
            "| Model | Datamarking | Patch, replayed | Patch, plain override | "
            "Patch, re-ranked | Re-ranked strategy | Patch, all ranked | p | "
            "Clean task success, datamarking | Clean task success, patch |",
            "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
        for row in patch:
            n = row["held_out_seeds"]
            docs = row.get("clean_documents")
            clean_old = row.get("clean_task_success_spotlight")
            clean_new = row.get(f"clean_task_success_{HARDENED_CONDITION}")
            lines.append(
                f"| {row['model']} | {_frac(row['spotlight_successes'], n)} | "
                f"{_frac(row['replayed_successes'], n)} | "
                f"{_frac(row['plain_override_successes'], n)} | "
                f"{_frac(row['re_ranked_successes'], n)} | `{row['re_ranked_strategy']}` | "
                f"{_frac(row['re_ranked_all_successes'], n)} | "
                f"{_p(row['mcnemar_p']) if 'mcnemar_p' in row else 'n/a'} | "
                f"{clean_old}/{docs} | {clean_new}/{docs} |"
            )
    if placed:
        lines += [
            "",
            "## Placement: user message against tool result, paired by seed",
            "",
            "Held-out seeds. Two attacks fixed in advance: the static document and the plain "
            "override. `defended_no_tail` is `defended-v1` without the line after the "
            "document. Holm p is adjusted over every row of this table.",
            "",
            "| Model | Attack | First | Second | What changes | First | Second | "
            "Only first | Only second | p | Holm p |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in placed:
            n = row["pairs"]
            lines.append(
                f"| {row['model']} | {row['attack']} | {row['first']} | {row['second']} | "
                f"{row['change']} | {row['first_successes']}/{n} | "
                f"{row['second_successes']}/{n} | {row['only_first']} | "
                f"{row['only_second']} | {_p(row['mcnemar_p'])} | "
                f"{_p(row['mcnemar_p_holm'])} |"
            )
    lines += ["", f"Dev grid cells: {len(grid)}. Full grid in `dev_grid.csv`.", ""]
    return "\n".join(lines)


def _figure(head: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    head = [row for row in head if row["condition"] in CONDITIONS]
    models = list(dict.fromkeys(row["model"] for row in head))
    fig, axes = plt.subplots(1, len(models), figsize=(4.2 * len(models), 3.8), sharey=True)
    if len(models) == 1:
        axes = [axes]
    series = (
        ("static_successes", "Static documents (0.3.0)", "#98a6b3"),
        ("reference_naive_successes", "Plain override, same payload", "#e0a458"),
        ("adaptive_1_successes", "First-ranked strategy, one try", "#3d5a80"),
    )
    names = {"baseline": "No defense", "defended": "Generic rule", "spotlight": "Datamarking"}
    for axis, model in zip(axes, models, strict=True):
        rows = [row for row in head if row["model"] == model]
        for offset, (key, label, color) in enumerate(series):
            values = [(row.get(key) or 0) / row["held_out_seeds"] for row in rows]
            positions = [index + (offset - 1) * 0.27 for index in range(len(rows))]
            axis.bar(positions, values, width=0.25, label=label, color=color)
        axis.set_xticks(range(len(rows)))
        axis.set_xticklabels([names.get(row["condition"], row["condition"]) for row in rows])
        axis.set_title(model)
        axis.set_ylim(0, 1)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Attack success rate, 59 held-out seeds")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_report(all_inputs: list[ModelInputs], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    head = [row for inputs in all_inputs for row in headline(inputs)]
    adjust_family(head)
    grid = [row for inputs in all_inputs for row in dev_grid(inputs)]
    abl = ablation(grid)
    goals = [row for inputs in all_inputs for row in by_goal(inputs)]
    moved = transfer(all_inputs)
    clean = [row for inputs in all_inputs for row in carriers(inputs)]
    arms = [row for inputs in all_inputs for row in attacker_arms(inputs)]
    arm_tests = [row for inputs in all_inputs for row in attacker_paired(inputs)]
    patch = [row for inputs in all_inputs for row in patch_round(inputs)]
    placed = [row for inputs in all_inputs for row in placement(inputs)]
    for row, value in zip(placed, holm([row["mcnemar_p"] for row in placed]), strict=True):
        row["mcnemar_p_holm"] = value
    _write_csv(output_dir / "placement.csv", placed)
    _write_csv(output_dir / "patch_round.csv", patch)
    _write_csv(output_dir / "carriers.csv", clean)
    _write_csv(output_dir / "attacker_model.csv", arms)
    _write_csv(output_dir / "attacker_model_paired.csv", arm_tests)
    _write_csv(output_dir / "headline.csv", head)
    _write_csv(output_dir / "dev_grid.csv", grid)
    _write_csv(output_dir / "ablation.csv", abl)
    _write_csv(output_dir / "by_goal.csv", goals)
    _write_csv(output_dir / "transfer.csv", moved)
    (output_dir / "report.md").write_text(
        _report(head, grid, abl, goals, moved, clean, arms, arm_tests, patch, placed),
        encoding="utf-8",
    )
    _figure(head, output_dir / "static_vs_adaptive.png")
    summary = {
        "headline": head,
        "transfer": moved,
        "by_goal": goals,
        "ablation": abl,
        "carriers": clean,
        "attacker_model": arms,
        "attacker_model_paired": arm_tests,
        "patch_round": patch,
        "placement": placed,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
