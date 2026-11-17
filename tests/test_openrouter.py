"""OpenRouter adapter, spend ledger and screen: offline with mocked responses. No network call."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from prompt_injection_eval.providers.base import GenerationRequest
from prompt_injection_eval.providers.openrouter import (
    ENDPOINTS,
    PROVIDER_OVERHEAD_TOKENS,
    OpenRouterProvider,
    served_provider,
    worst_case_usd,
)
from prompt_injection_eval.providers.spend_ledger import LedgerBusy, SpendLedger

KEY = "sk-or-test-not-a-real-key"
LUNA, HAIKU = "openai/gpt-6-luna", "anthropic/claude-haiku-5.5"


class Api:
    """A mocked OpenRouter: chat completions from ``chat``; /key reports the cost billed so far."""

    def __init__(self, chat: Any, limit: float | None = 5.0, extra_usage: float = 0.0) -> None:
        self.chat = chat
        self.limit = limit
        self.billed = 0.0
        self.extra_usage = extra_usage
        self.chat_requests = 0
        self.lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/key"):
            used = self.billed + self.extra_usage
            data = {
                "usage": used,
                "limit": self.limit,
                "limit_remaining": None if self.limit is None else self.limit - used,
                "limit_reset": None,
            }
            return httpx.Response(200, json={"data": data})
        with self.lock:
            self.chat_requests += 1
        response = self.chat(request)
        if isinstance(response, httpx.Response) and response.status_code == 200:
            cost = ((response.json().get("usage") or {}).get("cost")) or 0.0
            with self.lock:
                self.billed += cost
        return response


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(
        base_url="https://openrouter.test/api/v1", transport=httpx.MockTransport(handler)
    )


def _provider(handler: Any, path: Path, cap: float = 5.0, calls: int = 100) -> OpenRouterProvider:
    return OpenRouterProvider(
        SpendLedger(path, cap, calls), api_key=KEY, client=_client(handler), retry_wait_seconds=0.0
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
    model: str = LUNA,
    provider: str | None = None,
    calls: list | None = None,
    content: str = "Done.",
    cost: Any = 0.00002,
) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    usage: dict[str, Any] = {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "completion_tokens_details": {"reasoning_tokens": 5},
    }
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-1",
        "model": ENDPOINTS[model].canonical,
        "provider": provider or ENDPOINTS[model].provider_name,
        "choices": [
            {
                "finish_reason": "tool_calls" if calls else "stop",
                "native_finish_reason": "stop",
                "message": message,
            }
        ],
        "usage": usage,
    }


# Routing and records -------------------------------------------------------------------


def test_routing_is_pinned_and_only_supported_parameters_are_sent(tmp_path: Path) -> None:
    seen: list[dict] = []

    def chat(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, json=_ok(seen[-1]["model"]))

    p = _provider(Api(chat), tmp_path / "l.jsonl")
    for model in (LUNA, HAIKU):
        assert p.generate(_request(model)).error_type is None
    for body, slug in zip(seen, ("openai", "anthropic"), strict=True):
        assert body["provider"] == {
            "only": [slug],
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
            "max_price": {"prompt": pytest.approx(0.1), "completion": pytest.approx(0.5)},
        }
        assert "models" not in body and "route" not in body and "temperature" not in body
        assert body["reasoning"] == {"effort": "low"} and body["max_tokens"] == 4096
    assert seen[0]["seed"] == 20261117 and "seed" not in seen[1]


def test_a_recorded_response_holds_no_credential_and_everything_else(tmp_path: Path) -> None:
    p = _provider(Api(lambda r: httpx.Response(200, json=_ok())), tmp_path / "l.jsonl")
    meta = p.generate(_request()).provider_metadata
    assert KEY not in json.dumps(meta) and "Authorization" not in json.dumps(meta)
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
    assert KEY not in (tmp_path / "l.jsonl").read_text()


def test_served_provider_comes_from_the_field_or_the_routing_metadata() -> None:
    assert served_provider({"provider": "OpenAI"}) == "OpenAI"
    meta = {
        "openrouter_metadata": {
            "endpoints": {
                "available": [
                    {"provider": "Azure", "selected": False},
                    {"provider": "OpenAI", "selected": True},
                ]
            }
        }
    }
    assert served_provider(meta) == "OpenAI" and served_provider({}) is None


def test_model_and_provider_mismatches_are_their_own_outcomes(tmp_path: Path) -> None:
    other = _ok()
    other["model"] = "openai/gpt-6-luna-20270101"
    assert (
        _provider(Api(lambda r: httpx.Response(200, json=other)), tmp_path / "a.jsonl")
        .generate(_request())
        .error_type
        == "model_mismatch"
    )
    wrong = _ok(provider="Azure")
    assert (
        _provider(Api(lambda r: httpx.Response(200, json=wrong)), tmp_path / "b.jsonl")
        .generate(_request())
        .error_type
        == "provider_mismatch"
    )


def test_an_unsupported_frozen_parameter_is_refused(monkeypatch, tmp_path: Path) -> None:
    from dataclasses import replace

    from prompt_injection_eval.providers import openrouter

    monkeypatch.setitem(
        openrouter.ENDPOINTS,
        HAIKU,
        replace(ENDPOINTS[HAIKU], params={**ENDPOINTS[HAIKU].params, "seed": 1}),
    )
    with pytest.raises(ValueError, match="not supported"):
        _provider(Api(lambda r: httpx.Response(200, json=_ok())), tmp_path / "l.jsonl").body(
            _request(HAIKU)
        )


# The spend ledger: acceptance tests for repair 1 ---------------------------------------


def test_the_bound_is_bytes_plus_an_allowance_and_uses_the_higher_tier() -> None:
    body = {"messages": [{"role": "user", "content": "é" * 100}], "tools": [], "max_tokens": 4096}
    tokens = len(json.dumps(body, ensure_ascii=False).encode()) + PROVIDER_OVERHEAD_TOKENS
    assert worst_case_usd(body, ENDPOINTS[LUNA]) == pytest.approx(tokens * 1e-7 + 4096 * 5e-7)
    big = {"messages": [{"role": "user", "content": "x" * 300000}], "tools": [], "max_tokens": 4096}
    tokens = len(json.dumps(big).encode()) + PROVIDER_OVERHEAD_TOKENS
    assert worst_case_usd(big, ENDPOINTS[LUNA]) == pytest.approx(tokens * 2e-7 + 4096 * 7.5e-7)


def test_a_timeout_after_sending_stays_charged(tmp_path: Path) -> None:
    def chat(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no response", request=request)

    p = _provider(Api(chat), tmp_path / "l.jsonl")
    assert p.generate(_request()).error_type == "timeout"
    state = p.ledger.state()
    assert state["spent_usd"] == 0 and state["unresolved_usd"] > 0
    assert state["committed_usd"] == state["unresolved_usd"]


def test_missing_usage_is_charged_at_the_bound_not_zero(tmp_path: Path) -> None:
    p = _provider(Api(lambda r: httpx.Response(200, json=_ok(cost=None))), tmp_path / "l.jsonl")
    assert p.generate(_request()).error_type is None
    worst = worst_case_usd(p.body(_request()), ENDPOINTS[LUNA])
    assert p.ledger.committed() == pytest.approx(worst, rel=1e-9) and p.ledger.spent == 0


def test_a_refused_connection_is_released_with_evidence(tmp_path: Path) -> None:
    def chat(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    p = _provider(Api(chat), tmp_path / "l.jsonl")
    assert p.generate(_request()).error_type == "connection"
    assert p.ledger.state()["committed_usd"] == 0
    assert '"op": "release"' in (tmp_path / "l.jsonl").read_text()


def test_a_crash_in_flight_and_a_restart_restore_everything(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    ledger = SpendLedger(path, 1.0, 10)
    a = ledger.reserve(0.1)
    assert a is not None
    ledger.settle(a, 0.03, "usage.cost")
    ledger.reserve(0.2)  # in flight when the process dies: never settled
    ledger.close()  # stands in for the crash: nothing else is written
    again = SpendLedger(path, 1.0, 10)
    state = again.state()
    assert state["spent_usd"] == pytest.approx(0.03)
    assert state["unresolved_usd"] == pytest.approx(0.2)  # charged until reconciled
    assert state["calls"] == 2
    assert again.reserve(0.8) is None and again.reserve(0.7) is not None  # 0.03 + 0.2 + 0.7 <= 1
    again.close()


def test_one_spender_at_a_time_in_process_and_across_processes(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    with SpendLedger(path, 1.0, 10):
        with pytest.raises(LedgerBusy):
            SpendLedger(path, 1.0, 10)
        code = (
            "import sys; from pathlib import Path;"
            "from prompt_injection_eval.providers.spend_ledger import SpendLedger, LedgerBusy\n"
            "try:\n    SpendLedger(Path(sys.argv[1]), 1.0, 10)\n"
            "except LedgerBusy:\n    sys.exit(7)\nsys.exit(0)"
        )
        assert subprocess.run([sys.executable, "-c", code, str(path)], check=False).returncode == 7
    with SpendLedger(path, 1.0, 10):  # released on close
        pass


def test_concurrent_requests_never_commit_beyond_the_cap(tmp_path: Path) -> None:
    api = Api(lambda r: httpx.Response(200, json=_ok(cost=None)))  # every attempt stays charged
    request = _request()
    probe = _provider(api, tmp_path / "probe.jsonl")
    worst = worst_case_usd(probe.body(request), ENDPOINTS[LUNA])
    p = _provider(api, tmp_path / "l.jsonl", cap=worst * 3.5)
    results: list[Any] = []
    threads = [
        threading.Thread(target=lambda: results.append(p.generate(request))) for _ in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    refused = sum(r.error_type == "budget_exhausted" for r in results)
    assert refused == 7 and p.ledger.committed() <= p.ledger.cap_usd


def test_a_reported_cost_above_its_reservation_halts_spending(tmp_path: Path) -> None:
    api = Api(lambda r: httpx.Response(200, json=_ok(cost=1.0)))  # far beyond any reservation
    p = _provider(api, tmp_path / "l.jsonl", cap=5.0)
    assert p.generate(_request()).error_type is None
    assert p.ledger.state()["halted"]
    before = api.chat_requests
    assert p.generate(_request()).error_type == "budget_exhausted" and api.chat_requests == before


def test_preflight_requires_a_service_side_limit_and_reconcile_detects_hidden_spend(
    tmp_path: Path,
) -> None:
    p = _provider(Api(lambda r: httpx.Response(200, json=_ok()), limit=None), tmp_path / "a.jsonl")
    assert p.preflight()
    p = _provider(Api(lambda r: httpx.Response(200, json=_ok()), limit=50.0), tmp_path / "b.jsonl")
    assert any("exceeds the cap" in x for x in p.preflight())
    api = Api(lambda r: httpx.Response(200, json=_ok()), limit=5.0)
    p = _provider(api, tmp_path / "c.jsonl")
    assert p.preflight() == [] and p.ledger.baseline is not None
    p.generate(_request())
    assert p.reconcile()["consistent"]
    api.extra_usage = 1.0  # spend the ledger never saw
    assert not p.reconcile()["consistent"] and p.ledger.state()["halted"]


# Episodes ------------------------------------------------------------------------------

agentdojo = pytest.importorskip("agentdojo")


def _agent(
    follow: list | None = None,
    bad_json: bool = False,
    provider: str | None = None,
    cost: Any = 0.00002,
):  # noqa: ANN202
    """A mocked model: issues ``follow`` as tool calls after the replayed prefix, then stops."""
    follow = follow or []

    def chat(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        model = body["model"]
        own = [
            m
            for m in body["messages"]
            if m["role"] == "assistant"
            and any(c["id"].startswith("call_") for c in m.get("tool_calls") or [])
        ]
        if len(own) < len(follow):
            name, args = follow[len(own)]
            arguments = "{not json" if bad_json else json.dumps(args)
            calls = [
                {
                    "id": f"x{len(own)}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ]
            return httpx.Response(
                200, json=_ok(model, provider, calls=calls, content="", cost=cost)
            )
        return httpx.Response(200, json=_ok(model, provider, cost=cost))

    return chat


def test_episode_scores_environment_state_and_verifies_the_request(tmp_path: Path) -> None:
    from prompt_injection_eval.pilot import episode, screen, stage1
    from prompt_injection_eval.pilot.screen_cli import settings

    p = stage1.PATHWAYS[0]
    spec = episode.Spec(p.suite, "attack", "json@text", p.user_task, p.goal, screen.FORGED, 0)
    trace = episode.run(
        spec, _provider(Api(_agent([p.following[1]])), tmp_path / "l.jsonl"), settings(LUNA)
    )
    assert (
        trace["status"] == "completed"
        and trace["security"] is True
        and trace["delivery_defects"] == []
    )
    assert KEY not in json.dumps(trace)
    carrier = trace["turns"][0]["api"]["sent_request"]["messages"][3]
    assert carrier["role"] == "tool" and carrier["content"].startswith("{")


def test_malformed_tool_calls_and_api_failures_are_distinct(tmp_path: Path) -> None:
    from prompt_injection_eval.pilot import episode, screen, stage1
    from prompt_injection_eval.pilot.screen_cli import settings

    p = stage1.PATHWAYS[0]
    spec = episode.Spec(p.suite, "attack", "text", p.user_task, p.goal, screen.INSTRUCTION, 0)
    malformed = episode.run(
        spec,
        _provider(Api(_agent([p.following[1]], bad_json=True)), tmp_path / "a.jsonl"),
        settings(LUNA),
    )
    assert malformed["status"] == "completed" and malformed["totals"]["invalid_argument_json"] == 1
    failed = episode.run(
        spec,
        _provider(Api(lambda r: httpx.Response(500, text="err")), tmp_path / "b.jsonl"),
        settings(LUNA),
    )
    assert failed["status"] == "api_error" and failed["security"] is None


# The screen: calibration gate and matched-case report ----------------------------------


def test_screen_design_is_the_eligible_explicit_manifest() -> None:
    from prompt_injection_eval.pilot import screen

    d = screen.design()
    assert d["eligibility"]["requested_cases"] == 24 and d["eligibility"]["eligible_cases"] == 5
    assert d["episodes"] == 60 and d["calibration_episodes"] == 4
    assert {u.fmt for u in screen.units()} == {"text", "json@text"}
    frozen = json.loads(
        (Path(__file__).resolve().parents[1] / "data" / "screen" / "design.json").read_text()
    )
    assert frozen == json.loads(json.dumps(d))


@pytest.mark.parametrize(
    ("bad", "expected"),
    [({"provider": "Azure"}, "endpoint_mismatch"), ({"cost": None}, "no usable reported cost")],
)
def test_a_failing_calibration_makes_zero_screen_requests(
    tmp_path: Path, bad: dict, expected: str
) -> None:
    from prompt_injection_eval.pilot import screen_cli

    api = Api(_agent(**bad))
    calibration_requests = []
    for _attempt in range(2):  # a resume must fail the same way
        with pytest.raises(screen_cli.CalibrationFailed, match=expected):
            screen_cli.run(tmp_path, 5.0, calibration_only=False, client=_client(api), api_key=KEY)
        assert not (tmp_path / "screen").exists()
        calibration_requests.append(api.chat_requests)
    # Every request was a calibration request: each model's two calibration units, at most.
    assert calibration_requests[-1] <= 2 * len(screen_cli.screen_models()) * 16


def test_a_passing_calibration_then_the_screen_with_matched_reporting(tmp_path: Path) -> None:
    import contextlib
    import io

    from prompt_injection_eval.pilot import screen_cli

    api = Api(_agent())
    with contextlib.redirect_stdout(io.StringIO()):
        out = screen_cli.run(
            tmp_path, 5.0, calibration_only=False, client=_client(api), api_key=KEY
        )
    assert out["calibration_problems"] == [] and out["screen/openai/gpt-6-luna"]["statuses"] == {
        "completed": 30
    }
    assert out["reconcile/openai/gpt-6-luna"]["consistent"]
    path = screen_cli._dir(tmp_path, LUNA) / "traces.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    drop = next(
        r
        for r in rows
        if r["mode"] == "clean"
        and r["fmt"] == "json@text"
        and (r["suite"], r["user_task"]) == ("banking", "user_task_0")
    )
    path.write_text("".join(json.dumps(r) + "\n" for r in rows if r is not drop))
    result = screen_cli.report(tmp_path, tmp_path / "report")
    benign = result["models"][LUNA]["matched"]["benign"]
    assert (
        benign["accepted"]["missing_counterpart"] == ["F1"]
        and "F1" not in benign["accepted"]["matched_cases"]
    )
    assert result["models"][LUNA]["matched"]["forged"]["accepted"]["matched_cases"] == [
        "F1",
        "F2",
        "F3",
    ]
