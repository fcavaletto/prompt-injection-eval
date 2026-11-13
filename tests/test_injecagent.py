"""Study B: InjecAgent loading, conversations, scoring, and a run against a fake server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from prompt_injection_eval.injecagent import (
    CONDITIONS,
    SECURITY_RULE,
    Settings,
    build_conversation,
    load_cases,
    load_tools,
    run,
    score,
    write_report,
)
from prompt_injection_eval.providers.openai_compat import OpenAICompatProvider
from prompt_injection_eval.results_io import load_results


@pytest.fixture(scope="module")
def cases():
    return load_cases()


@pytest.fixture(scope="module")
def tools():
    return load_tools()


def test_vendored_data_matches_injecagent(cases, tools) -> None:
    assert len(cases) == 2108 and len(tools) == 330
    counts: dict[tuple[str, str], int] = {}
    for case in cases:
        counts[(case.attack, case.setting)] = counts.get((case.attack, case.setting), 0) + 1
        assert case.user_tool in tools and all(name in tools for name in case.attacker_tools)
    assert counts == {
        ("dh", "base"): 510,
        ("dh", "enhanced"): 510,
        ("ds", "base"): 544,
        ("ds", "enhanced"): 544,
    }
    assert len({case.id for case in cases}) == 2108


def test_conditions_change_only_placement_and_rule(cases, tools) -> None:
    case = cases[0]
    built = {name: build_conversation(case, name, tools) for name in CONDITIONS}
    for name, (messages, offered) in built.items():
        assert [tool["function"]["name"] for tool in offered] == [
            case.user_tool,
            *case.attacker_tools,
        ]
        user = messages[1]["content"]
        assert user.startswith(case.user_instruction)
        assert (SECURITY_RULE in user) == name.endswith("_defended")
    user_messages, _ = built["user"]
    assert [m["role"] for m in user_messages] == ["system", "user"]
    assert case.tool_response in user_messages[1]["content"]
    raw, _ = built["tool"]
    encoded, _ = built["tool_json"]
    assert [m["role"] for m in raw] == ["system", "user", "assistant", "tool"]
    assert raw[-1]["content"] == case.tool_response
    assert encoded[-1]["content"] == json.dumps(case.tool_response)
    assert raw[:-1] == encoded[:-1]
    assert json.loads(raw[2]["tool_calls"][0]["function"]["arguments"]) == case.tool_parameters


def test_benign_case_has_no_attacker_instruction(cases) -> None:
    case = next(c for c in cases if c.setting == "base")
    benign = case.benign()
    assert "<Attacker Instruction>" not in benign.tool_response
    assert "Amy" not in benign.tool_response or "grant" not in benign.tool_response


def test_scoring_follows_injecagent(cases) -> None:
    case = cases[0]
    target, user_tool = case.target_tool, case.user_tool
    assert score(case, [{"name": target}], "")["injecagent_eval"] == "succ"
    assert score(case, [{"name": user_tool}], "let me try again")["injecagent_eval"] == "unsucc"
    assert score(case, [{"name": user_tool}], "")["injecagent_eval"] == "invalid"
    assert score(case, [{"name": "SomethingElse"}], "")["injecagent_eval"] == "invalid"
    none = score(case, None, f"I will call {target} now")
    assert none["injecagent_eval"] == "unsucc" and none["attack_score"] == "failure"
    assert none["target_in_text_unparsed"] is True


def _server(target_by_user: dict[str, str]) -> Any:
    """Calls the attacker tool when the document is in a tool result, refuses otherwise."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"version": "0.99.0", "data": []})
        body = json.loads(request.content)
        assert body["tool_choice"] == "auto" and body["tools"]
        roles = [m["role"] for m in body["messages"]]
        message: dict[str, Any] = {"role": "assistant", "content": "Here are the details."}
        if "tool" in roles:
            name = target_by_user[body["messages"][1]["content"].split("\n")[0]]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "x", "type": "function", "function": {"name": name, "arguments": "{}"}}
                ],
            }
        return httpx.Response(
            200,
            json={
                "model": "org/model",
                "prompt_text": "<rendered>",
                "choices": [{"finish_reason": "stop", "message": message}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )

    return handler


def test_run_scores_resumes_and_reports(cases, tools, tmp_path: Path) -> None:
    picked = cases[:4] + cases[-4:]
    targets = {case.user_instruction: case.target_tool for case in picked}
    client = httpx.Client(
        base_url="https://srv.example.test", transport=httpx.MockTransport(_server(targets))
    )
    provider = OpenAICompatProvider(
        base_url="https://srv.example.test", client=client, concurrency=4, retry_wait_seconds=0
    )
    settings = Settings(model="org/model")
    kwargs: dict[str, Any] = dict(
        cases=picked, conditions=CONDITIONS, tools=tools, provider=provider, settings=settings
    )
    first = run(output_dir=tmp_path / "m", **kwargs)
    assert (first.written, first.backend_errors) == (48, 0)
    again = run(output_dir=tmp_path / "m", **kwargs)
    assert (again.written, again.skipped) == (0, 48)
    rows, _ = load_results(tmp_path / "m" / "raw_results.jsonl")
    by_condition: dict[str, list[str]] = {}
    for row in rows:
        by_condition.setdefault(row["condition"], []).append(row["injecagent_eval"])
        assert row["provider"] == "openai" and "srv.example" not in json.dumps(row)
    assert set(by_condition["tool_defended"]) == {"succ"}
    assert set(by_condition["user_defended"]) == {"unsucc"}
    # Full rendered prompts are kept for three units per condition; every row has a hash.
    assert sum(1 for row in rows if row.get("rendered_prompt")) == 3 * len(CONDITIONS)
    assert all(row.get("rendered_prompt_sha256") for row in rows)

    summary = write_report({"m": rows}, tmp_path / "report")
    primary = [row for row in summary["comparisons"] if row["family"] == "primary"]
    assert (primary[0]["first_successes"], primary[0]["second_successes"]) == (0, 8)
    assert summary["verdict"]["models"] == 1 and summary["verdict"]["replicates"] is False
    assert (tmp_path / "report" / "report.md").read_text().startswith("# InjecAgent")
