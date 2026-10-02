"""Typed run configuration. Environment variables cover non-secret runtime settings only."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from prompt_injection_eval.constants import (
    DEFAULT_CONCURRENCY,
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MOCK_MODEL,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    REASONING_MAX_TOKENS,
    REASONING_TIMEOUT_SECONDS,
)


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["mock", "ollama"]
    model: str
    dataset: Path
    condition: Literal["baseline", "defended", "spotlight", "both", "all"]
    output_dir: Path
    limit: int | None = None
    case_ids: list[str] = Field(default_factory=list)
    category: str | None = None
    difficulty: str | None = None
    seed: int | None = None
    temperature: float = DEFAULT_TEMPERATURE
    max_output_tokens: int = DEFAULT_MAX_TOKENS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    resume: bool = True
    overwrite: bool = False
    verbose: bool = False
    keep_alive: str | None = DEFAULT_KEEP_ALIVE
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    task_mode: Literal["strict", "lenient"] = "strict"
    concurrency: int = DEFAULT_CONCURRENCY
    # None leaves the runtime default. True or False is forwarded to Ollama as `think`.
    think: bool | None = None
    profile: Literal["default", "reasoning"] = "default"

    def public_dict(self) -> dict[str, object]:
        from prompt_injection_eval.privacy import display_path

        payload = self.model_dump(mode="json")
        payload["dataset"] = display_path(self.dataset)
        payload["output_dir"] = display_path(self.output_dir)
        return payload


def default_model(provider: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    env_model = os.environ.get("PIE_MODEL")
    if env_model:
        return env_model
    if provider == "mock":
        return DEFAULT_MOCK_MODEL
    return DEFAULT_MODEL


def env_base_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    return os.environ.get("PIE_OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)


def env_timeout_override(explicit: float | None) -> float | None:
    """CLI value, else PIE_TIMEOUT, else None so the profile default applies."""
    if explicit is not None:
        return explicit
    raw = os.environ.get("PIE_TIMEOUT")
    if raw:
        return float(raw)
    return None


def resolve_generation_limits(
    *, profile: str, max_tokens: int | None, timeout: float | None
) -> tuple[int, float]:
    """Explicit values win. Otherwise the profile picks the defaults."""
    if profile == "reasoning":
        default_tokens, default_timeout = REASONING_MAX_TOKENS, REASONING_TIMEOUT_SECONDS
    else:
        default_tokens, default_timeout = DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT_SECONDS
    tokens = max_tokens if max_tokens is not None else default_tokens
    seconds = timeout if timeout is not None else default_timeout
    return tokens, seconds


def env_keep_alive(explicit: str | None) -> str | None:
    if explicit is not None:
        return explicit
    if "PIE_KEEP_ALIVE" in os.environ:
        raw = os.environ["PIE_KEEP_ALIVE"]
        return raw or None
    return DEFAULT_KEEP_ALIVE
