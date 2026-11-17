#!/usr/bin/env python
"""Cost of the OpenRouter screen, from real request sizes and the pinned prices. No call.

Builds each screen unit's first request offline (scripted stand-in), measures it, and grows
it turn by turn as an episode would. Cumulative input is counted: every call resends the
whole conversation and the tool schemas. Reasoning is billed as output, inside max_tokens.

    python scripts/cost_screen.py --output data/screen/cost_estimate.json
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval.pilot import episode, screen  # noqa: E402
from prompt_injection_eval.pilot.scripted import ScriptedProvider  # noqa: E402
from prompt_injection_eval.providers.openrouter import ENDPOINTS  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = episode.Settings(model="scripted", label="s", profile="scripted", study=screen.STAGE)
    first_chars, per_turn_chars, calls = [], [], []
    for unit in screen.units():
        with contextlib.redirect_stdout(io.StringIO()):
            trace = episode.run(unit, ScriptedProvider("benign"), settings)
        tools = json.dumps(list(episode.adapter.wire_tools(unit.suite)))
        msgs = trace["messages"]
        first = len(json.dumps(msgs[: 4 + 2 * trace["injection_index"]])) + len(tools)
        total = len(json.dumps(msgs)) + len(tools)
        first_chars.append(first)
        per_turn_chars.append(max(1, (total - first) / max(1, len(trace["turns"]))))
        calls.append(len(trace["turns"]))
    price_in = max(e.prompt_usd_per_token for e in ENDPOINTS.values())
    price_out = max(e.completion_usd_per_token for e in ENDPOINTS.values())
    max_out = max(e.params["max_tokens"] for e in ENDPOINTS.values())
    n = len(screen.units()) * len(screen.MODELS) + len(screen.calibration()) * len(screen.MODELS)

    def episode_cost(
        calls_per: float, chars_per_token: float, out_tokens: float, growth: float
    ) -> float:
        cost = 0.0
        size = sum(first_chars) / len(first_chars)
        for _ in range(int(round(calls_per))):
            cost += size / chars_per_token * price_in + out_tokens * price_out
            size += growth
        return cost

    growth = sum(per_turn_chars) / len(per_turn_chars)
    central = n * episode_cost(4, 4.0, 600, growth + 600 * 4)
    high = n * 1.1 * episode_cost(16, 3.0, 2048, growth + 2048 * 4)
    worst = n * 3 * episode_cost(16, 2.0, max_out, growth + max_out * 4)  # 3 attempts per call
    out = {
        "episodes_including_calibration": n,
        "measured": {
            "first_request_chars_mean": round(sum(first_chars) / len(first_chars)),
            "first_request_chars_max": max(first_chars),
            "reference_calls_per_episode_mean": round(sum(calls) / len(calls), 2),
        },
        "prices_usd_per_token": {
            "prompt": price_in,
            "completion": price_out,
            "source": "OpenRouter endpoints API, 2026-11-17",
        },
        "central_usd": round(central, 2),
        "central_assumptions": "4 calls/episode, 4 chars/token, 600 output tokens incl. reasoning per call",
        "high_usd": round(high, 2),
        "high_assumptions": "every episode reaches 16 calls, 10% retried, 3 chars/token, 2048 output tokens per call",
        "worst_case_usd_unbounded": round(worst, 2),
        "worst_case_assumptions": "16 calls/episode, 3 attempts each, 2 chars/token, every call at max_tokens",
        "enforced_cap_usd": screen.CAP_USD,
        "enforcement": "SpendGuard reserves each attempt's worst case before sending; calls stop at the cap",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
