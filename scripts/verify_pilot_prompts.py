#!/usr/bin/env python
"""Check every stored prompt hash in a pilot phase against a local rendering. No inference.

For each model turn, the request's messages are rebuilt from the trace's stored conversation
(everything before that turn's assistant message), rendered with the model's chat template
at the pinned revision, and hashed. The hash is compared with ``prompt_sha256``, the hash
of the prompt the server returned. Where the full returned prompt was kept, the text is
compared too.

Needs ``transformers`` and downloads tokenizer files only.

    python scripts/verify_pilot_prompts.py PHASE_DIR --repository Qwen/Qwen3-32B \\
        --revision 9216db5781bf21249d130ec9da846c4624c16137 --output result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _miss(trace: dict, step: int, why: str) -> dict:
    return {"unit": trace["condition"], "pair": trace["pair"], "step": step, "why": why}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("phase_dir", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    import transformers

    from prompt_injection_eval.pilot import adapter

    manifest = json.loads((args.phase_dir / "manifest.json").read_text())
    think = manifest["settings"]["think"]
    extra = {} if think is None else {"enable_thinking": bool(think)}
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        args.repository, revision=args.revision, token=False
    )
    lines = (args.phase_dir / "traces.jsonl").read_text().splitlines()
    traces = [json.loads(line) for line in lines]
    checked = matched = text_checked = text_matched = 0
    mismatches = []
    for trace in traces:
        tools = list(adapter.wire_tools(trace["suite"]))
        messages = trace["messages"]
        assistant_positions = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
        model_positions = assistant_positions[len(trace["prefix_calls"]) :]
        kept = trace.get("rendered_prompts") or []
        for step, turn in enumerate(trace["turns"]):
            if step >= len(model_positions):
                mismatches.append(_miss(trace, step, "turn has no stored assistant message"))
                continue
            request = messages[: model_positions[step]]
            rendered = tokenizer.apply_chat_template(
                request, tools=tools, add_generation_prompt=True, tokenize=False, **extra
            )
            digest = hashlib.sha256(rendered.encode()).hexdigest()
            checked += 1
            if digest == turn["prompt_sha256"]:
                matched += 1
            else:
                mismatches.append(_miss(trace, step, "hash differs"))
            if step < len(kept) and kept[step] is not None:
                text_checked += 1
                text_matched += kept[step] == rendered
    result = {
        "phase_dir": str(args.phase_dir),
        "tokenizer": f"{args.repository}@{args.revision}",
        "transformers": transformers.__version__,
        "template_kwargs": extra,
        "episodes": len(traces),
        "turns_checked": checked,
        "hashes_matching_local_rendering": matched,
        "full_prompts_kept_and_compared": text_checked,
        "full_prompts_identical": text_matched,
        "mismatches": mismatches,
    }
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)
    sys.exit(0 if matched == checked and not mismatches else 1)


if __name__ == "__main__":
    main()
