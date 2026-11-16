"""WP7: AgentDojo's published LocalLLM traces, reconstructed offline.

For each published trace of a model run with AgentDojo's ``local`` provider, rebuild the
last request LocalLLM sent (every message before the final assistant turn, formatted by
LocalLLM's own code with the suite's tools) and count its tokens with the model's chat
template. A trace whose final assistant turn is empty, with no tool call, is what
LocalLLM writes when the server request raised (``chat_completion_request`` returns ''
on any exception). If those traces, and only those, have requests above a sharp token
threshold, the empty turns are consistent with a context-length limit on the server.

No model is called. Needs agentdojo==0.1.35, the AgentDojo repository at tag v0.1.35
(for ``runs/``), and the tokenizer files of the template named below.

    python scripts/wp7_agentdojo_traces.py /path/to/agentdojo --out results-published/wp7-audit-2026-11-16
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

TEMPLATE = ("unsloth/Llama-3.3-70B-Instruct", "99cd0d2c829e92a67c844f9144c2509632e5c87f")
MODELS = ("meta-llama_Llama-3.3-70B-Instruct", "Meta-SecAlign-70B")


def text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):
        return "".join(b.get("content") or "" for b in content if isinstance(b, dict))
    return content or ""


def is_empty_final(messages: list[dict[str, Any]]) -> bool:
    last = messages[-1]
    return last["role"] == "assistant" and not text(last).strip() and not last.get("tool_calls")


def request_for(messages: list[dict[str, Any]], runtime: Any) -> list[dict[str, Any]]:
    """The request LocalLLM.query builds from these messages (captured, not sent)."""
    from types import SimpleNamespace

    from agentdojo.agent_pipeline.llms.local_llm import LocalLLM
    from agentdojo.functions_runtime import EmptyEnv

    captured: list[Any] = []

    class Completions:
        def create(self, **kwargs: Any) -> Any:
            captured.append(kwargs["messages"])
            raise RuntimeError("captured")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    LocalLLM(client, "m").query("", runtime, EmptyEnv(), messages)  # type: ignore[arg-type]
    return list(captured[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path, help="AgentDojo repository at tag v0.1.35")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    import contextlib
    import io

    from agentdojo.functions_runtime import FunctionsRuntime
    from agentdojo.task_suite.load_suites import get_suite
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(TEMPLATE[0], revision=TEMPLATE[1])
    rows = []
    for model in MODELS:
        for path in sorted((args.repo / "runs" / model).rglob("*.json")):
            trace = json.loads(path.read_text())
            suite = get_suite(trace["benchmark_version"], trace["suite_name"])
            runtime = FunctionsRuntime(suite.tools)
            messages = trace["messages"]
            with contextlib.redirect_stdout(io.StringIO()):
                request = request_for(messages[:-1], runtime)
            prompt = tok.apply_chat_template(request, tokenize=False, add_generation_prompt=True)
            n = len(tok(prompt, add_special_tokens=False)["input_ids"])
            rows.append(
                {
                    "model": model,
                    "file": str(path.relative_to(args.repo / "runs")),
                    "suite": trace["suite_name"],
                    "attack": trace.get("attack_type"),
                    "empty_final": is_empty_final(messages),
                    "security": trace.get("security"),
                    "utility": trace.get("utility"),
                    "final_request_tokens": n,
                }
            )
    summary: dict[str, Any] = {}
    for model in MODELS:
        mine = [r for r in rows if r["model"] == model]
        empty = [r["final_request_tokens"] for r in mine if r["empty_final"]]
        other = [r["final_request_tokens"] for r in mine if not r["empty_final"]]
        threshold_ok = bool(empty) and min(empty) > max(other)
        attack = collections.Counter()
        for r in mine:
            if r["attack"] not in (None, "none"):
                attack[(r["attack"], "n")] += 1
                attack[(r["attack"], "success")] += bool(r["security"])
                attack[(r["attack"], "empty")] += r["empty_final"]
        by_attack = {
            a: {
                "episodes": attack[(a, "n")],
                "published_successes": attack[(a, "success")],
                "empty_final_scored_as_no_success": attack[(a, "empty")],
                "published_asr": round(100 * attack[(a, "success")] / attack[(a, "n")], 2),
                "asr_excluding_empty": round(
                    100 * attack[(a, "success")] / (attack[(a, "n")] - attack[(a, "empty")]), 2
                ),
                "asr_upper_bound_if_empty_were_successes": round(
                    100 * (attack[(a, "success")] + attack[(a, "empty")]) / attack[(a, "n")], 2
                ),
            }
            for a in sorted({k[0] for k in attack})
        }
        summary[model] = {
            "traces": len(mine),
            "empty_final": len(empty),
            "empty_final_suites": dict(
                collections.Counter(r["suite"] for r in mine if r["empty_final"])
            ),
            "min_tokens_empty_final": min(empty) if empty else None,
            "max_tokens_other": max(other),
            "separated_by_a_token_threshold": threshold_ok,
            "other_traces_at_or_above_min_empty": sum(n >= min(empty) for n in other)
            if empty
            else None,
            "by_attack": by_attack,
        }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "agentdojo_local_traces.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )
    (args.out / "agentdojo_local_traces_summary.json").write_text(
        json.dumps(
            {"template": {"repo": TEMPLATE[0], "revision": TEMPLATE[1]}, "summary": summary},
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
