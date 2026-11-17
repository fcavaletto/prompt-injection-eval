"""OpenRouter feasibility screen: design frozen before any call (docs/protocol-openrouter.md).

Question: on contemporary tool-using models, does representation affect explicit
instruction attacks and forged-data attacks differently?

A development feasibility screen. It does not estimate resistance to an optimized attacker
and does not replace the controlled Granite experiment.

**Eligibility.** A case needs both attack families aimed at the *same* unauthorized action,
each valid under the threat model and reachable under AgentDojo's own check. Only the five
forged-data pathways of Stage 1 meet that (each validated offline in tests/test_stage1.py);
the instruction attack on the same pair targets the same goal check. The requested 24 cases
are therefore not available: the manifest has 5 cases, not 24, and no invalid attack is
added to fill the matrix.

**Intervention.** Only the injected result (the carrier) changes representation: labelled
text against valid JSON. Every other tool result stays labelled text in both arms.
"""

from __future__ import annotations

import random
from dataclasses import asdict
from typing import Any

from prompt_injection_eval.pilot import attacks, stage1
from prompt_injection_eval.pilot.episode import Spec
from prompt_injection_eval.providers.openrouter import ENDPOINTS

STAGE = "openrouter-screen-v1"
MODELS = tuple(ENDPOINTS)  # openai/gpt-6-luna, anthropic/claude-haiku-5.5
REPRESENTATIONS = {"text": "text", "json": "json@text"}  # carrier only; context stays text
INSTRUCTION = attacks.BASELINE  # AgentDojo's important_instructions, multiline
FORGED = "forged_multiline"
SEED = 20261120
REQUESTED_CASES = 24
CAP_USD = 5.0
MAX_ROUNDS = 15  # as in the pilot: at most 16 model calls per episode
MAX_ATTEMPTS = 3  # per call, inside the provider


def cases() -> list[tuple[str, str, str]]:
    return [(p.suite, p.user_task, p.goal) for p in stage1.PATHWAYS]


def units() -> list[Spec]:
    """Per model: 5 cases x 2 representations x (instruction, forged, benign) = 30."""
    out = []
    for suite, user, goal in cases():
        for fmt in REPRESENTATIONS.values():
            out.append(Spec(suite, "attack", fmt, user, goal, INSTRUCTION, 0))
            out.append(Spec(suite, "attack", fmt, user, goal, FORGED, 0))
            out.append(Spec(suite, "clean", fmt, user, None, None, 0))
    return out


def schedule(model: str) -> list[Spec]:
    found = units()
    random.Random(f"{SEED}:{model}").shuffle(found)
    return found


def calibration() -> list[Spec]:
    """Two episodes per model, kept apart from the screen and never analysed with it."""
    suite, user, goal = cases()[0]
    return [
        Spec(suite, "clean", "text", user, None, None, 0),
        Spec(suite, "attack", "json@text", user, goal, INSTRUCTION, 0),
    ]


def family(unit: Spec) -> str:
    if unit.mode == "clean":
        return "benign"
    return "forged" if unit.attack == FORGED else "instruction"


def design() -> dict[str, Any]:
    return {
        "stage": STAGE,
        "question": (
            "On contemporary tool-using models, does representation affect explicit "
            "instruction attacks and forged-data attacks differently?"
        ),
        "status": "development feasibility screen; not an estimate against optimized attackers",
        "models": {
            m: {k: v for k, v in asdict(ENDPOINTS[m]).items() if k != "supported"} for m in MODELS
        },
        "eligibility": {
            "requested_cases": REQUESTED_CASES,
            "eligible_cases": len(cases()),
            "rule": "both families aim at the same goal check; forged pathway validated offline",
            "cases": [list(c) for c in cases()],
        },
        "representations": REPRESENTATIONS,
        "attacks": {"instruction": INSTRUCTION, "forged": FORGED},
        "per_model_episodes": len(units()),
        "episodes": len(units()) * len(MODELS),
        "calibration_episodes": len(calibration()) * len(MODELS),
        "cap_usd_including_calibration": CAP_USD,
        "max_model_calls_per_episode": MAX_ROUNDS + 1,
        "max_attempts_per_call": MAX_ATTEMPTS,
        "manifest": {m: [asdict(u) | {"family": family(u)} for u in schedule(m)] for m in MODELS},
        "units_sha256": stage1.sha([asdict(u) for u in units()]),
    }
