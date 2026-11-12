"""`pie stats`: paired tests, power, and secondary readings as Markdown and CSV."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from prompt_injection_eval.metrics import wilson_interval
from prompt_injection_eval.secondary import LENIENT_READING_VERSION
from prompt_injection_eval.stats import (
    defense_tests,
    model_tests,
    power_table,
    precision_table,
    smallest_significant_split,
)


def secondary_by_model_condition(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(str(row.get("model")), str(row.get("condition")))].append(row)
    out: list[dict[str, Any]] = []
    for (model, condition), group in sorted(buckets.items()):
        valid = [row for row in group if row.get("lenient_task_score") != "uncertain"]
        tool = [row for row in valid if row.get("tool_proxy_fired") is not None]
        strict = sum(1 for row in valid if row.get("task_score") == "success")
        lenient = sum(1 for row in valid if row.get("lenient_task_score") == "success")
        out.append(
            {
                "model": model,
                "condition": condition,
                "valid_units": len(valid),
                "strict_task_successes": strict,
                "lenient_task_successes": lenient,
                "tool_cases": len(tool),
                "tool_attack_successes": sum(
                    1 for row in tool if row.get("attack_score") == "success"
                ),
                "tool_attack_uncertain": sum(
                    1 for row in tool if row.get("attack_score") == "uncertain"
                ),
                "tool_proxy_fired": sum(1 for row in tool if row.get("tool_proxy_fired")),
            }
        )
    return out


def lenient_calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Strict and lenient task readings against attached human task labels."""
    labelled = [row for row in rows if row.get("human_task_label") in {"success", "failure"}]
    per_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    disagreements: list[dict[str, Any]] = []
    for row in labelled:
        model = str(row.get("model"))
        human = row["human_task_label"]
        bucket = per_model[model]
        bucket["reviewed"] += 1
        bucket["strict_agree"] += int(row.get("task_score") == human)
        bucket["lenient_agree"] += int(row.get("lenient_task_score") == human)
        if row.get("lenient_task_score") != human:
            disagreements.append(
                {
                    "model": model,
                    "case_id": row.get("case_id"),
                    "condition": row.get("condition"),
                    "strict": row.get("task_score"),
                    "lenient": row.get("lenient_task_score"),
                    "human": human,
                    "response": str(row.get("response_text") or "")[:200],
                }
            )
    summary = []
    for model, bucket in sorted(per_model.items()):
        n = bucket["reviewed"]
        summary.append(
            {
                "model": model,
                "reviewed": n,
                "strict_agreements": bucket["strict_agree"],
                "strict_ci": wilson_interval(bucket["strict_agree"], n),
                "lenient_agreements": bucket["lenient_agree"],
                "lenient_ci": wilson_interval(bucket["lenient_agree"], n),
            }
        )
    return {"per_model": summary, "disagreements": disagreements}


def write_stats_report(
    rows: list[dict[str, Any]], output_dir: Path, *, sources: list[str]
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    defense = defense_tests(rows)
    attack_contrasts = model_tests(rows, field="attack_score")
    secondary = secondary_by_model_condition(rows)
    calibration = lenient_calibration(rows)
    attack_pairs = max(
        (item["pairs"] for item in defense if item["field"] == "attack_score"), default=0
    )
    power = power_table(attack_pairs) if attack_pairs else []
    precision = precision_table(attack_pairs) if attack_pairs else []
    summary = {
        "sources": sources,
        "lenient_reading_version": LENIENT_READING_VERSION,
        "defense_tests": defense,
        "model_tests": attack_contrasts,
        "secondary": secondary,
        "lenient_calibration": calibration,
        "power": power,
        "precision": precision,
        "smallest_significant_split": smallest_significant_split(),
    }
    (output_dir / "stats.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    pd.DataFrame([_flat(item) for item in defense]).to_csv(
        output_dir / "defense_tests.csv", index=False
    )
    pd.DataFrame([_flat(item) for item in attack_contrasts]).to_csv(
        output_dir / "model_tests.csv", index=False
    )
    pd.DataFrame(secondary).to_csv(output_dir / "secondary_readings.csv", index=False)
    pd.DataFrame(power).to_csv(output_dir / "power.csv", index=False)
    if calibration["disagreements"]:
        pd.DataFrame(calibration["disagreements"]).to_csv(
            output_dir / "lenient_disagreements.csv", index=False
        )
    (output_dir / "stats.md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def _flat(item: dict[str, Any]) -> dict[str, Any]:
    flat = {key: value for key, value in item.items() if key not in {"mcnemar", "bootstrap"}}
    flat["mcnemar_p"] = item["mcnemar"]["p_value"]
    flat["bootstrap_difference"] = item["bootstrap"]["difference"]
    flat["bootstrap_low"] = item["bootstrap"]["low"]
    flat["bootstrap_high"] = item["bootstrap"]["high"]
    return flat


def _p(value: float) -> str:
    return "<0.001" if value < 0.001 else f"{value:.3f}"


def _diff(boot: dict[str, Any]) -> str:
    if boot["difference"] is None:
        return "n/a"
    return f"{boot['difference']:+.3f} [{boot['low']:+.3f}, {boot['high']:+.3f}]"


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Paired statistics",
        "",
        "Sources: " + ", ".join(f"`{source}`" for source in summary["sources"]),
        "",
        "Each row pairs the same case under two conditions (or two models). `b` counts cases "
        "where only the first side succeeded, `c` where only the second did. McNemar's exact "
        "test uses only those discordant pairs. The difference is second minus first, with a "
        "95% percentile bootstrap interval from 10,000 resamples of cases (seed 20261104). "
        "Holm-adjusted p-values control the chance of any false positive within each family "
        "of tests listed in the `family_size` column of the CSV.",
        "",
        f"With alpha 0.05, a McNemar test needs at least {summary['smallest_significant_split']} "
        "discordant pairs, all in the same direction, before it can reject. Fewer than that "
        "cannot reach p <= 0.05 whatever the split.",
        "",
        "## Conditions against each other, within each model",
        "",
        "| Model | Contrast | Field | Uncertain counted as | Pairs | First | Second | b | c | "
        "p | Holm p | Difference [95% bootstrap] |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary["defense_tests"]:
        lines.append(
            f"| `{item['model']}` | {item['contrast']} | {item['field']} | "
            f"{item['uncertain_counted_as']} | {item['pairs']} | {item['first_successes']} | "
            f"{item['second_successes']} | {item['only_first']} | {item['only_second']} | "
            f"{_p(item['mcnemar']['p_value'])} | {_p(item['holm_p_value'])} | "
            f"{_diff(item['bootstrap'])} |"
        )
    lines += [
        "",
        "## Models against each other, attack success on the same cases",
        "",
        "| Condition | First model | Second model | Pairs | First | Second | b | c | p | "
        "Holm p | Difference [95% bootstrap] |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summary["model_tests"]:
        lines.append(
            f"| {item['condition']} | `{item['first_model']}` | `{item['second_model']}` | "
            f"{item['pairs']} | {item['first_successes']} | {item['second_successes']} | "
            f"{item['only_first']} | {item['only_second']} | {_p(item['mcnemar']['p_value'])} | "
            f"{_p(item['holm_p_value'])} | {_diff(item['bootstrap'])} |"
        )
    if summary["power"]:
        lines += [
            "",
            f"## Power with {summary['power'][0]['pairs']} attack pairs",
            "",
            "Chance that an exact McNemar test at alpha 0.05 rejects, if the defense removes "
            "the stated share of attack successes and newly causes successes on `p_c` of cases.",
            "",
            "| Reduction | p_c | Power |",
            "| ---: | ---: | ---: |",
        ]
        for item in summary["power"]:
            lines.append(f"| {item['reduction']:.2f} | {item['p_c']:.2f} | {item['power']:.2f} |")
        lines += [
            "",
            "Wilson intervals at this denominator:",
            "",
            "| Count | Interval |",
            "| --- | --- |",
        ]
        for item in summary["precision"]:
            lines.append(
                f"| {item['successes']}/{item['n']} | [{item['low']:.3f}, {item['high']:.3f}] |"
            )
    lines += [
        "",
        "## Secondary readings",
        "",
        f"Lenient task reading `{summary['lenient_reading_version']}` and the tool-call text "
        "proxy. Neither replaces the strict headline.",
        "",
        "| Model | Condition | Valid | Strict task | Lenient task | Tool cases | "
        "Tool attack success | Tool uncertain | Naive parser fired |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary["secondary"]:
        lines.append(
            f"| `{item['model']}` | {item['condition']} | {item['valid_units']} | "
            f"{item['strict_task_successes']} | {item['lenient_task_successes']} | "
            f"{item['tool_cases']} | {item['tool_attack_successes']} | "
            f"{item['tool_attack_uncertain']} | {item['tool_proxy_fired']} |"
        )
    calibration = summary["lenient_calibration"]
    if calibration["per_model"]:
        lines += [
            "",
            "## Lenient reading against human task labels",
            "",
            "| Model | Reviewed | Strict agrees | Lenient agrees |",
            "| --- | ---: | --- | --- |",
        ]
        for item in calibration["per_model"]:
            lines.append(
                f"| `{item['model']}` | {item['reviewed']} | {item['strict_agreements']} "
                f"[{item['strict_ci']['low']:.3f}, {item['strict_ci']['high']:.3f}] | "
                f"{item['lenient_agreements']} "
                f"[{item['lenient_ci']['low']:.3f}, {item['lenient_ci']['high']:.3f}] |"
            )
        lines += [
            "",
            f"{len(calibration['disagreements'])} lenient disagreements are listed in "
            "`lenient_disagreements.csv`.",
        ]
    lines.append("")
    return "\n".join(lines)
