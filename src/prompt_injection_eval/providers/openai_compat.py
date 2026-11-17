"""Provider for an OpenAI-compatible chat server, written for vLLM on a rented GPU.

The harness stays on the local machine and sends each prompt over HTTP. The server
applies the model's own chat template, so a tool-result conversation is rendered the
way the model's developers intended, as with the MLX provider.

What differs from the local providers:

- The server batches requests, so the adaptive runner sends several at once
  (`concurrency`). At temperature 0 the answers are stable in practice, but batched
  inference is not bit-exact across batch compositions. A repeat measures this.
- Each request asks for `return_prompt_text`, a vLLM extension that returns the prompt
  string after templating. It is stored with the row, because for the tool-result
  placement the rendered prompt is the thing being studied.
- The server address is never written to a row. A rented pod's address is transient
  and identifies an account's resource.

Reasoning arrives in a separate `reasoning` field when the server runs a reasoning
parser, or inline as `<think>` tags when it does not. Both are captured.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from prompt_injection_eval.privacy import sanitize_text
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse
from prompt_injection_eval.reasoning import split_reasoning

BASE_URL_ENV = "PIE_OPENAI_BASE_URL"
API_KEY_ENV = "PIE_OPENAI_API_KEY"
CONCURRENCY_ENV = "PIE_OPENAI_CONCURRENCY"
LAUNCH_ARGS_ENV = "PIE_OPENAI_LAUNCH_ARGS"
DEFAULT_REMOTE_CONCURRENCY = 16
# A proxy in front of a pod returns these while the server is busy or restarting.
_RETRY_STATUS = frozenset({429, 502, 503, 504})
_RETRIES = 3


class OpenAICompatProvider:
    name = "openai"
    result_origin = "empirical_model_run"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        concurrency: int = 1,
        launch_args: str | None = None,
        client: httpx.Client | None = None,
        retry_wait_seconds: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/").removesuffix("/v1")
        self.concurrency = max(1, concurrency)
        self.launch_args = launch_args
        self.retry_wait_seconds = retry_wait_seconds
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            headers=headers,
            limits=httpx.Limits(max_connections=self.concurrency + 2),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def payload(self, request: GenerationRequest) -> dict[str, Any]:
        messages = (
            [_wire_message(message) for message in request.messages]
            if request.messages is not None
            else [
                {"role": "system", "content": request.system_message},
                {"role": "user", "content": request.user_message},
            ]
        )
        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "return_prompt_text": True,
        }
        if request.seed is not None:
            body["seed"] = request.seed
        if request.tools:
            # By default the tool call is already in the conversation and the model is
            # asked to answer, so the server must not parse its reply as a new call.
            body["tools"] = request.tools
            body["tool_choice"] = request.tool_choice or "none"
        think = request.provider_settings.get("think")
        if think is not None:
            body["chat_template_kwargs"] = {"enable_thinking": bool(think)}
        effort = request.provider_settings.get("reasoning_effort")
        if effort is not None:
            body["reasoning_effort"] = effort
        return body

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        body = self.payload(request)
        started = time.perf_counter()
        data: Any = None
        for attempt in range(1, _RETRIES + 1):
            try:
                response = self._client.post(
                    "/v1/chat/completions", json=body, timeout=request.timeout_seconds
                )
                if response.status_code in _RETRY_STATUS and attempt < _RETRIES:
                    time.sleep(self.retry_wait_seconds * attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                break
            except httpx.TimeoutException as exc:
                return self._failure(request, "timeout", exc, started)
            except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                # RemoteProtocolError: a proxy closed a pooled connection before any
                # response ("Server disconnected without sending a response"). Generation
                # has no server-side effect, so the request is retried like a refused
                # connection (bounded by _RETRIES). Added 2026-11-17 for Stage 1; the
                # archived pilot recorded these as infra_error and reran them on resume.
                if attempt < _RETRIES:
                    time.sleep(self.retry_wait_seconds * attempt)
                    continue
                return self._failure(request, "connection", exc, started)
            except httpx.HTTPStatusError as exc:
                detail = sanitize_text(exc.response.text[:300])
                return self._failure(request, "http_status", exc, started, detail)
            except httpx.HTTPError as exc:
                return self._failure(request, "http_error", exc, started)
            except ValueError as exc:
                return self._failure(request, "invalid_provider_json", exc, started)
        latency = time.perf_counter() - started
        choices = data.get("choices") if isinstance(data, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(choice, dict) or not isinstance(message, dict):
            return GenerationResponse(
                text=None,
                provider=self.name,
                model=request.model,
                latency_seconds=latency,
                error_type="empty_provider_response",
                error_message="The server returned no assistant message.",
            )
        finish = choice.get("finish_reason")
        content = message.get("content")
        raw_content: str = content if isinstance(content, str) else ""
        split = split_reasoning(raw_content)
        field_reasoning = message.get("reasoning") or message.get("reasoning_content")
        reasoning = split.reasoning
        if isinstance(field_reasoning, str) and field_reasoning.strip():
            reasoning = (
                field_reasoning.strip()
                if reasoning is None
                else field_reasoning.strip() + "\n\n" + reasoning
            )
        # The budget ran out inside the reasoning: there is no answer to score.
        cut_in_reasoning = split.truncated or (
            finish == "length" and not raw_content.strip() and reasoning is not None
        )
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        metadata: dict[str, Any] = {
            "finish_reason": finish,
            "reported_model": data.get("model"),
            "reasoning_field_present": isinstance(field_reasoning, str),
            "inline_think_tags": split.reasoning is not None or split.truncated,
            "request_options": {
                key: body[key]
                for key in ("chat_template_kwargs", "reasoning_effort", "tool_choice")
                if key in body
            },
        }
        calls = message.get("tool_calls")
        if isinstance(calls, list) and calls:
            metadata["tool_calls"] = [_call_summary(call) for call in calls]
        prompt_text = data.get("prompt_text")
        if isinstance(prompt_text, str):
            metadata["rendered_prompt"] = prompt_text
        return GenerationResponse(
            text="" if cut_in_reasoning else split.answer,
            raw_text=raw_content,
            reasoning_text=reasoning,
            reasoning_truncated=bool(cut_in_reasoning),
            provider=self.name,
            model=request.model,
            latency_seconds=latency,
            prompt_token_count=_as_int(usage.get("prompt_tokens")),
            completion_token_count=_as_int(usage.get("completion_tokens")),
            provider_metadata=metadata,
        )

    def health(self, model: str) -> list[str]:
        """Actionable issues. An empty list means the server is up and serves the model."""
        try:
            response = self._client.get("/v1/models", timeout=15.0)
            response.raise_for_status()
            listed = response.json().get("data", [])
        except httpx.HTTPError as exc:
            return [f"The model server is not answering: {sanitize_text(str(exc))}"]
        except (ValueError, AttributeError):
            return ["The model server returned invalid JSON from /v1/models."]
        names = [item.get("id") for item in listed if isinstance(item, dict)]
        if model in names:
            return []
        return [f"The server does not serve {model}. It serves: {', '.join(map(str, names))}."]

    def runtime_info(self, model: str) -> dict[str, Any]:
        """Server version and what it reports about the model.

        `launch_args` is what the operator says the server was started with. The
        server does not report its dtype, so that part is declared, not verified.
        """
        info: dict[str, Any] = {
            "runtime": "vllm",
            "runtime_version": None,
            "served_model": model,
            "max_model_len": None,
            "launch_args": self.launch_args,
        }
        try:
            version = self._client.get("/version", timeout=10.0)
            version.raise_for_status()
            payload = version.json()
            if isinstance(payload, dict):
                info["runtime_version"] = payload.get("version")
        except (httpx.HTTPError, ValueError):
            pass
        try:
            listed = self._client.get("/v1/models", timeout=10.0).json().get("data", [])
            for item in listed if isinstance(listed, list) else []:
                if isinstance(item, dict) and item.get("id") == model:
                    info["max_model_len"] = item.get("max_model_len")
                    info["model_root"] = item.get("root")
        except (httpx.HTTPError, ValueError, AttributeError):
            pass
        return info

    def _failure(
        self,
        request: GenerationRequest,
        error_type: str,
        exc: Exception,
        started: float,
        detail: str | None = None,
    ) -> GenerationResponse:
        message = sanitize_text(str(exc)).replace(self.base_url, "<server>")
        if detail:
            message = f"{message} | {detail}"
        return GenerationResponse(
            text=None,
            provider=self.name,
            model=request.model,
            latency_seconds=time.perf_counter() - started,
            error_type=error_type,
            error_message=message,
        )


def _wire_message(message: dict[str, Any]) -> dict[str, Any]:
    """The OpenAI wire format carries tool-call arguments as a JSON string."""
    calls = message.get("tool_calls")
    if not calls:
        return dict(message)
    wired = dict(message)
    wired["tool_calls"] = []
    for call in calls:
        function = dict(call.get("function", {}))
        if not isinstance(function.get("arguments"), str):
            function["arguments"] = json.dumps(function.get("arguments", {}))
        wired["tool_calls"].append({**call, "function": function})
    return wired


def _call_summary(call: Any) -> dict[str, Any]:
    """Name and arguments of one parsed tool call, as the server returned them."""
    function = call.get("function") if isinstance(call, dict) else None
    if not isinstance(function, dict):
        return {"name": None, "arguments": None}
    return {"name": function.get("name"), "arguments": function.get("arguments")}


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def provider_from_env() -> OpenAICompatProvider:
    """Build the provider from `PIE_OPENAI_*` variables. Raises if the address is missing."""
    base_url = os.environ.get(BASE_URL_ENV)
    if not base_url:
        raise ValueError(f"Set {BASE_URL_ENV} to the model server's address.")
    try:
        concurrency = int(os.environ.get(CONCURRENCY_ENV, DEFAULT_REMOTE_CONCURRENCY))
    except ValueError as exc:
        raise ValueError(f"{CONCURRENCY_ENV} must be a whole number.") from exc
    return OpenAICompatProvider(
        base_url=base_url,
        api_key=os.environ.get(API_KEY_ENV) or None,
        concurrency=concurrency,
        launch_args=os.environ.get(LAUNCH_ARGS_ENV) or None,
    )
