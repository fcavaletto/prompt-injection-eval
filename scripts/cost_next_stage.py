"""Cost of the next-stage options, from the pilot's measured throughput. No model call.

Every input is stated below. Calls per episode and throughput on workspace and travel
are assumptions scaled from Slack; they are the main source of uncertainty.

    python scripts/cost_next_stage.py
"""

from __future__ import annotations

PRICE_PER_HOUR = 2.69 + 0.03  # RTX PRO 6000 Blackwell, Secure, listed 2026-11-16; plus disk
REMAINING = 50.0 - 18.71  # posted billing, project-attributed (spending ledger)

# Reserved suites, AgentDojo v1.2.2: user tasks x attacker goals.
SUITES = {"workspace": (40, 14), "travel": (20, 7)}
PAIRS = sum(u * g for u, g in SUITES.values())  # 700
USERS = sum(u for u, _ in SUITES.values())  # 60
GOALS = sum(g for _, g in SUITES.values())  # 21
REPEAT_PAIRS = USERS  # one pre-drawn pair per user task gets runs 2 and 3
CONTROL_RUNS = 3
# Per run and format: clean and scratch per user task; direct and twin per goal.
CONTROL_EPISODES = CONTROL_RUNS * 2 * (2 * USERS + 2 * GOALS)  # 972

# Measured on Slack in the pilot: model calls per second during the evaluation phase.
# Qwen ran on a host about 2.2x slower than F1's; Granite's rate is from its phases.
SLACK_RATE = {"qwen": 3.09, "granite": 7.5}
# Assumptions for the reserved suites (workspace tool outputs are ~15x Slack's in
# characters; travel reference solutions are 1.3x longer). Central / conservative.
RATE_FACTOR = (0.7, 0.5)
ATTACK_CALLS = (7.0, 11.0)  # Slack measured 6.3 (Qwen) and 7.0 (Granite)
CONTROL_CALLS = (5.0, 7.0)  # Slack controls measured 4.7 (Qwen) and 4.8 (Granite)
OVERHEAD_HOURS = (0.5, 0.75)  # startup, rendering check, prompt checks, idle, shutdown


def hours(model: str, conditions: int, case: int, controls: bool = True) -> float:
    episodes = conditions * (PAIRS + 2 * REPEAT_PAIRS)
    calls = episodes * ATTACK_CALLS[case] + (
        CONTROL_EPISODES * CONTROL_CALLS[case] if controls else 0
    )
    rate = SLACK_RATE[model] * RATE_FACTOR[case]
    return calls / rate / 3600 + OVERHEAD_HOURS[case]


OPTIONS = {
    "A. Fixed baseline only, both models": {"qwen": 2, "granite": 2},
    "B. Frozen attack sets, both models (baseline + banking-selected)": {"qwen": 6, "granite": 4},
    "A+G. Core A plus Granite's selection module": {"qwen": 2, "granite": 4},
    "C. Granite only, frozen attack set": {"granite": 4},
    "D. Revised direction: baseline + one data-injection payload, both models": {
        "qwen": 4,
        "granite": 4,
    },
}


def main() -> None:
    print(f"Pairs {PAIRS}, user tasks {USERS}, goals {GOALS}, control episodes {CONTROL_EPISODES}")
    print(f"Remaining of $50 after posted billing: ${REMAINING:.2f}")
    for name, models in OPTIONS.items():
        cells = []
        for case in (0, 1):
            h = sum(hours(m, c, case) for m, c in models.items())
            cells.append(f"{h:.1f} h ${h * PRICE_PER_HOUR:.1f}")
        episodes = sum(c * (PAIRS + 2 * REPEAT_PAIRS) + CONTROL_EPISODES for c in models.values())
        print(f"{name}: {episodes} episodes; central {cells[0]}; conservative {cells[1]}")


if __name__ == "__main__":
    main()
