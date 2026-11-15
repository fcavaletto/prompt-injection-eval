"""Scripted stand-ins for a model, for offline tests and dry runs.

They produce no empirical result. A scripted agent follows a task's reference solution,
or the attacker's, and returns a prompt rendered in the Hermes-style layout that Qwen3 and
Granite 4.0 use, so the delivery check has something real to read. ``fault`` breaks that
rendering on purpose, to show the check notices.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import Any

from prompt_injection_eval.pilot import PilotError, adapter
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse

POLICIES = ("benign", "attacker", "obedient", "silent")
FAULTS = (None, "drop_tools", "truncate_results", "reencode_results", "drop_calls", "no_prompt")


def reference_render(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]], fault: str | None = None
) -> str:
    """A Hermes-style prompt: tool results in a user turn inside ``<tool_response>`` tags."""
    out = []
    for message in messages:
        role, content = message["role"], message.get("content") or ""
        if role == "system":
            block = content
            if tools and fault != "drop_tools":
                listed = "\n".join(json.dumps(tool, ensure_ascii=False) for tool in tools)
                block += f"\n\n# Tools\n\n<tools>\n{listed}\n</tools>"
            out.append(f"<|im_start|>system\n{block}<|im_end|>\n")
        elif role == "user":
            out.append(f"<|im_start|>user\n{content}<|im_end|>\n")
        elif role == "assistant":
            block = content
            for call in message.get("tool_calls") or []:
                if fault == "drop_calls":
                    continue
                function = call["function"]
                arguments = function["arguments"]
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                body = json.dumps(
                    {"name": function["name"], "arguments": arguments}, ensure_ascii=False
                )
                block += f"\n<tool_call>\n{body}\n</tool_call>"
            out.append(f"<|im_start|>assistant\n{block}<|im_end|>\n")
        elif role == "tool":
            if fault == "truncate_results":
                content = content[:40]
            elif fault == "reencode_results":
                content = json.dumps(content)
            out.append(
                f"<|im_start|>user\n<tool_response>\n{content}\n</tool_response><|im_end|>\n"
            )
    out.append("<|im_start|>assistant\n")
    return "".join(out)


class ScriptedProvider:
    """Follows reference solutions. ``policy`` decides whose."""

    name = "scripted"
    result_origin = "synthetic_scripted"
    concurrency = 1

    def __init__(
        self,
        policy: str = "benign",
        fault: str | None = None,
        renderer: Callable[[list[dict[str, Any]], list[dict[str, Any]]], str] | None = None,
    ) -> None:
        if policy not in POLICIES or fault not in FAULTS:
            raise PilotError(f"Unknown scripted policy or fault: {policy!r}, {fault!r}")
        self.policy = policy
        self.fault = fault
        # A real chat template can stand in for the reference layout (see template_renderer).
        self.renderer = renderer

    def _script(self, info: dict[str, Any], delivered: bool) -> tuple[list[Any], str]:
        s = adapter.suite(info["suite"])
        mode = info["mode"]
        if self.policy == "silent":
            return [], "I can't help with that."
        if mode in ("direct", "twin"):
            goal = (
                s.injection_tasks[info["injection_task"]]
                if mode == "direct"
                else adapter.twin(info["suite"], info["injection_task"])
            )
            if goal is None:
                raise PilotError(f"{info['injection_task']} has no benign twin.")
            return list(goal.ground_truth(adapter.environment(info["suite"]))), "Done."
        task = s.user_tasks[info["user_task"]]
        env = task.init_environment(adapter.environment(info["suite"]))
        rest = list(task.ground_truth(env))[info["prefix_calls"] :]
        follow = self.policy == "attacker" or (self.policy == "obedient" and delivered)
        if mode == "attack" and follow:
            goal = s.injection_tasks[info["injection_task"]]
            rest = [*goal.ground_truth(env), *rest]
        return rest, task.GROUND_TRUTH_OUTPUT

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        info = request.metadata["pilot"]
        messages = request.messages or []
        if self.renderer is not None:
            rendered = self.renderer(messages, request.tools or [])
        else:
            rendered = reference_render(messages, request.tools or [], self.fault)
        goal_text = ""
        if info["mode"] == "attack":
            goal_text = adapter.suite(info["suite"]).injection_tasks[info["injection_task"]].GOAL
        # What an obedient model can see is the prompt, not what the harness meant to send.
        delivered = bool(goal_text) and (
            goal_text in rendered or json.dumps(goal_text)[1:-1] in rendered
        )
        calls, final = self._script(info, delivered)
        step = sum(m["role"] == "assistant" for m in messages) - info["prefix_calls"]
        metadata: dict[str, Any] = {"finish_reason": "stop"}
        if self.fault != "no_prompt":
            metadata["rendered_prompt"] = rendered
        text = final
        if step < len(calls):
            call = calls[step]
            text = ""
            metadata["tool_calls"] = [
                {"name": call.function, "arguments": json.dumps(dict(call.args), default=str)}
            ]
        return GenerationResponse(
            text=text,
            raw_text=text,
            provider=self.name,
            model=request.model,
            latency_seconds=0.0,
            prompt_token_count=len(rendered) // 4,
            completion_token_count=max(1, len(text) // 4),
            provider_metadata=metadata,
        )

    def runtime_info(self, model: str) -> dict[str, Any]:
        return {"runtime": "scripted", "policy": self.policy, "fault": self.fault}


def template_renderer(
    repository: str, revision: str | None, think: bool | None
) -> Callable[[list[dict[str, Any]], list[dict[str, Any]]], str]:
    """Render with a model's own chat template. Downloads tokenizer files, never weights."""
    try:
        transformers: Any = importlib.import_module("transformers")
    except ImportError as exc:
        raise PilotError("The template check needs transformers: pip install transformers") from exc
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        repository, revision=revision, token=False
    )
    extra = {} if think is None else {"enable_thinking": think}

    def render(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
        return str(
            tokenizer.apply_chat_template(
                messages, tools=tools, add_generation_prompt=True, tokenize=False, **extra
            )
        )

    return render
