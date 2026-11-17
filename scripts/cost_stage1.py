#!/usr/bin/env python
"""Cost of Stage 1 and of the adaptive follow-up, from measured pilot figures. No inference.

Calls per episode come from Granite's stored pilot traces (first runs, completed). The
throughput and startup time come from Granite's run record. The hourly price is passed in
and must be read from the provider's catalogue immediately before any rental.

    python scripts/cost_stage1.py --price 2.69 --output data/stage1/cost_estimate.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval.pilot import stage1  # noqa: E402
from prompt_injection_eval.pilot.analysis import latest  # noqa: E402
from prompt_injection_eval.pilot.runner import read_traces  # noqa: E402

G = ROOT / "results-published" / "pilot-2026-11-16" / "granite-4.0-h-small"
DISK_PER_HOUR = 150 * 0.10 / 730  # 150 GB container disk at $0.10 per GB-month
ONE_LINE = (
    "json_field_mimic",
    "json_single_line_authority",
    "json_key_value_prose",
    "neutral_pass_on",
)


def mean_calls(phase: str, keep) -> float:  # noqa: ANN001
    rows = [
        r
        for r in latest(read_traces(G / phase / "traces.jsonl")).values()
        if r["status"] == "completed" and r["run"] == 0 and keep(r)
    ]
    return statistics.fmean(r["totals"]["model_calls"] for r in rows)


def session_minutes(startup: float) -> float:
    return startup + 1 + 2 + 5  # rendering check, idle, shutdown margin


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--price", type=float, required=True, help="USD per GPU-hour, read today")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = json.loads((ROOT / "results-published/pilot-2026-11-16/run_record.json").read_text())
    g = run["granite-4.0-h-small"]["phases"]
    rates = [
        g["dev-controls"]["rate_calls_per_second"],
        g["select"]["rate_calls_per_second"],
        g["eval-controls"]["rate_calls_per_second"],
        *g["evaluate"]["rates_calls_per_second"],
    ]

    measured = {
        "banking_instruction": mean_calls(
            "select",
            lambda r: r["attack"] in (stage1.attacks.BASELINE, "neutral_baseline_one_line"),
        ),
        "slack_instruction": mean_calls(
            "evaluate", lambda r: r["attack"] == stage1.attacks.BASELINE
        ),
        "banking_one_line_proxy_for_forged": mean_calls(
            "select", lambda r: r["attack"] in ONE_LINE
        ),
        "banking_clean": mean_calls("dev-controls", lambda r: r["mode"] == "clean"),
        "slack_clean": mean_calls("eval-controls", lambda r: r["mode"] == "clean"),
        "throughput_calls_per_second": {"min": min(rates), "max": max(rates)},
        "startup_minutes": 5.98,  # created 12:58:12, healthy 13:04:11 (run_record)
    }
    units = stage1.units()
    calls_central = 0.0
    for u in units:
        if u.mode == "clean":
            calls_central += measured[f"{u.suite}_clean"]
        elif u.attack in stage1.FORGED_TWINS:
            calls_central += (
                measured["banking_one_line_proxy_for_forged"]
                if u.suite == "banking"
                else measured["slack_clean"]
            )
        else:
            calls_central += measured[f"{u.suite}_instruction"]
    n_attack = sum(u.mode == "attack" for u in units)
    n_clean = sum(u.mode == "clean" for u in units)

    def case(calls: float, rate: float, startup: float, retries: float, extra_start: float) -> dict:
        inference = calls * (1 + retries) / rate / 60
        minutes = 2 * session_minutes(startup) + inference + extra_start
        hours = minutes / 60
        return {
            "model_calls": round(calls * (1 + retries)),
            "calls_per_second": rate,
            "inference_minutes": round(inference, 1),
            "pod_minutes": round(minutes, 1),
            "usd": round(hours * (args.price + DISK_PER_HOUR), 2),
        }

    stage = {
        "episodes": len(units),
        "low": case(len(units) * 2.5, 7.1, measured["startup_minutes"], 0.0, 0),
        "central": case(calls_central, 7.1, measured["startup_minutes"], 0.05, 0),
        "high": case(n_attack * 16 + n_clean * 5.5, 3.55, 15, 0.10, 15),
    }
    # Adaptive follow-up (docs/protocol-adaptive.md): victim episodes plus attacker time.
    search, crossover, controls = 2304, 576, 144
    victim = search + crossover + controls

    def adaptive(per_episode: float, rate: float, startup: float, attacker_minutes: float) -> dict:
        inference = victim * per_episode / rate / 60
        minutes = 2 * session_minutes(startup) + inference + attacker_minutes
        return {
            "victim_episodes": victim,
            "victim_model_calls": round(victim * per_episode),
            "attacker_proposals": 12 * 16,
            "attacker_tokens_estimate": {
                "input": 12 * 16 * 3000 * 1.5,
                "output": 12 * 16 * 400 * 1.5,
            },
            "attacker_minutes": attacker_minutes,
            "pod_minutes": round(minutes, 1),
            "usd": round(minutes / 60 * (args.price + DISK_PER_HOUR), 2),
        }

    out = {
        "price_usd_per_hour": args.price,
        "price_source": (
            "RunPod list-gpu-types, RTX PRO 6000 Blackwell Server Edition, Secure, read 2026-11-17"
        ),
        "measured_from_pilot": measured,
        "stage1": stage,
        "stage1_proposed_cap_usd": 8.0,
        "adaptive": {
            "central": adaptive(6.0, 5.7, 10, 5),
            "high": adaptive(16.0, 3.0, 25, 16),
        },
        "adaptive_proposed_cap_usd": 18.0,
        "assumptions": [
            "two pod sessions per stage (one per batch, or search then held-out)",
            "per session: startup + 1 min rendering check + 2 min idle + 5 min shutdown margin",
            "central throughput = Granite's sustained Slack rate; "
            "high = half (a 2x slower host was observed)",
            "high case: every attack and forged episode reaches the 15-round limit (16 calls)",
            "high case adds 10% reruns and one failed start (15 min)",
            "adaptive: attacker Qwen3-8B co-hosted on the same card; victim throughput 0.8x",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("measured_from_pilot", "stage1", "adaptive")}, indent=1))


if __name__ == "__main__":
    main()
