"""OpenRouter adapter and screen, offline with mocked responses. No network call is made."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from prompt_injection_eval.providers.base import GenerationRequest
from prompt_injection_eval.providers.openrouter import (
    ENDPOINTS,
    OpenRouterProvider,
    SpendGuard,
    worst_case_usd,
)

KEY = "sk-or-test-not-a-real-key"
LUNA, HAIKU = "openai/gpt-6-luna", "anthropic/claude-haiku-5.5"


def _provider(handler: Any, cap: float = 5.0, calls: int = 100) -> OpenRouterProvider:
    client = httpx.Client(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler)
    )
    return OpenRouterProvider(
        SpendGuard(cap, calls), api_key=KEY, client=client, retry_wait_seconds=0.0
    )


def _request(model: str = LUNA, **kw: Any) -> GenerationRequest:
    values: dict[str, Any] = dict(
        model=model,
        system_message="",
        user_message="",
        temperature=0.0,
        seed=20261115,
        max_output_tokens=64,
        timeout_seconds=5.0,
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        tools=[
            {"type": "function", "function": {"name": "f", "description": "d", "parameters": {}}}
        ],
        tool_choice="auto",
    )
    values.update(kw)
    return GenerationRequest(**values)


def _ok(
    model: str = LUNA, provider: str = "OpenAI", calls: list | None = None, content: str = "Done."
) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return {
        "id": "gen-1",
        "model": ENDPOINTS[model].canonical,
        "provider": provider,
        "choices": [
            {
                "finish_reason": "tool_calls" if calls else "stop",
                "native_finish_reason": "stop",
                "message": message,
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "cost": 0.00002,
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
    }


def test_routing_is_pinned_and_only_supported_parameters_are_sent() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        return httpx.Response(
            200,
            json=_ok(
                LUNA if seen[-1]["model"] == LUNA else HAIKU,
                "OpenAI" if seen[-1]["model"] == LUNA else "Anthropic",
            ),
        )

    p = _provider(handler)
    for model in (LUNA, HAIKU):
        response = p.generate(_request(model))
        assert response.error_type is None, response.error_message
    luna, haiku = seen
    for body, slug in ((luna, "openai"), (haiku, "anthropic")):
        assert body["provider"] == {
            "only": [slug],
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
            "max_price": {"prompt": pytest.approx(0.1), "completion": pytest.approx(0.5)},
        }
        assert "models" not in body and "route" not in body and "temperature" not in body
        assert body["reasoning"] == {"effort": "low"} and body["max_tokens"] == 4096
    assert luna["seed"] == 20261117 and "seed" not in haiku  # Haiku's endpoint lists no seed


def test_a_recorded_response_holds_no_credential_and_everything_else() -> None:
    p = _provider(lambda r: httpx.Response(200, json=_ok()))
    meta = p.generate(_request()).provider_metadata
    text = json.dumps(meta)
    assert KEY not in text and "Authorization" not in text
    for key in (
        "sent_request",
        "raw_response",
        "attempts",
        "reported_model",
        "reported_provider",
        "usage",
        "spend",
    ):
        assert key in meta
    assert meta["reasoning_tokens"] == 5 and meta["delivery_verification"].startswith(
        "request-level"
    )


def test_retries_are_bounded_and_recorded() -> None:
    state = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(503, text="busy")
        if state["n"] == 2:
            raise httpx.RemoteProtocolError("Server disconnected")
        return httpx.Response(200, json=_ok())

    response = _provider(flaky).generate(_request())
    assert response.error_type is None
    assert [a["outcome"] for a in response.provider_metadata["attempts"]] == [
        "retryable_status",
        "connection",
        "ok",
    ]
    hard = _provider(lambda r: httpx.Response(400, text="bad request")).generate(_request())
    assert hard.error_type == "http_status" and len(hard.provider_metadata["attempts"]) == 1


def test_model_and_provider_mismatches_are_their_own_outcomes() -> None:
    other = _ok()
    other["model"] = "openai/gpt-6-luna-20270101"
    assert (
        _provider(lambda r: httpx.Response(200, json=other)).generate(_request()).error_type
        == "model_mismatch"
    )
    wrong = _ok(provider="Azure")
    assert (
        _provider(lambda r: httpx.Response(200, json=wrong)).generate(_request()).error_type
        == "provider_mismatch"
    )


def test_the_cap_holds_under_concurrency_and_refuses_without_sending() -> None:
    sent = {"n": 0}
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with lock:
            sent["n"] += 1
        return httpx.Response(200, json=_ok())

    request = _request()
    p = _provider(handler)
    worst = worst_case_usd(p.body(request), ENDPOINTS[LUNA])
    p = _provider(handler, cap=worst * 3.5)
    results: list[Any] = []
    threads = [
        threading.Thread(target=lambda: results.append(p.generate(request))) for _ in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in results if r.error_type is None]
    refused = [r for r in results if r.error_type == "budget_exhausted"]
    assert len(ok) + len(refused) == 10 and sent["n"] == len(ok)
    assert p.guard.spent + p.guard.reserved <= p.guard.cap_usd + 1e-12


def test_an_unsupported_frozen_parameter_is_refused(monkeypatch) -> None:
    from dataclasses import replace

    from prompt_injection_eval.providers import openrouter

    bad = replace(ENDPOINTS[HAIKU], params={**ENDPOINTS[HAIKU].params, "seed": 1})
    monkeypatch.setitem(openrouter.ENDPOINTS, HAIKU, bad)
    with pytest.raises(ValueError, match="not supported"):
        _provider(lambda r: httpx.Response(200, json=_ok())).body(_request(HAIKU))


# Episodes and the screen ------------------------------------------------------------

agentdojo = pytest.importorskip("agentdojo")


def _agent(follow: list[tuple[str, dict]], model: str = LUNA, bad_json: bool = False):  # noqa: ANN202
    """A mocked model: issues ``follow`` as tool calls after the replayed prefix, then stops."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        own = [
            m
            for m in body["messages"]
            if m["role"] == "assistant"
            and any(c["id"].startswith("call_") for c in m.get("tool_calls") or [])
        ]
        made = len(own)
        if made < len(follow):
            name, args = follow[made]
            arguments = "{not json" if bad_json else json.dumps(args)
            calls = [
                {
                    "id": f"x{made}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ]
            return httpx.Response(
                200, json=_ok(model, ENDPOINTS[model].provider_name, calls=calls, content="")
            )
        return httpx.Response(200, json=_ok(model, ENDPOINTS[model].provider_name))

    return handler


def test_episode_scores_environment_state_and_verifies_the_request() -> None:
    from prompt_injection_eval.pilot import episode, screen, stage1
    from prompt_injection_eval.pilot.screen_cli import settings

    p = stage1.PATHWAYS[0]  # banking user_task_0 x injection_task_5, forged payee IBAN
    spec = episode.Spec(p.suite, "attack", "json@text", p.user_task, p.goal, screen.FORGED, 0)
    trace = episode.run(spec, _provider(_agent([p.following[1]])), settings(LUNA))
    assert trace["status"] == "completed", trace["status_detail"]
    assert trace["security"] is True and trace["delivery_defects"] == []
    assert KEY not in json.dumps(trace)
    first = trace["turns"][0]["api"]
    assert (
        first["reported_provider"] == "OpenAI"
        and first["sent_request"]["provider"]["allow_fallbacks"] is False
    )
    carrier = first["sent_request"]["messages"][3]
    assert carrier["role"] == "tool" and carrier["content"].startswith("{")  # carrier in JSON
    benign = episode.run(
        episode.Spec(p.suite, "attack", "json@text", p.user_task, p.goal, screen.FORGED, 0),
        _provider(_agent([])),
        settings(LUNA),
    )
    assert benign["security"] is False  # nothing done, nothing scored


def test_malformed_tool_calls_and_api_failures_are_distinct() -> None:
    from prompt_injection_eval.pilot import episode, screen, stage1
    from prompt_injection_eval.pilot.screen_cli import settings

    p = stage1.PATHWAYS[0]
    spec = episode.Spec(p.suite, "attack", "text", p.user_task, p.goal, screen.INSTRUCTION, 0)
    malformed = episode.run(
        spec, _provider(_agent([p.following[1]], bad_json=True)), settings(LUNA)
    )
    assert malformed["status"] == "completed" and malformed["totals"]["invalid_argument_json"] == 1
    failed = episode.run(spec, _provider(lambda r: httpx.Response(500, text="err")), settings(LUNA))
    assert failed["status"] == "api_error" and failed["security"] is None
    assert failed["failed_turn"]["api"]["attempts"][0]["status"] == 500


def test_screen_design_is_the_eligible_explicit_manifest() -> None:
    from prompt_injection_eval.pilot import screen, stage1

    d = screen.design()
    assert d["eligibility"] == {**d["eligibility"], "requested_cases": 24, "eligible_cases": 5}
    assert d["episodes"] == 60 and d["calibration_episodes"] == 4
    units = screen.units()
    assert {u.fmt for u in units} == {"text", "json@text"}  # only the carrier changes
    for u in units:
        if u.attack == screen.FORGED:
            assert stage1.render(u, "") == stage1.pathway(
                u.suite, u.user_task, u.injection_task
            ).payload(screen.FORGED)
    frozen = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "screen" / "design.json").read_text()
    )
    assert frozen == json.loads(json.dumps(d))


def test_screen_run_respects_a_cumulative_cap_with_a_mocked_api(tmp_path: Path) -> None:
    import contextlib
    import io

    from prompt_injection_eval.pilot.screen_cli import recorded_spend, report, run

    provider = _provider(_agent([]), cap=5.0, calls=1200)
    with contextlib.redirect_stdout(io.StringIO()):
        out = run(tmp_path, 5.0, calibration_only=False, provider=provider)
    assert out["screen/openai/gpt-6-luna"]["statuses"].get("completed") == 30
    spent = recorded_spend(tmp_path)
    assert spent == pytest.approx(provider.guard.spent)
    with pytest.raises(Exception, match="at most"):
        run(tmp_path, 6.0, calibration_only=True, provider=provider)
    result = report(tmp_path, tmp_path / "report")
    assert result["delivery_verification"].startswith("request-level")
    assert set(result["models"]) == {LUNA, HAIKU}
