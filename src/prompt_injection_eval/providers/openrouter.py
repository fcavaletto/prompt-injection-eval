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
- **Spending.** A durable ``SpendLedger`` reserves each attempt's bounded cost before it is
  sent and keeps it charged until the API reports the attempt's cost; a dedicated key with a
  service-side credit limit no larger than the cap is required (``preflight``), and the key's
  reported usage is reconciled against the ledger (``reconcile``). The local bound is stated,
  not proved: see ``worst_case_usd``.
- **Delivery is verified at request level only.** The provider's internal rendering of the
  conversation is not observable; no rendered prompt is returned or claimed.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from prompt_injection_eval.privacy import sanitize_text
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse
from prompt_injection_eval.providers.spend_ledger import SpendLedger

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
    # Long-prompt price tier from the endpoint metadata: above this many prompt tokens the
    # higher prices apply. The bound prices with the higher tier whenever it could apply.
    tier_min_prompt_tokens: int = 0
    tier_prompt_usd_per_token: float = 0.0
    tier_completion_usd_per_token: float = 0.0


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
        tier_min_prompt_tokens=272000,
        tier_prompt_usd_per_token=2.0e-7,
        tier_completion_usd_per_token=7.5e-7,
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
        tier_min_prompt_tokens=100000,
        tier_prompt_usd_per_token=5.0e-7,
        tier_completion_usd_per_token=2.5e-6,
    ),
}


# Tokens a provider may add around the request (tool-use instructions, role framing). Not
# documented by OpenRouter; a stated allowance, not a measured maximum.
PROVIDER_OVERHEAD_TOKENS = 4096


def worst_case_usd(body: dict[str, Any], endpoint: Endpoint) -> float:
    """The reservation for one attempt.

    Input: the UTF-8 byte length of the whole request body (byte-level BPE tokenizers emit
    at most one token per byte of text) plus ``PROVIDER_OVERHEAD_TOKENS``. Output: ``max_tokens``,
    which OpenRouter documents as covering reasoning and visible output "on most providers".
    Both models' tokenizers and the providers' added framing are not documented, so this is
    a conservative bound, not a proof. The long-prompt price tier is used if it could apply.
    """
    prompt_tokens = len(json.dumps(body, ensure_ascii=False).encode()) + PROVIDER_OVERHEAD_TOKENS
    out = int(body["max_tokens"])
    price_in, price_out = endpoint.prompt_usd_per_token, endpoint.completion_usd_per_token
    if endpoint.tier_min_prompt_tokens and prompt_tokens >= endpoint.tier_min_prompt_tokens:
        price_in = max(price_in, endpoint.tier_prompt_usd_per_token)
        price_out = max(price_out, endpoint.tier_completion_usd_per_token)
    return prompt_tokens * price_in + out * price_out


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
        ledger: SpendLedger,
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
        self.ledger = ledger
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
            rid = self.ledger.reserve(worst, note=request.model)
            if rid is None:
                attempts.append({"attempt": attempt, "outcome": "budget_exhausted"})
                return self._failure(
                    request, body, attempts, "budget_exhausted", "cap, call cap or halt", started
                )
            try:
                response = self._client.post(
                    "/chat/completions",
                    json=body,
                    headers=self._headers,
                    timeout=request.timeout_seconds,
                )
            except httpx.ConnectError as exc:
                # The connection was refused: nothing was sent, so nothing can be billed.
                self.ledger.release(rid, f"connect error before sending: {type(exc).__name__}")
                attempts.append(
                    {"attempt": attempt, "outcome": "connection_refused", "reservation": rid}
                )
                if attempt < _RETRIES:
                    time.sleep(self.retry_wait_seconds * attempt)
                    continue
                return self._failure(request, body, attempts, "connection", str(exc), started)
            except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError) as exc:
                # Sent, possibly processed and billed: stays charged until reconciled.
                self.ledger.mark_unresolved(rid, f"{type(exc).__name__} after sending")
                kind = "timeout" if isinstance(exc, httpx.TimeoutException) else "connection"
                attempts.append({"attempt": attempt, "outcome": kind, "reservation": rid})
                if kind == "connection" and attempt < _RETRIES:
                    time.sleep(self.retry_wait_seconds * attempt)
                    continue
                return self._failure(request, body, attempts, kind, str(exc), started)
            record = {"attempt": attempt, "status": response.status_code, "reservation": rid}
            try:
                data = response.json()
            except ValueError:
                data = None
            cost = _reported_cost(data)
            if cost is None:
                self.ledger.mark_unresolved(rid, f"no reported cost (HTTP {response.status_code})")
            else:
                self.ledger.settle(rid, cost, f"usage.cost, HTTP {response.status_code}")
            record["cost_usd"] = cost
            if response.status_code in _RETRY_STATUS:
                attempts.append(
                    record
                    | {"outcome": "retryable_status", "body": sanitize_text(response.text[:300])}
                )
                if attempt < _RETRIES:
                    time.sleep(self.retry_wait_seconds * attempt)
                    continue
                return self._failure(
                    request, body, attempts, "http_status", f"HTTP {response.status_code}", started
                )
            if response.status_code >= 400:
                attempts.append(
                    record | {"outcome": "http_error", "body": sanitize_text(response.text[:300])}
                )
                return self._failure(
                    request, body, attempts, "http_status", f"HTTP {response.status_code}", started
                )
            if data is None:
                attempts.append(record | {"outcome": "invalid_json"})
                return self._failure(
                    request, body, attempts, "invalid_provider_json", "not JSON", started
                )
            attempts.append(record | {"outcome": "ok"})
            break
        return self._parse(request, endpoint, body, data, attempts, started)

    # -- service-side limit -----------------------------------------------------------

    def key_info(self) -> dict[str, Any]:
        """GET /key: usage, limit and limit_remaining for this key, in USD."""
        response = self._client.get("/key", headers=self._headers, timeout=30.0)
        response.raise_for_status()
        data = response.json().get("data") or {}
        return {k: data.get(k) for k in ("usage", "limit", "limit_remaining", "limit_reset")}

    def preflight(self) -> list[str]:
        """The key must carry a service-side credit limit no larger than the ledger's cap."""
        info = self.key_info()
        problems = []
        if info["limit"] is None:
            problems.append(
                "the key has no credit limit; create a dedicated key limited to the cap"
            )
        elif float(info["limit"]) > self.ledger.cap_usd + 1e-9:
            problems.append(
                f"the key's limit {info['limit']} exceeds the cap {self.ledger.cap_usd}"
            )
        if info["limit_reset"] not in (None, "never"):
            problems.append(
                f"the key's limit resets ({info['limit_reset']}); use a non-resetting limit"
            )
        if not problems:
            self.ledger.record_baseline({"key_usage": info["usage"], "key_limit": info["limit"]})
        return problems

    def reconcile(self) -> dict[str, Any]:
        """Compare the key's usage since the baseline with what the ledger has committed."""
        info = self.key_info()
        base = self.ledger.baseline or {}
        used = float(info["usage"] or 0.0) - float(base.get("key_usage") or 0.0)
        committed = self.ledger.committed()
        ok = used <= committed + 1e-6
        if not ok:
            self.ledger.halt(f"key usage {used:.6f} exceeds the ledger's committed {committed:.6f}")
        return {"key_usage_since_baseline": used, "ledger_committed": committed, "consistent": ok}

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
            "reported_provider": served_provider(data),
            "routing_metadata": data.get("openrouter_metadata") if isinstance(data, dict) else None,
            "delivery_verification": VERIFICATION,
            "spend": self.ledger.state(),
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
                "spend": self.ledger.state(),
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


def served_provider(data: Any) -> str | None:
    """The provider that served the request: the top-level ``provider`` field when present,
    else the selected endpoint in the routing metadata (requested with the metadata header).
    None when neither is present: identity is then unobserved, which calibration rejects."""
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("provider"), str):
        return str(data["provider"])
    meta = data.get("openrouter_metadata")
    endpoints = meta.get("endpoints") if isinstance(meta, dict) else None
    available = endpoints.get("available") if isinstance(endpoints, dict) else None
    for entry in available or []:
        if (
            isinstance(entry, dict)
            and entry.get("selected")
            and isinstance(entry.get("provider"), str)
        ):
            return str(entry["provider"])
    return None


def _reported_cost(data: Any) -> float | None:
    """The cost the API reported for this attempt, or None. Never inferred from tokens."""
    usage = data.get("usage") if isinstance(data, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if isinstance(cost, int | float) and not isinstance(cost, bool) and cost >= 0:
        return float(cost)
    return None
