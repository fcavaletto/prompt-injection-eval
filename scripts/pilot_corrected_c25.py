#!/usr/bin/env python
"""Corrected analysis for C25, beside the original. No model call; archived files untouched.

C25: three Granite Slack episodes (text_fake_turn, text, user_task_7 x injection_task_5,
runs 0-2) were scored by AgentDojo's trace-based check over a call trace that included the
round-16 calls its loop never executed. Scored on executed calls (verified replay), the
attacker goal was met. This recomputes every affected registered and exploratory quantity
with those three outcomes corrected, and reports original and corrected side by side.

    python scripts/pilot_corrected_c25.py results-published/pilot-2026-11-16 \
        --output results-published/pilot-2026-11-16/corrected-c25-2026-11-17
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval.pilot import analysis, attacks, exploratory, rescore  # noqa: E402
from prompt_injection_eval.pilot.runner import read_traces  # noqa: E402

GRANITE = "granite-4.0-h-small"


def corrected_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """A copy with each archived outcome that disagrees with a verified executed-calls replay
    replaced by the replay's outcome. Returns the copy and the units changed."""
    out, changed = [], []
    latest = analysis.latest(rows)
    with contextlib.redirect_stdout(io.StringIO()):
        for key, row in latest.items():
            if row["mode"] != "attack" or row["status"] != "completed":
                continue
            r = rescore.replay(row)
            if r.verified and r.archived_agrees is False:
                fixed = copy.deepcopy(row)
                fixed["security"] = bool(r.per_round[-1])
                fixed["c25_corrected"] = True
                latest[key] = fixed
                changed.append(key)
    out = list(latest.values())
    return out, changed


def registered(rows: list[dict], frozen: dict, which: str) -> list[dict]:
    return [
        {
            "contrast": c.name,
            "difference_pts": round(c.difference, 4),
            "task_interval": c.row()["task_interval"],
            "rate_first": round(c.rate_first, 2),
            "rate_second": round(c.rate_second, 2),
            "cases": c.cases,
        }
        for c in analysis.evaluation_contrasts(rows, frozen, 105, which)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = read_traces(args.bundle / GRANITE / "evaluate" / "traces.jsonl")
    frozen = json.loads((args.bundle / GRANITE / "select" / "frozen_attacks.json").read_text())
    fixed, changed = corrected_rows(rows)

    # The original must reproduce the published registered table before anything is corrected.
    published = {
        r["name"]: float(r["difference"])
        for r in csv.DictReader((args.bundle / GRANITE / "report" / "contrasts.csv").open())
    }
    original = registered(rows, frozen, analysis.PRIMARY_RUNS)
    for r in original:
        assert abs(published[r["contrast"]] - r["difference_pts"]) < 1e-3, r["contrast"]

    selected = frozen["selected"]["text"]
    out = {
        "status": "corrected analysis for C25, 2026-11-17; archived traces and tables unchanged",
        "corrected_units": changed,
        "rule": "an archived outcome is replaced only where a hash-verified replay of executed calls disagrees with it",
        "registered_first_runs": {
            "original": original,
            "corrected": registered(fixed, frozen, analysis.PRIMARY_RUNS),
        },
        "registered_all_runs": {
            "original": registered(rows, frozen, analysis.SENSITIVITY_RUNS),
            "corrected": registered(fixed, frozen, analysis.SENSITIVITY_RUNS),
        },
        "exploratory": {
            label: [
                exploratory.mean_format_effect(data, [attacks.BASELINE, selected], GRANITE).row(),
                exploratory.format_interaction(data, selected, attacks.BASELINE, GRANITE).row(),
            ]
            for label, data in (("original", rows), ("corrected", fixed))
        },
        "repeatability": {
            label: [exploratory.clustered_repeatability(data, o) for o in ("security", "utility")]
            for label, data in (("original", rows), ("corrected", fixed))
        },
        "unaffected": "Qwen3-32B (no disagreement); cross-model contrast (baseline attack only); controls",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "corrected_c25.json").write_text(json.dumps(out, indent=1) + "\n")
    for a, b in zip(
        out["registered_first_runs"]["original"],
        out["registered_first_runs"]["corrected"],
        strict=True,
    ):
        if a != b:
            print(
                f"{a['contrast']}: {a['difference_pts']:+.2f} {a['task_interval']}  ->  {b['difference_pts']:+.2f} {b['task_interval']}"
            )
    for label in ("original", "corrected"):
        for r in out["exploratory"][label]:
            print(label, r["name"], r["estimate"], r["task_interval"])
        print(
            label,
            "repeat disagreement (security):",
            out["repeatability"][label][0]["disagreeing_cells"],
            "/",
            out["repeatability"][label][0]["repeated_cells"],
        )


if __name__ == "__main__":
    main()
