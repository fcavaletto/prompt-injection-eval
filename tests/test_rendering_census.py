"""Pins the published rendering census and checks the helpers that produced it."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "results-published" / "rendering-census-2026-11-15"


@pytest.fixture(scope="module")
def census_script():
    pytest.importorskip("yaml")
    spec = importlib.util.spec_from_file_location(
        "rendering_census", ROOT / "scripts" / "rendering_census.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary() -> dict[tuple[str, str], dict[str, str]]:
    with (CENSUS / "summary.csv").open() as handle:
        return {(row["stack"], row["config"]): row for row in csv.DictReader(handle)}


def test_carrier_reports_the_last_role_header(census_script) -> None:
    qwen = (
        "<|im_start|>assistant\n<tool_call>\n{}\n</tool_call><|im_end|>\n"
        "<|im_start|>user\n<tool_response>\n"
    )
    assert census_script.carrier(qwen) == ("<|im_start|>user", "user")
    llama = "<|eot_id|><|start_header_id|>ipython<|end_header_id|>\n\n"
    assert census_script.carrier(llama)[1] == "ipython"
    assert census_script.carrier("no header here") == (None, None)


def test_content_encoding_tells_verbatim_from_escaped(census_script) -> None:
    content = 'line one\nline "two" MARK'
    assert census_script.content_encoding(f"x {content} y", content, "MARK") == "verbatim"
    escaped = json.dumps(content)[1:-1]
    assert census_script.content_encoding(f"x {escaped} y", content, "MARK") == "json_escaped_ascii"
    assert census_script.content_encoding("nothing", content, "MARK") == "absent"
    parts = [{"type": "text", "text": content}]
    assert (
        census_script.content_encoding(f"x {parts!r} y", parts, "MARK")
        == "parts_serialized_as_list"
    )


def test_fixture_variants_describe_the_same_conversation(census_script) -> None:
    fixtures = census_script.load_fixtures()
    hf, tools, _ = census_script.build(fixtures, "multi_turn", "default")
    ollama, _, _ = census_script.build(fixtures, "multi_turn", "default", flavour="ollama")
    assert [m["role"] for m in hf] == [m["role"] for m in ollama]
    assert tools is not None and len(tools) == 4
    as_string, _, _ = census_script.build(fixtures, "single_call", "args_string")
    assert isinstance(as_string[2]["tool_calls"][0]["function"]["arguments"], str)
    _, no_tools, _ = census_script.build(fixtures, "single_call", "no_tools")
    assert no_tools is None


def test_published_census_headline_counts() -> None:
    summary = _summary()
    hf = {config: row for (stack, config), row in summary.items() if stack == "transformers"}
    assert len(hf) == 26
    # The two Study B defects, from pinned template revisions.
    assert hf["phi-4-mini"]["tool_definitions"] == "False"
    assert hf["phi-4-mini"]["completed_call"] == "False"
    assert hf["granite-3.3-8b"]["completed_call"] == "False"
    # A tool result is carried by a user turn on Qwen and by other constructions elsewhere.
    assert {
        hf[m]["result_carrier_role"]
        for m in ("qwen3-8b", "qwen3-32b", "qwen2.5-7b", "granite-4.0-h-small")
    } == {"user"}
    assert hf["hermes-3-8b"]["result_carrier_role"] == "tool"
    assert hf["llama-3.1-8b"]["result_carrier_role"] == "ipython"
    assert hf["gemma-4-12b"]["result_carrier_role"] == "model"
    # Four templates JSON-encode a string tool result themselves.
    encoded = sorted(m for m, row in hf.items() if row["raw_output"].startswith("json_escaped"))
    assert encoded == [
        "gpt-oss-120b",
        "gpt-oss-20b",
        "llama-3.1-8b",
        "llama-3.2-3b",
        "llama-4-maverick",
    ]
    # Same family, different stack.
    ollama = {config: row for (stack, config), row in summary.items() if stack == "ollama_template"}
    assert ollama["hermes3:8b"]["result_carrier_role"] == "user"
    assert ollama["phi4-mini:latest"]["tool_definitions"] == "True"
    assert ollama["llama3.1:8b"]["tool_definitions"] == "False"


def test_vllm_prompts_equal_the_local_rendering() -> None:
    rows = [json.loads(line) for line in (CENSUS / "vllm_replay.jsonl").read_text().splitlines()]
    stored = [row for row in rows if row["stored_prompts"]]
    assert len(stored) == 8
    assert all(
        row["identical_with_arguments_parsed"] == row["stored_prompts"] == 18 for row in stored
    )
    assert {row["config"] for row in rows if not row["stored_prompts"]} == {
        "gpt-oss-20b",
        "gpt-oss-120b",
    }
    qwen25 = next(row for row in stored if row["config"] == "qwen2.5-7b")
    assert qwen25["identical_with_arguments_as_sent"] == 6
