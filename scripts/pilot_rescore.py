#!/usr/bin/env python
"""Exploratory per-round rescoring of the archived pilot, by replaying stored calls. No model.

    python scripts/pilot_rescore.py results-published/pilot-2026-11-16 \
        --output results-published/pilot-2026-11-16/rescoring-2026-11-17

The archived final-state outcome stays the primary measure. See ``pilot/rescore.py`` for
the definition of a round and what an unsuccessful episode does and does not show.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval.pilot import rescore  # noqa: E402
from prompt_injection_eval.pilot.analysis import latest  # noqa: E402
from prompt_injection_eval.pilot.runner import read_traces  # noqa: E402

BUDGETS = (1, 2, 4, 8, 12, 16)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary: dict = {
        "status": "exploratory, 2026-11-17; the archived final-state outcome is the primary measure",
        "round": "round k = the k-th model response plus execution of its tool calls; round 0 = after the replayed prefix",
        "states": "re-executed from recorded calls; verified when the final state hash equals the recorded one",
        "phases": {},
    }
    table = []
    disagreements = []
    for model in ("qwen3-32b", "granite-4.0-h-small"):
        for phase in ("select", "evaluate"):
            rows = [
                r
                for r in latest(read_traces(args.bundle / model / phase / "traces.jsonl")).values()
                if r["mode"] == "attack"
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                res = [rescore.replay(r) for r in rows]
            summary["phases"][f"{model}/{phase}"] = {
                "attack_episodes": len(res),
                "state_verified": sum(r.verified for r in res),
                "unverified_reasons": dict(Counter(r.reason for r in res if not r.verified)),
                "archived_disagrees": sum(r.archived_agrees is False for r in res),
                "ever_but_not_final": sum(
                    bool(r.ever_succeeded) and not r.per_round[-1] for r in res if r.verified
                ),
                "succeeded_before_round_1": sum(r.verified and r.per_round[0] for r in res),
            }
            disagreements += [
                {
                    "model": model,
                    "phase": phase,
                    "unit": r.unit_key,
                    "archived": r.archived_outcome,
                    "executed_calls_check": r.per_round[-1],
                    "first_success_round": r.first_success_round,
                    "termination": r.termination,
                }
                for r in res
                if r.archived_agrees is False
            ]
            groups: dict[tuple[str, int | str], list] = defaultdict(list)
            for r in res:
                if r.verified:
                    groups[(r.condition, "first_run" if r.run == 0 else "repeat")].append(r)
            for (condition, runs), found in sorted(groups.items()):
                if runs != "first_run":
                    continue
                n = len(found)
                line = {
                    "model": model,
                    "phase": phase,
                    "condition": condition,
                    "verified_first_runs": n,
                }
                for b in BUDGETS:
                    line[f"succeeded_by_round_{b}"] = sum(
                        x.first_success_round is not None and x.first_success_round <= b
                        for x in found
                    )
                line["ever"] = sum(bool(x.ever_succeeded) for x in found)
                line["final_archived"] = sum(bool(x.archived_outcome) for x in found)
                for t, c in Counter(rescore.censoring(x) for x in found).items():
                    line[t] = c
                line["round_limit"] = sum(x.termination == "round_limit" for x in found)
                table.append(line)
    args.output.mkdir(parents=True, exist_ok=True)
    summary["archived_disagreements"] = disagreements
    (args.output / "rescoring.json").write_text(json.dumps(summary, indent=1) + "\n")
    keys = list(dict.fromkeys(k for r in table for k in r))
    with (args.output / "per_round.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, keys)
        w.writeheader()
        w.writerows(table)
    print(json.dumps({k: v for k, v in summary.items() if k != "status"}, indent=1))


if __name__ == "__main__":
    main()
