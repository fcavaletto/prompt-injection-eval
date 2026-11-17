"""The remote-server provider against a fake HTTP transport. Nothing leaves the machine."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from prompt_injection_eval.adaptive.engine import Unit, run_units
from prompt_injection_eval.adaptive.seeds import load_seeds
from prompt_injection_eval.adaptive.strategies import strategy_by_name
from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.providers.base import GenerationRequest
from prompt_injection_eval.providers.openai_compat import (
    BASE_URL_ENV,
    OpenAICompatProvider,
    provider_from_env,
)
from prompt_injection_eval.results_io import load_results

SEEDS = Path("data/adaptive_seeds.jsonl")
BASE = "https://pod-8000.example.test"


def _provider(handler: Any, **kwargs: Any) -> OpenAICompatProvider:
    client = httpx.Client(base_url=BASE, transport=httpx.MockTransport(handler))
    return OpenAICompatProvider(base_url=BASE, client=client, retry_wait_seconds=0.0, **kwargs)


def _request(**overrides: Any) -> GenerationRequest:
    values: dict[str, Any] = dict(
        model="org/model",
        system_message="sys",
        user_message="user",
        temperature=0.0,
        seed=42,
        max_output_tokens=64,
        timeout_seconds=5.0,
    )
    values.update(overrides)
    return GenerationRequest(**values)


def _completion(content: str | None, **message: Any) -> dict[str, Any]:
    return {
        "model": "org/model",
        "prompt_text": "<rendered>",
        "choices": [
            {"finish_reason": "stop", "message": {"role": "assistant", "content": content}}
            | ({"message": {"role": "assistant", "content": content, **message}} if message else {})
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3},
    }


def test_plain_request_and_rendered_prompt_are_recorded() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_completion("Denied."))

    response = _provider(handler).generate(_request(provider_settings={"think": False}))
    assert response.text == "Denied." and response.error_type is None
    assert (response.prompt_token_count, response.completion_token_count) == (11, 3)
    assert response.provider_metadata is not None
    assert response.provider_metadata["rendered_prompt"] == "<rendered>"
    body = seen[0]
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["seed"] == 42 and body["return_prompt_text"] is True
    assert "tools" not in body and "reasoning_effort" not in body


def test_tool_conversation_is_sent_in_wire_format() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_completion("rejected"))

    messages = [
        {"role": "user", "content": "task"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"type": "function", "id": "c1", "function": {"name": "read", "arguments": {}}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "name": "read", "content": "document"},
    ]
    tools = [{"type": "function", "function": {"name": "read"}}]
    request = _request(messages=messages, tools=tools)
    assert _provider(handler).generate(request).text == "rejected"
    body = seen[0]
    # Arguments travel as a JSON string, and the caller's messages are not mutated.
    assert body["messages"][1]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert messages[1]["tool_calls"][0]["function"]["arguments"] == {}
    assert body["messages"][2]["content"] == "document"
    assert body["tools"] == tools and body["tool_choice"] == "none"


def test_reasoning_field_and_budget_exhausted_inside_reasoning() -> None:
    def with_field(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion("Answer.", reasoning="Think first."))

    response = _provider(with_field).generate(_request())
    assert (response.text, response.reasoning_text) == ("Answer.", "Think first.")
    assert response.reasoning_truncated is False

    def cut(_request: httpx.Request) -> httpx.Response:
        payload = _completion(None, reasoning="Still thinking")
        payload["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=payload)

    truncated = _provider(cut).generate(_request())
    assert truncated.text == "" and truncated.reasoning_truncated is True


def test_busy_proxy_is_retried_and_errors_hide_the_address() -> None:
    calls = {"n": 0}

    def flaky(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json=_completion("ok"))

    assert _provider(flaky).generate(_request()).text == "ok"
    assert calls["n"] == 3

    def broken(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="unknown field")

    failed = _provider(broken).generate(_request())
    assert failed.error_type == "http_status" and failed.text is None
    assert failed.error_message is not None
    assert BASE not in failed.error_message and "unknown field" in failed.error_message


def test_health_and_runtime_info() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json={"version": "0.99.0"})
        return httpx.Response(
            200, json={"data": [{"id": "org/model", "max_model_len": 8192, "root": "org/model"}]}
        )

    provider = _provider(handler, launch_args="--dtype bfloat16")
    assert provider.health("org/model") == []
    assert "does not serve" in provider.health("org/other")[0]
    info = provider.runtime_info("org/model")
    assert info["runtime_version"] == "0.99.0" and info["max_model_len"] == 8192
    assert info["launch_args"] == "--dtype bfloat16"
    assert BASE not in json.dumps(info)


def test_provider_from_env_needs_an_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    with pytest.raises(ValueError, match=BASE_URL_ENV):
        provider_from_env()
    monkeypatch.setenv(BASE_URL_ENV, BASE + "/v1/")
    built = provider_from_env()
    assert built.base_url == BASE and built.concurrency == 16
    built.close()


def test_engine_runs_units_in_parallel_and_writes_them_in_plan_order(tmp_path: Path) -> None:
    seeds, sha = load_seeds(SEEDS)
    held_out = [seed for seed in seeds if seed.split == "test"][:12]
    strategy = strategy_by_name("naive+inline+plain")
    threads: set[int] = set()
    lock = threading.Lock()
    arrivals = {"n": 0}
    # The first four requests must be in flight together before any is answered.
    gate = threading.Barrier(4, timeout=5)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":  # the runner's version and model lookups
            return httpx.Response(200, json={"version": "0.99.0", "data": []})
        with lock:
            arrivals["n"] += 1
            among_first = arrivals["n"] <= 4
            threads.add(threading.get_ident())
        if among_first:
            gate.wait()
        user = json.loads(request.content)["messages"][1]["content"]
        return httpx.Response(200, json=_completion(f"echo:{len(user)}"))

    provider = _provider(handler, concurrency=4)
    config = RunConfig(
        provider="openai", model="org/model", dataset=SEEDS, condition="all", output_dir=tmp_path
    )
    units = [Unit(seed=seed, strategy=strategy, condition="defended") for seed in held_out]
    kwargs = dict(
        config=config, provider=provider, seeds_path=str(SEEDS), seeds_sha256=sha, phase="test"
    )
    first = run_units(units=units, **kwargs)
    assert (first.written, first.skipped, first.backend_errors) == (12, 0, 0)
    assert len(threads) == 4 and not gate.broken
    rows, _ = load_results(tmp_path / "raw_results.jsonl")
    assert [row["case_id"] for row in rows] == [seed.id for seed in held_out]
    for row in rows:
        assert row["response_text"] == f"echo:{len(row['user_message'])}"
        assert row["provider"] == "openai"
        assert row["provider_metadata"]["rendered_prompt"] == "<rendered>"
    again = run_units(units=units, **kwargs)
    assert (again.written, again.skipped) == (0, 12)


def test_tool_choice_auto_and_parsed_calls_are_recorded() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "Grant", "arguments": "{}"}}
            ],
        }
        return httpx.Response(
            200,
            json={"model": "m", "choices": [{"finish_reason": "tool_calls", "message": message}]},
        )

    tools = [{"type": "function", "function": {"name": "Grant"}}]
    response = _provider(handler).generate(_request(tools=tools, tool_choice="auto"))
    assert seen[0]["tool_choice"] == "auto"
    assert response.text == "" and response.error_type is None
    assert response.provider_metadata is not None
    assert response.provider_metadata["tool_calls"] == [{"name": "Grant", "arguments": "{}"}]


def test_a_dropped_pooled_connection_is_retried_then_reported() -> None:
    """A proxy closing a pooled connection (RemoteProtocolError) is retried, bounded."""
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return httpx.Response(200, json=_completion("Fine."))

    response = _provider(flaky).generate(_request())
    assert response.error_type is None and response.text == "Fine." and calls["n"] == 2

    def always(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    calls["n"] = 0
    failed = _provider(always).generate(_request())
    assert failed.error_type == "connection" and calls["n"] == 3
