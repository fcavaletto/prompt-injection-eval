"""OpenRouter chat-completions provider for the API screen (docs/protocol-openrouter.md).

Measurement rules, each enforced here and tested offline with mocked responses:

- **One pinned endpoint per model.** ``provider.only`` names one provider slug,
  ``allow_fallbacks`` is false, ``require_parameters`` is true, no ``models`` array is sent
  (no model fallback), and ``max_price`` caps the per-token price at the pinned endpoint's.
- **Only parameters the pinned endpoint lists** are sent. Neither model lists
  ``temperature``; only GPT-6 Luna's endpoint lists ``seed``. Neither makes outputs
  deterministic.
- **Frozen reasoning and output limits** per model (``ENDPOINTS``).
- **Everything recorded** except credentials: the exact outgoing body, the raw response,
  requested and returned model, provider fields when present, usage and cost, finish
  reasons, every attempt with its error.
- **Distinct failure outcomes.** API errors, budget refusals, and model or provider
  mismatches are ``error_type`` values; a malformed tool call is a model output, not an API
  failure, and is counted by the episode.
- **A hard spending cap.** ``SpendGuard`` reserves each attempt's worst-case cost before it
  is sent and settles it with the reported cost afterwards, so concurrent requests cannot
  exceed the cap.
- **Delivery is verified at request level only.** The provider's internal rendering of the
  conversation is not observable; no rendered prompt is returned or claimed.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from prompt_injection_eval.privacy import sanitize_text
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse

API_KEY_ENV = "OPENROUTER_API_KEY"
BASE_URL = "https://openrouter.ai/api/v1"
_RETRY_STATUS = frozenset({429, 502, 503, 504})
_RETRIES = 3
VERIFICATION = (
    "request-level: outgoing request checked; the provider's internal rendering is unobserved"
)


@dataclass(frozen=True)
class Endpoint:
    """One model at one provider endpoint, as read from OpenRouter's metadata (2026-11-17)."""

    model: str  # the id sent
    canonical: str  # dated slug the id resolved to when read
    provider_slug: str  # for provider.only; a base slug excludes tier endpoints (flex, fast)
    provider_name: str  # as the endpoints API names it
    prompt_usd_per_token: float
    completion_usd_per_token: float
    supported: tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)  # frozen, all in ``supported``


ENDPOINTS: dict[str, Endpoint] = {
    "openai/gpt-6-luna": Endpoint(
        model="openai/gpt-6-luna",
        canonical="openai/gpt-6-luna-20260922",
        provider_slug="openai",
        provider_name="OpenAI",
        prompt_usd_per_token=1.0e-7,
        completion_usd_per_token=5.0e-7,
        supported=(
            "reasoning",
            "include_reasoning",
            "seed",
            "max_tokens",
            "response_format",
            "structured_outputs",
            "tools",
            "tool_choice",
            "verbosity",
            "reasoning_effort",
        ),
        params={"max_tokens": 4096, "reasoning": {"effort": "low"}, "seed": 20261117},
    ),
    "anthropic/claude-haiku-5.5": Endpoint(
        model="anthropic/claude-haiku-5.5",
        canonical="anthropic/claude-haiku-5.5-20261007",
        provider_slug="anthropic",
        provider_name="Anthropic",
        prompt_usd_per_token=1.0e-7,
        completion_usd_per_token=5.0e-7,
        supported=(
            "reasoning",
            "include_reasoning",
            "max_tokens",
            "stop",
            "tools",
            "tool_choice",
            "structured_outputs",
            "response_format",
            "verbosity",
            "reasoning_effort",
        ),
        params={"max_tokens": 4096, "reasoning": {"effort": "low"}},
    ),
}


class SpendGuard:
    """A cap in USD and on calls. Reserve the worst case before sending; settle after."""

    def __init__(self, cap_usd: float, max_calls: int) -> None:
        self.cap_usd = cap_usd
        self.max_calls = max_calls
        self.spent = 0.0
        self.reserved = 0.0
        self.calls = 0
        self._lock = threading.Lock()

    def reserve(self, worst_usd: float) -> bool:
        with self._lock:
            if (
                self.calls >= self.max_calls
                or self.spent + self.reserved + worst_usd > self.cap_usd
            ):
                return False
            self.reserved += worst_usd
            self.calls += 1
            return True

    def settle(self, reserved_usd: float, actual_usd: float) -> None:
        with self._lock:
            self.reserved -= reserved_usd
            self.spent += actual_usd

    def state(self) -> dict[str, float]:
        with self._lock:
            return {"spent_usd": self.spent, "reserved_usd": self.reserved, "calls": self.calls}


def worst_case_usd(body: dict[str, Any], endpoint: Endpoint) -> float:
    """An upper bound on one attempt's cost: at least 1 token per 2 characters of input."""
    prompt_tokens = math.ceil(
        len(json.dumps(body["messages"]) + json.dumps(body.get("tools", []))) / 2
    )
    return (
        prompt_tokens * endpoint.prompt_usd_per_token
        + body["max_tokens"] * endpoint.completion_usd_per_token
    )


def _wire_message(message: dict[str, Any]) -> dict[str, Any]:
    """OpenAI chat format: tool-call arguments are JSON strings."""
    if message.get("role") == "assistant" and message.get("tool_calls"):
        calls = []
        for call in message["tool_calls"]:
            f = call["function"]
            args = f["arguments"]
            calls.append(
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": f["name"],
                        "arguments": args if isinstance(args, str) else json.dumps(args),
                    },
                }
            )
        return {"role": "assistant", "content": message.get("content") or "", "tool_calls": calls}
    if message.get("role") == "tool":
        return {
            "role": "tool",
            "tool_call_id": message["tool_call_id"],
            "content": message["content"],
        }
    return {"role": message["role"], "content": message.get("content") or ""}


class OpenRouterProvider:
    name = "openrouter"
    result_origin = "empirical_model_run"
    concurrency = 4

    def __init__(
        self,
        guard: SpendGuard,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        retry_wait_seconds: float = 2.0,
    ) -> None:
        key = api_key or os.environ.get(API_KEY_ENV)
        if not key:
            raise ValueError(
                f"Set {API_KEY_ENV}; it is read from the environment and never recorded."
            )
        self._client = client or httpx.Client(base_url=BASE_URL)
        self._headers = {"Authorization": f"Bearer {key}", "X-OpenRouter-Metadata": "enabled"}
        self.guard = guard
        self.retry_wait_seconds = retry_wait_seconds

    def body(self, request: GenerationRequest) -> dict[str, Any]:
        endpoint = ENDPOINTS[request.model]
        unsupported = [p for p in endpoint.params if p not in endpoint.supported]
        if unsupported:
            raise ValueError(f"{request.model}: frozen parameters not supported: {unsupported}")
        body: dict[str, Any] = {
            "model": endpoint.model,
            "messages": [_wire_message(m) for m in request.messages or []],
            "tools": request.tools or [],
            "tool_choice": request.tool_choice or "auto",
            **json.loads(json.dumps(endpoint.params)),
            "provider": {
                "only": [endpoint.provider_slug],
                "allow_fallbacks": False,
                "require_parameters": True,
                "data_collection": "deny",
                "max_price": {
                    "prompt": endpoint.prompt_usd_per_token * 1e6,
                    "completion": endpoint.completion_usd_per_token * 1e6,
                },
            },
        }
        if "seed" in body:
            body["seed"] = int(body["seed"]) + int(request.seed or 0) - 20261115
        return body

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        endpoint = ENDPOINTS[request.model]
        body = self.body(request)
        attempts: list[dict[str, Any]] = []
        started = time.perf_counter()
        data: Any = None
        for attempt in range(1, _RETRIES + 1):
            worst = worst_case_usd(body, endpoint)
            if not self.guard.reserve(worst):
                attempts.append({"attempt": attempt, "outcome": "budget_exhausted"})
                return self._failure(
                    request,
                    body,
                    attempts,
                    "budget_exhausted",
                    "spending cap or call cap reached",
                    started,
                )
            actual = 0.0
            try:
                response = self._client.post(
                    "/chat/completions",
                    json=body,
                    headers=self._headers,
                    timeout=request.timeout_seconds,
                )
                record = {"attempt": attempt, "status": response.status_code}
                if response.status_code in _RETRY_STATUS:
                    attempts.append(
                        record
                        | {
                            "outcome": "retryable_status",
                            "body": sanitize_text(response.text[:300]),
                        }
                    )
                    if attempt < _RETRIES:
                        time.sleep(self.retry_wait_seconds * attempt)
                        continue
                    return self._failure(
                        request,
                        body,
                        attempts,
                        "http_status",
                        f"HTTP {response.status_code}",
                        started,
                    )
                if response.status_code >= 400:
                    attempts.append(
                        record
                        | {"outcome": "http_error", "body": sanitize_text(response.text[:300])}
                    )
                    return self._failure(
                        request,
                        body,
                        attempts,
                        "http_status",
                        f"HTTP {response.status_code}",
                        started,
                    )
                data = response.json()
                actual = _cost(data, endpoint)
                attempts.append(record | {"outcome": "ok", "cost_usd": actual})
                break
            except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                attempts.append(
                    {"attempt": attempt, "outcome": "connection", "error": type(exc).__name__}
                )
                if attempt < _RETRIES:
                    time.sleep(self.retry_wait_seconds * attempt)
                    continue
                return self._failure(request, body, attempts, "connection", str(exc), started)
            except httpx.TimeoutException as exc:
                attempts.append({"attempt": attempt, "outcome": "timeout"})
                return self._failure(request, body, attempts, "timeout", str(exc), started)
            except ValueError as exc:
                attempts.append({"attempt": attempt, "outcome": "invalid_json"})
                return self._failure(
                    request, body, attempts, "invalid_provider_json", str(exc), started
                )
            finally:
                # Failed attempts are settled at zero only if the API reported no cost.
                self.guard.settle(worst, actual)
        return self._parse(request, endpoint, body, data, attempts, started)

    def _parse(
        self,
        request: GenerationRequest,
        endpoint: Endpoint,
        body: dict[str, Any],
        data: Any,
        attempts: list[dict[str, Any]],
        started: float,
    ) -> GenerationResponse:
        latency = time.perf_counter() - started
        meta: dict[str, Any] = {
            "sent_request": body,
            "raw_response": data,
            "attempts": attempts,
            "requested_model": endpoint.model,
            "expected_canonical": endpoint.canonical,
            "reported_model": data.get("model") if isinstance(data, dict) else None,
            "reported_provider": data.get("provider") if isinstance(data, dict) else None,
            "delivery_verification": VERIFICATION,
            "spend": self.guard.state(),
        }
        choices = data.get("choices") if isinstance(data, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(message, dict):
            return GenerationResponse(
                text=None,
                provider=self.name,
                model=request.model,
                latency_seconds=latency,
                error_type="empty_provider_response",
                error_message="No assistant message.",
                provider_metadata=meta,
            )
        if meta["reported_model"] not in (endpoint.model, endpoint.canonical):
            return GenerationResponse(
                text=None,
                provider=self.name,
                model=request.model,
                latency_seconds=latency,
                error_type="model_mismatch",
                error_message=f"returned model {meta['reported_model']!r}",
                provider_metadata=meta,
            )
        provider = meta["reported_provider"]
        if provider is not None and provider != endpoint.provider_name:
            return GenerationResponse(
                text=None,
                provider=self.name,
                model=request.model,
                latency_seconds=latency,
                error_type="provider_mismatch",
                error_message=f"served by {provider!r}",
                provider_metadata=meta,
            )
        usage: dict[str, Any] = data["usage"] if isinstance(data.get("usage"), dict) else {}
        details = usage.get("completion_tokens_details") or {}
        meta.update(
            {
                "finish_reason": choice.get("finish_reason") if choice else None,
                "native_finish_reason": choice.get("native_finish_reason") if choice else None,
                "usage": usage,
                "reasoning_tokens": details.get("reasoning_tokens"),
                "generation_id": data.get("id"),
            }
        )
        calls = message.get("tool_calls")
        if isinstance(calls, list) and calls:
            meta["tool_calls"] = [
                {
                    "name": (c.get("function") or {}).get("name"),
                    "arguments": (c.get("function") or {}).get("arguments"),
                }
                for c in calls
                if isinstance(c, dict)
            ]
        reasoning = message.get("reasoning")
        return GenerationResponse(
            text=message.get("content") or "",
            raw_text=message.get("content") or "",
            reasoning_text=reasoning if isinstance(reasoning, str) else None,
            provider=self.name,
            model=request.model,
            latency_seconds=latency,
            prompt_token_count=usage.get("prompt_tokens"),
            completion_token_count=usage.get("completion_tokens"),
            provider_metadata=meta,
        )

    def _failure(
        self,
        request: GenerationRequest,
        body: dict[str, Any],
        attempts: list[dict[str, Any]],
        kind: str,
        message: str,
        started: float,
    ) -> GenerationResponse:
        return GenerationResponse(
            text=None,
            provider=self.name,
            model=request.model,
            latency_seconds=time.perf_counter() - started,
            error_type=kind,
            error_message=sanitize_text(message)[:300],
            provider_metadata={
                "sent_request": body,
                "attempts": attempts,
                "delivery_verification": VERIFICATION,
                "spend": self.guard.state(),
            },
        )

    def runtime_info(self, model: str) -> dict[str, Any]:
        e = ENDPOINTS[model]
        return {
            "runtime": "openrouter",
            "model": e.model,
            "canonical_when_read": e.canonical,
            "provider": e.provider_slug,
            "params": e.params,
            "routing": {
                "allow_fallbacks": False,
                "require_parameters": True,
                "only": [e.provider_slug],
            },
            "verification": VERIFICATION,
        }


def _cost(data: Any, endpoint: Endpoint) -> float:
    """Reported cost if present; otherwise priced from tokens (reasoning counted as output)."""
    usage: dict[str, Any] = (
        data["usage"] if isinstance(data, dict) and isinstance(data.get("usage"), dict) else {}
    )
    if isinstance(usage.get("cost"), int | float):
        return float(usage["cost"])
    return (usage.get("prompt_tokens") or 0) * endpoint.prompt_usd_per_token + (
        usage.get("completion_tokens") or 0
    ) * endpoint.completion_usd_per_token
