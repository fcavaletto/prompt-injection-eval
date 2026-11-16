"""WP7 audit: the checker, the stored findings, and AgentDojo regressions (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from prompt_injection_eval import wp7

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results-published" / "wp7-audit-2026-11-16"


def _prompt(result_text: str, *, call: bool = True) -> str:
    fx = wp7.load_fixture()
    tools = json.dumps(
        [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in fx["tools"]
        ]
    )
    parts = [f"SYSTEM {fx['system']} TOOLS {tools}", f"USER {fx['user']}"]
    if call:
        parts.append('CALL read_channel_messages {"channel": "general-MARKARG"}')
    parts.append(f"RESULT {result_text}")
    return "\n".join(parts)


@pytest.mark.parametrize(
    "encode",
    [
        lambda r: yaml.safe_dump(r),
        lambda r: yaml.safe_dump(r, allow_unicode=True, width=8192),
        lambda r: json.dumps(r),
        lambda r: json.dumps(r, ensure_ascii=False),
        lambda r: json.dumps(json.dumps(r)),
        lambda r: json.dumps({"result": [{"type": "text", "content": yaml.safe_dump(r)}]}),
        lambda r: json.dumps(
            json.dumps({"result": [{"type": "text", "content": yaml.safe_dump(r)}]})
        ),
        lambda r: str(r),
    ],
)
def test_checker_accepts_valid_encodings_of_the_payload(encode) -> None:
    fx = wp7.load_fixture()
    found = wp7.check(_prompt(encode(fx["result"])))
    assert found.passed, found.missing
    assert found.payload_form != "normalized"


def test_checker_does_not_depend_on_global_yaml_registrations() -> None:
    before = wp7.payload_forms(wp7.load_fixture()["payload"])

    original = yaml.Dumper.yaml_representers.get(str)
    yaml.add_representer(
        str, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", v, style='"')
    )
    try:
        assert wp7.payload_forms(wp7.load_fixture()["payload"]) == before
    finally:
        if original is not None:
            yaml.add_representer(str, original)


def test_checker_reports_losses() -> None:
    fx = wp7.load_fixture()
    without_payload = [r for r in fx["result"] if "MARK-PAYLOAD" not in r["body"]]
    lost = wp7.check(_prompt(yaml.safe_dump(without_payload)))
    assert not lost.payload and not lost.passed and "payload" in lost.missing
    no_call = wp7.check(_prompt(yaml.safe_dump(fx["result"]), call=False))
    assert not no_call.call and not no_call.passed
    mangled = fx["payload"].replace("MARK-PAYLOAD-7", "MARK-PAYLOAD-7")[:20]
    truncated = wp7.check(_prompt(json.dumps([{"body": mangled}])))
    assert not truncated.payload


def test_stored_audit_rows_recheck_from_stored_renders() -> None:
    audit = json.loads((AUDIT / "audit.json").read_text())
    for row in audit["rows"]:
        if "check" not in row:
            continue
        rendering = (AUDIT / "renders" / f"{row['id']}.txt").read_text()
        assert wp7.check(rendering).row() == row["check"], row["id"]


def test_published_local_traces_split_at_a_token_threshold() -> None:
    summary = json.loads((AUDIT / "agentdojo_local_traces_summary.json").read_text())["summary"]
    for model, found in summary.items():
        assert found["separated_by_a_token_threshold"], model
        assert found["min_tokens_empty_final"] > found["max_tokens_other"]
        assert set(found["empty_final_suites"]) == {"workspace"}
    llama = summary["meta-llama_Llama-3.3-70B-Instruct"]["by_attack"]["important_instructions"]
    assert (llama["published_successes"], llama["empty_final_scored_as_no_success"]) == (219, 29)


# ------------------------------------------------------- AgentDojo 0.1.35 regressions


def _runtime_and_history():
    pytest.importorskip("agentdojo")
    import importlib.util

    spec = importlib.util.spec_from_file_location("wp7_audit", ROOT / "scripts" / "wp7_audit.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agentdojo_local_llm_wraps_tool_results_in_content_blocks() -> None:
    audit = _runtime_and_history()
    from agentdojo.agent_pipeline.llms import local_llm
    from agentdojo.agent_pipeline.llms.local_llm import LocalLLM
    from agentdojo.functions_runtime import EmptyEnv

    fx = wp7.load_fixture()
    runtime = audit._agentdojo_runtime(fx)
    assistant = local_llm._parse_model_output(
        '<function=read_channel_messages>{"channel": "general-MARKARG"}</function>'
    )
    history = audit._agentdojo_history(fx, dict(assistant), runtime)
    client, calls = audit.fake_client("ok")
    LocalLLM(client, "m").query("", runtime, EmptyEnv(), history)
    tool = calls.calls[0]["messages"][-1]
    decoded = json.loads(tool["content"])
    # Intended per the code's 'None' -> 'Success' branch: {"result": "<text>"}. Observed:
    assert isinstance(decoded["result"], list) and decoded["result"][0]["type"] == "text"
    assert "MARK-PAYLOAD-7" in decoded["result"][0]["content"]
    assert "tool_calls" not in calls.calls[0]["messages"][2]


def test_agentdojo_local_llm_turns_a_server_error_into_an_empty_answer(capsys) -> None:
    audit = _runtime_and_history()
    from agentdojo.agent_pipeline.llms.local_llm import LocalLLM
    from agentdojo.functions_runtime import EmptyEnv

    fx = wp7.load_fixture()
    runtime = audit._agentdojo_runtime(fx)
    client, _ = audit.fake_client(error=RuntimeError("maximum context length exceeded"))
    _, _, _, out, _ = LocalLLM(client, "m").query("", runtime, EmptyEnv(), [])
    last = out[-1]
    assert last["role"] == "assistant" and last["tool_calls"] == []
    assert last["content"][0]["content"] == ""
    assert "maximum context length" in capsys.readouterr().out  # printed, not recorded


def test_agentdojo_prompting_llm_sends_the_system_text_twice() -> None:
    audit = _runtime_and_history()
    from agentdojo.agent_pipeline.llms.prompting_llm import PromptingLLM
    from agentdojo.functions_runtime import EmptyEnv
    from agentdojo.types import text_content_block_from_string

    fx = wp7.load_fixture()
    runtime = audit._agentdojo_runtime(fx)
    history = [
        {"role": "system", "content": [text_content_block_from_string(fx["system"])]},
        {"role": "user", "content": [text_content_block_from_string(fx["user"])]},
    ]
    client, calls = audit.fake_client("<function-call>[]</function-call><answer>x</answer>")
    PromptingLLM(client, "meta-llama/Llama-3-70b-chat-hf").query("", runtime, EmptyEnv(), history)
    messages = calls.calls[0]["messages"]
    assert [m["role"] for m in messages] == ["system", "developer", "user"]
    assert fx["system"] in messages[0]["content"] and messages[1]["content"] == fx["system"]


@pytest.mark.skipif("WP7_EXT" not in __import__("os").environ, reason="needs the pinned clones")
def test_toolhazard_formatter_skips_yaml_for_non_string_output() -> None:
    import ast
    import importlib.util
    import os
    from typing import Any

    spec = importlib.util.spec_from_file_location("wp7_audit", ROOT / "scripts" / "wp7_audit.py")
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    path = Path(os.environ["WP7_EXT"]) / "ToolHazard" / "eval" / "agent" / "task_solve_agent.py"
    fmt = audit.load_functions(
        path,
        ["_coerce_to_obj_maybe", "_format_tool_output_text"],
        {"json": json, "ast": ast, "yaml": yaml, "Any": Any},
    )["_format_tool_output_text"]
    assert fmt("{'success': True}") == "success: true"  # strings: YAML
    assert fmt({"success": True}) == "{'success': True}"  # objects: Python repr, not YAML
