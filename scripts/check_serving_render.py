#!/usr/bin/env python
"""One development request: does the server's prompt equal the pinned local rendering?

Sends the conversation of a resumed banking episode (user_task_0, JSON format, at its
injection point) to the server named by PIE_OPENAI_BASE_URL, with the suite's tools, and
compares the prompt the server returns with the model's chat template rendered locally at
the pinned revision. Writes the request body, the returned prompt and the comparison.

    PIE_OPENAI_BASE_URL=... python scripts/check_serving_render.py --model M --revision R \\
        [--no-think] --output serving_rendering_check.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--think", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import httpx
    import transformers

    from prompt_injection_eval.pilot import episode
    from prompt_injection_eval.pilot.scripted import ScriptedProvider

    class Capture(ScriptedProvider):
        def generate(self, request: Any) -> Any:
            self.wire = copy.deepcopy(request.messages)
            self.tools = request.tools
            return super().generate(request)

    capture = Capture("benign")
    spec = episode.Spec("banking", "clean", "json", "user_task_0", None, None, 0)
    episode.run(spec, capture, episode.Settings(model="capture", label="capture"))
    wire = []
    for message in capture.wire:
        message = dict(message)
        if message.get("tool_calls"):
            message["tool_calls"] = [
                {
                    **c,
                    "function": {
                        **c["function"],
                        "arguments": json.dumps(c["function"]["arguments"]),
                    },
                }
                for c in message["tool_calls"]
            ]
        wire.append(message)
    body: dict[str, Any] = {
        "model": args.model,
        "messages": wire,
        "tools": capture.tools,
        "tool_choice": "auto",
        "temperature": 0.0,
        "max_tokens": 64,
        "return_prompt_text": True,
    }
    extra = {} if args.think is None else {"enable_thinking": args.think}
    if extra:
        body["chat_template_kwargs"] = extra
    client = httpx.Client(base_url=os.environ["PIE_OPENAI_BASE_URL"], timeout=120)
    version = client.get("/version").json()
    models = client.get("/v1/models").json()
    response = client.post("/v1/chat/completions", json=body)
    response.raise_for_status()
    data = response.json()
    served = data.get("prompt_text")
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        args.model, revision=args.revision, token=False
    )
    local = tokenizer.apply_chat_template(
        capture.wire, tools=capture.tools, add_generation_prompt=True, tokenize=False, **extra
    )
    result: dict[str, Any] = {
        "what": "One development request (banking user_task_0, resumed, JSON format) "
        "sent before the phase. Not an episode.",
        "server_version": version,
        "served_models": [
            {k: m.get(k) for k in ("id", "root", "max_model_len")} for m in models.get("data", [])
        ],
        "local_rendering": f"transformers {transformers.__version__}, "
        f"{args.model}@{args.revision}, template kwargs {extra}",
        "prompt_returned": isinstance(served, str),
        "identical_to_local_rendering": served == local,
        "tool_result_json_object_verbatim": isinstance(served, str)
        and wire[-1]["content"] in served,
        "response_finish_reason": data["choices"][0]["finish_reason"],
        "response_has_tool_calls": bool(data["choices"][0]["message"].get("tool_calls")),
        "usage": data.get("usage"),
    }
    if isinstance(served, str) and served != local:
        at = next(
            (i for i in range(min(len(local), len(served))) if local[i] != served[i]),
            min(len(local), len(served)),
        )
        result["first_difference"] = {
            "at": at,
            "local": local[max(0, at - 80) : at + 120],
            "server": served[max(0, at - 80) : at + 120],
        }
    print(json.dumps(result, indent=1))
    args.output.write_text(
        json.dumps({**result, "request_body": body, "server_prompt": served}, indent=1) + "\n"
    )
    sys.exit(0 if result["identical_to_local_rendering"] else 1)


if __name__ == "__main__":
    main()
