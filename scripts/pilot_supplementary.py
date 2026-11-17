#!/usr/bin/env python
"""One entry point for the pilot's supplementary (exploratory) tables. No model call.

Written 2026-11-17, after the pilot outcomes and three reviews were read: every table is
exploratory. The registered primary is recomputed only to check it is unchanged.

    python scripts/pilot_supplementary.py results-published/pilot-2026-11-16 \
        --f1 results-published/pilot-f1-2026-11-16 \
        --output results-published/pilot-2026-11-16/supplementary-2026-11-17

Writes ``analysis.json``, one CSV per table and ``tables.md``. Exits non-zero if a
registered or previously published figure that it re-derives does not match.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from prompt_injection_eval.pilot import attacks, exploratory, supplementary
from prompt_injection_eval.pilot.runner import read_traces

QWEN, GRANITE = "qwen3-32b", "granite-4.0-h-small"
CONTROL_OUTCOMES = {
    "clean": "utility",
    "scratch": "utility",
    "direct": "success",
    "twin": "success",
}

# Figures already published (pilot README, exploratory/, report draft) that must reproduce.
EXPECTED = {
    "qwen_primary_pts": 8.5714,
    "qwen_wording_pts": 7.1429,
    "qwen_format_pts": 1.4286,
    "granite_slack_baseline": ("67/105", "57/105"),
    "granite_banking_baseline": ("47/72", "35/72"),
    "granite_banking_one_line_twin": ("20/72", "28/72"),
}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {k: json.dumps(v) if isinstance(v, list | dict) else v for k, v in r.items()}
            )


def _md(rows: list[dict[str, Any]], columns: list[str]) -> str:
    def cell(key: str, v: Any) -> str:
        signed = key.endswith(("_pts", "interval")) or key == "task_interval"
        if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int | float) for x in v):
            return f"{v[0]:+.1f} to {v[1]:+.1f}" if signed else f"{v[0]:.1f} to {v[1]:.1f}"
        if isinstance(v, float):
            return f"{v:+.1f}" if signed else f"{v:.1f}"
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)

    head = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"
    return head + "".join(
        "| " + " | ".join(cell(c, r.get(c, "")) for c in columns) + " |\n" for r in rows
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--f1", type=Path, required=True, help="F1 bundle (Qwen's dev controls)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    phases: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for label in (QWEN, GRANITE):
        root = args.bundle / label
        dev = (args.f1 if label == QWEN else args.bundle) / label / "dev-controls"
        phases[label] = {
            "select": read_traces(root / "select" / "traces.jsonl"),
            "evaluate": read_traces(root / "evaluate" / "traces.jsonl"),
            "eval-controls": read_traces(root / "eval-controls" / "traces.jsonl"),
            "dev-controls": read_traces(dev / "traces.jsonl"),
        }
    frozen = {
        label: json.loads((args.bundle / label / "select" / "frozen_attacks.json").read_text())
        for label in (QWEN, GRANITE)
    }

    out: dict[str, Any] = {
        "status": (
            "exploratory, not pre-registered; written 2026-11-17 after the pilot outcomes and "
            "three external reviews were read. The registered primary is unchanged."
        ),
        "denominators": (
            "first_run tables: run 0 of each case only. all_runs tables: every completed final "
            "trace (repeats included). Banking selection has one run per cell, so its two "
            "denominators coincide. Superseded infra_error traces never enter an outcome."
        ),
        "round_limit": (
            "Episodes reaching the 15-round limit are completed, scored, finite-budget outcomes. "
            "They stay in every denominator and are also counted separately."
        ),
        "intervals": (
            "task bootstrap (user tasks resampled, goals kept), 5000 replicates, seed 20261115"
        ),
    }

    # Registered and previously published figures, re-derived.
    q = phases[QWEN]["evaluate"]
    qt, qj = frozen[QWEN]["selected"]["text"], frozen[QWEN]["selected"]["json"]
    decomposition = {c.name: c for c in exploratory.decomposition(q, qt, qj, QWEN)}
    names = list(decomposition)
    checks = {
        "qwen_primary_pts": round(decomposition[names[0]].estimate, 4),
        "qwen_wording_pts": round(decomposition[names[1]].estimate, 4),
        "qwen_format_pts": round(decomposition[names[2]].estimate, 4),
    }
    for key, label, phase, attack in (
        ("granite_slack_baseline", GRANITE, "evaluate", attacks.BASELINE),
        ("granite_banking_baseline", GRANITE, "select", attacks.BASELINE),
        ("granite_banking_one_line_twin", GRANITE, "select", supplementary.ONE_LINE_TWIN),
    ):
        rows = phases[label][phase]
        checks[key] = tuple(
            "{}/{}".format(*supplementary._count(rows, attack, f, "security", 0))
            for f in ("text", "json")
        )
    out["reproduction_checks"] = {
        k: {
            "expected": EXPECTED[k],
            "found": v,
            "match": (abs(v - EXPECTED[k]) < 1e-3) if isinstance(v, float) else v == EXPECTED[k],
        }
        for k, v in checks.items()
    }
    out["decomposition_names"] = names

    shapes = {
        label: supplementary.attack_shapes(phases[label]["select"]) for label in (QWEN, GRANITE)
    }
    out["attack_groups"] = {
        "definition": "multiline: payload.strip() contains a newline",
        "shapes": shapes[QWEN],
        "groups": supplementary.groups(shapes[QWEN]),
    }

    tables: dict[str, list[dict[str, Any]]] = {
        "banking_matrix": [],
        "slack_matrix": [],
        "group_aggregates": [],
        "twin_contrasts": [],
        "joint_outcomes": [],
        "per_goal": [],
        "budget_first_run": [],
        "budget_all_runs": [],
        "repeatability_clustered": [],
    }
    out["twin_payload_check"] = {}
    out["prompt_verification_scope"] = {}
    for label in (QWEN, GRANITE):
        sel, ev = phases[label]["select"], phases[label]["evaluate"]
        tables["banking_matrix"] += supplementary.attack_matrix(sel, label, "banking")
        tables["slack_matrix"] += supplementary.attack_matrix(ev, label, "slack")
        tables["group_aggregates"] += supplementary.group_aggregates(sel, label, "banking")
        tables["group_aggregates"] += supplementary.group_aggregates(ev, label, "slack")
        tables["twin_contrasts"] += supplementary.twin_contrasts(sel, label, "banking")
        tables["twin_contrasts"] += supplementary.twin_contrasts(ev, label, "slack")
        out["twin_payload_check"][label] = {
            "banking": supplementary.twin_payload_check(sel),
            "slack": supplementary.twin_payload_check(ev),
        }
        tables["joint_outcomes"] += supplementary.joint_outcomes(sel, label, "banking")
        tables["joint_outcomes"] += supplementary.joint_outcomes(ev, label, "slack")
        tables["per_goal"] += supplementary.per_goal(sel, label, "banking")
        tables["per_goal"] += supplementary.per_goal(ev, label, "slack")
        for phase, rows in phases[label].items():
            tables["budget_first_run"] += supplementary.budget(rows, label, phase, True)
            tables["budget_all_runs"] += supplementary.budget(rows, label, phase, False)
        for outcome in ("security", "utility"):
            tables["repeatability_clustered"].append(
                {
                    "outcome": outcome,
                    **supplementary.clustered_disagreement(
                        ev, label, "evaluate", ("attack",), {"attack": outcome}
                    ),
                }
            )
        for phase in ("eval-controls", "dev-controls"):
            tables["repeatability_clustered"].append(
                {
                    "outcome": "per mode",
                    **supplementary.clustered_disagreement(
                        phases[label][phase],
                        label,
                        phase,
                        tuple(CONTROL_OUTCOMES),
                        CONTROL_OUTCOMES,
                    ),
                }
            )
        out["prompt_verification_scope"][label] = {
            phase: supplementary.prompt_verification_scope(rows)
            for phase, rows in phases[label].items()
        }
    out["tables"] = tables

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "analysis.json").write_text(json.dumps(out, indent=2) + "\n")
    for name, rows in tables.items():
        _write_csv(args.output / f"{name}.csv", rows)

    md = [
        "# Supplementary pilot tables (exploratory, 2026-11-17)\n",
        "Generated by `scripts/pilot_supplementary.py` from stored traces. Not pre-registered. "
        "See the README in this directory for definitions and reading.\n",
        "## Reproduction checks\n",
        _md(
            [{"figure": k, **v} for k, v in out["reproduction_checks"].items()],
            ["figure", "expected", "found", "match"],
        ),
    ]
    sections = (
        (
            "Banking attack x format matrix (selection phase, 72 pairs, one run)",
            "banking_matrix",
            [
                "model",
                "attack",
                "multiline",
                "text_attack_success",
                "json_attack_success",
                "text_minus_json_pts",
                "task_interval",
                "text_utility_under_attack",
                "json_utility_under_attack",
            ],
        ),
        (
            "Slack matrix (evaluated attacks, first runs, 105 pairs)",
            "slack_matrix",
            [
                "model",
                "attack",
                "multiline",
                "text_attack_success",
                "json_attack_success",
                "text_minus_json_pts",
                "task_interval",
                "text_utility_under_attack",
                "json_utility_under_attack",
            ],
        ),
        (
            "Attack groups (pooled counts; descriptive, cells share pairs)",
            "group_aggregates",
            [
                "model",
                "suite",
                "group",
                "text_attack_success",
                "json_attack_success",
                "text_minus_json_pts",
                "attacks_where_json_lower",
                "attacks_where_json_higher",
            ],
        ),
        (
            "Baseline vs one-line twin, paired on the same cases",
            "twin_contrasts",
            [
                "model",
                "suite",
                "contrast",
                "cases",
                "estimate_pts",
                "task_interval",
                "only_first_succeeded",
                "only_second_succeeded",
            ],
        ),
        (
            "Joint security x utility outcomes (first runs)",
            "joint_outcomes",
            [
                "model",
                "suite",
                "condition",
                "cases",
                "attacked+task_done",
                "attacked+task_failed",
                "resisted+task_done",
                "resisted+task_failed",
                "of_which_round_limit",
            ],
        ),
        (
            "Round limit, calls and tokens: first runs",
            "budget_first_run",
            [
                "model",
                "phase",
                "condition",
                "episodes",
                "round_limit",
                "round_limit_with_positive_outcome",
                "model_calls_mean",
                "model_calls_max",
                "prompt_tokens_mean",
                "completion_tokens_mean",
                "last_prompt_tokens_max",
            ],
        ),
        (
            "Round limit, calls and tokens: all completed runs",
            "budget_all_runs",
            [
                "model",
                "phase",
                "condition",
                "episodes",
                "round_limit",
                "round_limit_with_positive_outcome",
                "model_calls_mean",
                "prompt_tokens_mean",
            ],
        ),
        (
            "Repeat disagreement, clustered by case",
            "repeatability_clustered",
            [
                "model",
                "phase",
                "outcome",
                "repeated_cases",
                "repeated_cells",
                "disagreeing_cells",
                "cell_share_pct",
                "cases_with_any_disagreement",
                "case_share_exact_interval_pct",
                "cell_share_case_bootstrap_pct",
            ],
        ),
        (
            "Per-goal format effects",
            "per_goal",
            [
                "model",
                "suite",
                "attack",
                "goal",
                "text_successes",
                "json_successes",
                "text_minus_json_pts",
            ],
        ),
    )
    for title, key, columns in sections:
        md += [f"\n## {title}\n", _md(tables[key], columns)]
    md += [
        "\n## Twin payload check\n",
        "```json\n" + json.dumps(out["twin_payload_check"], indent=1) + "\n```\n",
        "\n## Prompt-verification scope (turns reconstructible from stored history)\n",
        "```json\n" + json.dumps(out["prompt_verification_scope"], indent=1) + "\n```\n",
    ]
    (args.output / "tables.md").write_text("".join(md))

    failed = [k for k, v in out["reproduction_checks"].items() if not v["match"]]
    print(json.dumps(out["reproduction_checks"], indent=1))
    if failed:
        print(f"MISMATCH: {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
