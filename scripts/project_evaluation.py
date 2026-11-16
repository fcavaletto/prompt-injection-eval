#!/usr/bin/env python
"""Project a model's Slack phases from its own development data, before any Slack episode.

Pilot design, sections 9.5 and 9.6c. For each evaluated condition (attack x format), the
evaluation's episodes are projected at the selection phase's mean model calls per episode
for that attack and format, times the Slack attack factor (2.2), capped at the round limit
(16 calls). Slack controls are projected at the development controls' mean calls times 2.0.
Calls are divided by the aggregate rate the selection phase measured (calls over wall-clock
seconds, from runs.jsonl). The phase deadline is 1.3 times the projection.

    python scripts/project_evaluation.py --select-dir D --controls-dir C --frozen F \\
        [--dollars-per-hour 2.7105] --output projection.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SLACK_ATTACK_FACTOR = 2.2
SLACK_CONTROL_FACTOR = 2.0
ROUND_LIMIT_CALLS = 16
DEADLINE_FACTOR = 1.3


def _rate(phase_dir: Path) -> float:
    runs = [json.loads(line) for line in (phase_dir / "runs.jsonl").read_text().splitlines()]
    calls = sum(r["model_calls"] for r in runs)
    seconds = sum(r["seconds"] for r in runs)
    return calls / seconds


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--select-dir", type=Path, required=True)
    parser.add_argument("--controls-dir", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--dollars-per-hour", type=float, default=2.69 + 150 * 0.10 / 730)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from prompt_injection_eval.pilot import runner

    frozen = json.loads(args.frozen.read_text())
    select_rows = runner.read_traces(args.select_dir / "traces.jsonl")
    control_rows = runner.read_traces(args.controls_dir / "traces.jsonl")
    calls: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in select_rows:
        if row["status"] == "completed":
            calls[(row["attack"], row["fmt"])].append(row["totals"]["model_calls"])
    mean = {k: sum(v) / len(v) for k, v in calls.items()}
    control_calls = [r["totals"]["model_calls"] for r in control_rows if r["status"] == "completed"]
    control_mean = sum(control_calls) / len(control_calls)
    rate = _rate(args.select_dir)

    evaluate = runner.plan("evaluate", frozen)
    eval_calls = 0.0
    by_condition = {}
    for (attack, fmt), n in (
        (key, sum(1 for u in evaluate if (u.attack, u.fmt) == key))
        for key in sorted({(u.attack, u.fmt) for u in evaluate})
    ):
        per = min(ROUND_LIMIT_CALLS, SLACK_ATTACK_FACTOR * mean[(attack, fmt)])
        by_condition[f"{attack}/{fmt}"] = {
            "episodes": n,
            "development_calls": mean[(attack, fmt)],
            "projected_calls": per,
        }
        eval_calls += n * per
    controls = runner.plan("eval-controls")
    control_projected = len(controls) * min(ROUND_LIMIT_CALLS, SLACK_CONTROL_FACTOR * control_mean)
    minutes = {
        "eval-controls": control_projected / rate / 60,
        "evaluate": eval_calls / rate / 60,
    }
    out = {
        "select_rate_calls_per_second": rate,
        "development_control_calls_per_episode": control_mean,
        "evaluate_episodes": len(evaluate),
        "eval_controls_episodes": len(controls),
        "by_condition": by_condition,
        "projected_calls": {"eval-controls": control_projected, "evaluate": eval_calls},
        "projected_minutes": minutes,
        "deadline_minutes": {k: DEADLINE_FACTOR * v for k, v in minutes.items()},
        "projected_cost_usd": {k: v / 60 * args.dollars_per_hour for k, v in minutes.items()},
        "dollars_per_hour": args.dollars_per_hour,
    }
    args.output.write_text(json.dumps(out, indent=1) + "\n")
    print(
        json.dumps(
            {
                k: out[k]
                for k in (
                    "select_rate_calls_per_second",
                    "projected_minutes",
                    "deadline_minutes",
                    "projected_cost_usd",
                )
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
