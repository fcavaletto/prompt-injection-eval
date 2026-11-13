"""Versioned constants for the evaluation harness."""

# 1.1 adds the tool_call_request category, the tool_call_text attack goal, and the
# keyword_groups task. Every 1.0 file is also a valid 1.1 file.
SCHEMA_VERSION = "1.1"
PACKAGE_VERSION = "0.5.0"
SYNTHETIC_SECRET = "SYNTHETIC_SECRET_4C91"

BASELINE_TEMPLATE_VERSION = "baseline-v1"
DEFENDED_TEMPLATE_VERSION = "defended-v1"
# Spotlighting-style datamarking (Hines et al. 2024): every whitespace run in the
# document is replaced with DATAMARK so the model can see where untrusted text is.
SPOTLIGHT_TEMPLATE_VERSION = "defended-v2"
DATAMARK = "^"

# Condition names. "defended" is the generic instruction; "spotlight" is datamarking.
CONDITIONS = ("baseline", "defended", "spotlight")
DEFENSE_CONDITIONS = ("defended", "spotlight")

# attack-v2 adds tool_call_text and catches a secret written with separators between
# its characters. task-v2 adds keyword_groups. On every response in results-published/
# the v2 scorers return the same labels as v1; tests/test_rescore_published.py checks it.
ATTACK_SCORER_VERSION = "attack-v2"
TASK_SCORER_VERSION = "task-v2"
OUTCOME_VERSION = "outcome-v1"
SCORER_BUNDLE_VERSION = "attack-v2+task-v2+outcome-v1"

DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_MOCK_MODEL = "synthetic-mock"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 256
DEFAULT_TIMEOUT_SECONDS = 120.0
# Reasoning models spend most of their budget on visible chain-of-thought.
REASONING_MAX_TOKENS = 4096
REASONING_TIMEOUT_SECONDS = 900.0
DEFAULT_KEEP_ALIVE = "5m"
DEFAULT_CONCURRENCY = 1
