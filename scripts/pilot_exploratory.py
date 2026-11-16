"""Exploratory re-analysis of the two-model serialization pilot, from stored traces only.

Not pre-registered: written after the pilot's outcomes were known. Writes
``exploratory.json`` and ``goal_rates.csv`` to the output directory. Reads the evaluate
phase of each model and its frozen selection; makes no model call.

    python scripts/pilot_exploratory.py results-published/pilot-2026-11-16 \
        --output results-published/pilot-2026-11-16/exploratory
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from prompt_injection_eval.pilot import attacks, exploratory
from prompt_injection_eval.pilot.runner import read_traces

QWEN, GRANITE = "qwen3-32b", "granite-4.0-h-small"


def load(bundle: Path, label: str) -> tuple[list[dict], dict]:
    rows = read_traces(bundle / label / "evaluate" / "traces.jsonl")
    frozen = json.loads((bundle / label / "select" / "frozen_attacks.json").read_text())
    return rows, frozen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = attacks.BASELINE

    q_rows, q_frozen = load(args.bundle, QWEN)
    g_rows, g_frozen = load(args.bundle, GRANITE)
    qt, qj = q_frozen["selected"]["text"], q_frozen["selected"]["json"]
    gs = g_frozen["selected"]["text"]
    assert g_frozen["selected"]["json"] == gs and qt != qj

    results = {
        QWEN: [
            *exploratory.decomposition(q_rows, qt, qj, QWEN),
            exploratory.mean_format_effect(q_rows, [base, qt, qj], QWEN),
            exploratory.format_interaction(q_rows, qt, base, QWEN),
            exploratory.format_interaction(q_rows, qj, base, QWEN),
        ],
        GRANITE: [
            exploratory.mean_format_effect(g_rows, [base, gs], GRANITE),
            exploratory.format_interaction(g_rows, gs, base, GRANITE),
        ],
        "cross-model": [
            exploratory.cross_model_format_difference(
                g_rows, q_rows, base, base, ("Granite", "Qwen")
            ),
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    out = {
        "status": "exploratory, not pre-registered; written after the pilot outcomes were known",
        "cases": "first runs only, 105 Slack pairs, equal weight per pair (Amendment 3 primary)",
        "units": "percentage points of attack success; text minus JSON for format terms",
        "intervals": {
            "task": "user tasks resampled, goals kept (registered primary estimator)",
            "two_way": "user tasks and goals resampled; 5 goals, shown for width only",
            "sign_flip_p": "per-task means, sign-flipped; conditional on the 5 goals",
        },
        "selected": {QWEN: {"text": qt, "json": qj}, GRANITE: {"text": gs, "json": gs}},
        "contrasts": {k: [c.row() for c in v] for k, v in results.items()},
        "repeatability_clustered": {
            label: [exploratory.clustered_repeatability(rows, o) for o in ("security", "utility")]
            for label, rows in ((QWEN, q_rows), (GRANITE, g_rows))
        },
    }
    (args.output / "exploratory.json").write_text(json.dumps(out, indent=2) + "\n")
    with (args.output / "goal_rates.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, ["model", "attack", "format", "goal", "successes", "cases", "rate"]
        )
        writer.writeheader()
        for label, rows, attack_list in (
            (QWEN, q_rows, [base, qt, qj]),
            (GRANITE, g_rows, [base, gs]),
        ):
            for line in exploratory.goal_rates(rows, attack_list):
                writer.writerow({"model": label, **line})
    for group, found in results.items():
        print(f"## {group}")
        for c in found:
            r = c.row()
            print(
                f"{r['estimate']:+6.2f}"
                f"  task [{r['task_interval'][0]:+.1f}, {r['task_interval'][1]:+.1f}]"
                f"  two-way [{r['two_way_interval'][0]:+.1f}, {r['two_way_interval'][1]:+.1f}]"
                f"  p={r['sign_flip_p']:.3f}  {r['name']}"
            )
            print(
                "        per goal: "
                + ", ".join(f"{g[-1]}:{v:+.0f}" for g, v in r["per_goal"].items())
            )


if __name__ == "__main__":
    main()
