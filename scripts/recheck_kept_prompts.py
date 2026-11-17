#!/usr/bin/env python
"""Run the contract checker on every full prompt the pilot kept. No inference.

The pilot kept the server-returned prompt for a sample of turns (``rendered_prompts``).
Each is checked against the request rebuilt from the trace's stored conversation, under
the model's template profile. In JSON traces the records are the decoded tool contents.
In text traces they cannot be recovered without the record shapes, so the record items
(K5 record equality, K7 payload) are skipped and counted as skipped.

    python scripts/recheck_kept_prompts.py results-published/pilot-2026-11-16 \
        results-published/pilot-f1-2026-11-16 --output <file>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval.pilot import adapter, delivery  # noqa: E402
from prompt_injection_eval.pilot.runner import read_traces  # noqa: E402

PROFILE = {"qwen3-32b": "qwen3", "granite-4.0-h-small": "granite4"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundles", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tally: Counter[str] = Counter()
    failures = []
    for bundle in args.bundles:
        for path in sorted(bundle.glob("*/*/traces.jsonl")):
            label, phase = path.parts[-3], path.parts[-2]
            if label not in PROFILE:
                continue
            for trace in read_traces(path):
                kept = trace.get("rendered_prompts") or []
                if not kept:
                    continue
                tools = list(adapter.wire_tools(trace["suite"]))
                messages = trace["messages"]
                positions = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
                positions = positions[len(trace["prefix_calls"]) :]
                for step, prompt in enumerate(kept):
                    if prompt is None or step >= len(positions):
                        tally["kept_without_reconstructible_request"] += 1
                        continue
                    request = messages[: positions[step]]
                    tool_idx = [i for i, m in enumerate(request) if m["role"] == "tool"]
                    records = (
                        {i: json.loads(request[i]["content"]) for i in tool_idx}
                        if trace["fmt"] == "json"
                        else None
                    )
                    carrier = 3 + 2 * trace["injection_index"] if trace["payload"] else None
                    defects = delivery.check_contract(
                        prompt,
                        request,
                        tools,
                        records,
                        trace["fmt"],
                        trace["payload"] if carrier in tool_idx else None,
                        carrier if carrier in tool_idx else None,
                        profile=PROFILE[label],
                    )
                    tally["checked"] += 1
                    tally[f"checked_{trace['fmt']}"] += 1
                    tally["record_items_skipped"] += records is None
                    if defects:
                        tally["defects"] += 1
                        failures.append(
                            {
                                "phase": f"{label}/{phase}",
                                "unit": trace["unit_key"],
                                "step": step,
                                "defects": defects,
                            }
                        )
    out = {"tally": dict(sorted(tally.items())), "failures": failures[:50]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["tally"], indent=1))
    if failures:
        print(json.dumps(failures[:5], indent=1))


if __name__ == "__main__":
    main()
