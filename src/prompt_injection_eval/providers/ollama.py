"""Ollama local HTTP provider.

Seeding is forwarded when a seed is configured. Not every Ollama build or model
tag honors the seed, so a fixed seed is not a determinism guarantee.

Reasoning models return visible chain-of-thought either in a separate
``message.thinking`` field or inline as ``<think>`` tags. Both are captured as
``reasoning_text`` and removed from the scored answer. No hidden channel is
requested; only what the runtime returns is stored.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from prompt_injection_eval.constants import DEFAULT_KEEP_ALIVE, DEFAULT_OLLAMA_BASE_URL
from prompt_injection_eval.privacy import sanitize_text
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse
from prompt_injection_eval.reasoning import split_reasoning


class OllamaProvider:
    name = "ollama"
    result_origin = "empirical_model_run"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        keep_alive: str | None = DEFAULT_KEEP_ALIVE,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.keep_alive = keep_alive
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        payload = self._payload(request)
        started = time.perf_counter()
        try:
            response = self._client.post(
                "/api/chat",
                json=payload,
                timeout=request.timeout_seconds,
            )
            latency = time.perf_counter() - started
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            return self._failure(request, "timeout", exc, time.perf_counter() - started)
        except httpx.ConnectError as exc:
            return self._failure(request, "connection", exc, time.perf_counter() - started)
        except httpx.HTTPStatusError as exc:
            return self._failure(request, "http_status", exc, time.perf_counter() - started)
        except httpx.HTTPError as exc:
            return self._failure(request, "http_error", exc, time.perf_counter() - started)
        except ValueError as exc:
            return self._failure(
                request, "invalid_provider_json", exc, time.perf_counter() - started
            )

        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            return GenerationResponse(
                text=None,
                provider=self.name,
                model=request.model,
                latency_seconds=latency,
                error_type="empty_provider_response",
                error_message="Ollama returned no assistant message content.",
                provider_metadata={"synthetic_mock": False},
            )
        raw_content: str = message["content"]
        split = split_reasoning(raw_content)
        field_thinking = message.get("thinking")
        reasoning = split.reasoning
        if isinstance(field_thinking, str) and field_thinking.strip():
            reasoning = (
                field_thinking.strip()
                if reasoning is None
                else field_thinking.strip() + "\n\n" + reasoning
            )
        metadata = {
            "done": data.get("done"),
            "done_reason": data.get("done_reason"),
            "total_duration": data.get("total_duration"),
            "load_duration": data.get("load_duration"),
            "prompt_eval_duration": data.get("prompt_eval_duration"),
            "eval_duration": data.get("eval_duration"),
            "reported_model": data.get("model"),
            "thinking_field_present": isinstance(field_thinking, str),
            "inline_think_tags": split.reasoning is not None or split.truncated,
        }
        return GenerationResponse(
            text=split.answer,
            raw_text=raw_content,
            reasoning_text=reasoning,
            reasoning_truncated=split.truncated,
            provider=self.name,
            model=str(data.get("model") or request.model),
            latency_seconds=latency,
            prompt_token_count=_as_int(data.get("prompt_eval_count")),
            completion_token_count=_as_int(data.get("eval_count")),
            total_duration_ns=_as_int(data.get("total_duration")),
            load_duration_ns=_as_int(data.get("load_duration")),
            prompt_eval_duration_ns=_as_int(data.get("prompt_eval_duration")),
            eval_duration_ns=_as_int(data.get("eval_duration")),
            provider_metadata=metadata,
        )

    def health(self, model: str | None = None) -> list[str]:
        """Return actionable issues. An empty list means the check passed."""
        try:
            response = self._client.get("/api/tags", timeout=5.0)
            response.raise_for_status()
            payload = response.json()
        except httpx.ConnectError:
            return [
                "Ollama endpoint is not responding.",
                "Start Ollama with `ollama serve`.",
                "The Ollama desktop application may already be running.",
            ]
        except httpx.TimeoutException:
            return [
                "Ollama endpoint is not responding.",
                "Start Ollama with `ollama serve`.",
                "The Ollama desktop application may already be running.",
            ]
        except httpx.HTTPError as exc:
            return [f"Ollama endpoint returned an error: {sanitize_text(str(exc))}"]
        except ValueError:
            return ["Ollama endpoint returned invalid JSON from /api/tags."]
        if model is None:
            return []
        names = _model_names(payload)
        if _model_installed(names, model):
            return []
        return [
            f"Model {model} is not installed.",
            f"Install it with `ollama pull {model}`.",
        ]

    def model_info(self, model: str) -> dict[str, Any]:
        """Capabilities, quantization, and parameter size reported by /api/show."""
        try:
            response = self._client.post("/api/show", json={"model": model}, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        raw_details = payload.get("details")
        details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
        capabilities = payload.get("capabilities")
        return {
            "capabilities": capabilities if isinstance(capabilities, list) else [],
            "supports_thinking": isinstance(capabilities, list) and "thinking" in capabilities,
            "quantization_level": details.get("quantization_level"),
            "parameter_size": details.get("parameter_size"),
            "family": details.get("family"),
        }

    def _payload(self, request: GenerationRequest) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": request.temperature,
            "num_predict": request.max_output_tokens,
        }
        if request.seed is not None:
            options["seed"] = request.seed
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_message},
                {"role": "user", "content": request.user_message},
            ],
            "stream": False,
            "options": options,
        }
        keep_alive = request.provider_settings.get("keep_alive", self.keep_alive)
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        think = request.provider_settings.get("think")
        if think is not None:
            payload["think"] = bool(think)
        return payload

    def _failure(
        self,
        request: GenerationRequest,
        error_type: str,
        exc: Exception,
        latency: float,
    ) -> GenerationResponse:
        return GenerationResponse(
            text=None,
            provider=self.name,
            model=request.model,
            latency_seconds=latency,
            error_type=error_type,
            error_message=sanitize_text(str(exc)),
            provider_metadata={"synthetic_mock": False},
        )


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _model_names(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    names: list[str] = []
    for item in models:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def _model_installed(names: list[str], model: str) -> bool:
    accepted = {model, f"{model}:latest"}
    return any(name in accepted for name in names)
