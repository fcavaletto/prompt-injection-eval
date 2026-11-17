#!/usr/bin/env python
"""Build the base histories of the delivery-checker validation corpus. No inference.

Takes one stored pilot request (Granite, banking, JSON, ``text_fake_turn``,
``user_task_12|injection_task_6``: the request after a model turn with three parallel
``send_money`` calls; its prefix carries the payload and an integer argument), derives
the same conversation in the text format by re-serializing every tool record, and
renders all four (two pinned templates x two formats) with the tokenizer files at the
pilot's pinned revisions. Writes ``tests/fixtures/checker_corpus/base_cases.json`` so
that the tests need no tokenizer.

    HF_HUB_OFFLINE=1 python scripts/build_checker_corpus.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval.pilot import serialize  # noqa: E402
from prompt_injection_eval.pilot.runner import read_traces  # noqa: E402

TRACE = ROOT / "results-published/pilot-2026-11-16/granite-4.0-h-small/select/traces.jsonl"
UNIT = ("attack/text_fake_turn/json", "user_task_12|injection_task_6")
TEMPLATES = {
    "qwen3": (
        "Qwen/Qwen3-32B",
        "9216db5781bf21249d130ec9da846c4624c16137",
        {"enable_thinking": False},
    ),
    "granite4": ("ibm-granite/granite-4.0-h-small", "b8c0982bab7fde4eb48110f5a069527c008fab39", {}),
}
OUT = ROOT / "tests/fixtures/checker_corpus/base_cases.json"


def main() -> None:
    import transformers

    from prompt_injection_eval.pilot import adapter

    trace = next(
        t for t in read_traces(TRACE) if (t["condition"], t["pair"]) == UNIT and t["run"] == 0
    )
    messages = trace["messages"]
    # The request for model turn 1: everything before the second model-written assistant turn.
    assistant = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    cut = assistant[len(trace["prefix_calls"]) + 1]
    request_json = messages[:cut]
    records = {
        i: json.loads(m["content"]) for i, m in enumerate(request_json) if m["role"] == "tool"
    }
    payload_index = 3 + 2 * trace["injection_index"]
    tools = list(adapter.wire_tools("banking"))
    cases = []
    for fmt in ("json", "text"):
        request = [
            dict(m, content=serialize.serialize(records[i], fmt)) if m["role"] == "tool" else m
            for i, m in enumerate(request_json)
        ]
        assert request == request_json or fmt == "text"
        for name, (repo, revision, extra) in TEMPLATES.items():
            tok = transformers.AutoTokenizer.from_pretrained(repo, revision=revision, token=False)
            rendered = tok.apply_chat_template(
                request, tools=tools, add_generation_prompt=True, tokenize=False, **extra
            )
            cases.append(
                {
                    "id": f"{name}-{fmt}",
                    "template": name,
                    "tokenizer": f"{repo}@{revision}",
                    "template_kwargs": extra,
                    "fmt": fmt,
                    "messages": request,
                    "records": {str(k): v for k, v in records.items()},
                    "payload": trace["payload"],
                    "payload_index": payload_index,
                    "rendered": rendered,
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "source": f"{TRACE.relative_to(ROOT)} {UNIT} run 0, request for model turn 1",
                "tools_suite": "banking",
                "tools": tools,
                "cases": cases,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"wrote {len(cases)} base cases to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
