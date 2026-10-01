"""Provider interface. The runner depends on this module, not on Ollama."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class GenerationRequest:
    model: str
    system_message: str
    user_message: str
    temperature: float
    seed: int | None
    max_output_tokens: int
    timeout_seconds: float
    provider_settings: dict[str, Any] = field(default_factory=dict)
    # Harness metadata is not part of the prompt sent to a real model.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResponse:
    """Provider output.

    ``text`` is the final answer that the scorers see. ``raw_text`` is the
    completion exactly as the runtime returned it. ``reasoning_text`` holds
    visible chain-of-thought when the model produced any, and
    ``reasoning_truncated`` is True when generation stopped inside it.
    """

    text: str | None
    provider: str
    model: str
    latency_seconds: float | None
    raw_text: str | None = None
    reasoning_text: str | None = None
    reasoning_truncated: bool = False
    prompt_token_count: int | None = None
    completion_token_count: int | None = None
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_duration_ns: int | None = None
    provider_metadata: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_type is None and self.text is not None


class Provider(Protocol):
    name: str
    result_origin: str

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Return a response or a structured error. Do not raise for provider failures."""
