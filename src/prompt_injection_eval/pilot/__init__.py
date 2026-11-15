"""Serialization pilot on AgentDojo tasks. Design: docs/pilot-design.md."""

from __future__ import annotations

STUDY = "pilot-serialization-v1"
AGENTDOJO_VERSION = "0.1.35"
BENCHMARK_VERSION = "v1.2.2"
FORMATS = ("text", "json")
DEV_SUITE = "banking"
EVAL_SUITE = "slack"


class PilotError(ValueError):
    """A problem with the pilot's inputs, its environment or an existing output directory."""
