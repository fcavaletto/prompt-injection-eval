"""One episode: build the state, replay the prefix, let the model continue, score.

The agent is resumed at a controlled injection point. Tool calls, replayed and live, run
through AgentDojo's ``ToolsExecutor``; the model's turns run inside AgentDojo's
``ToolsExecutionLoop``; both task checks are AgentDojo's.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from prompt_injection_eval.pilot import (
    AGENTDOJO_VERSION,
    BENCHMARK_VERSION,
    FORMATS,
    STUDY,
    PilotError,
    adapter,
    attacks,
    delivery,
    serialize,
)
from prompt_injection_eval.providers.base import GenerationRequest, Provider

MODES = ("attack", "clean", "scratch", "direct", "twin")
# A request is not started with less time than this left before the deadline.
MIN_REQUEST_SECONDS = 2.0
# The provider makes up to this many attempts per request; each gets a share of the time left.
PROVIDER_ATTEMPTS = 3
RESUMED = ("attack", "clean")


@dataclass(frozen=True)
class Spec:
    """One planned unit. ``user_task`` is set for attack, clean and scratch;
    ``injection_task`` for attack, direct and twin; ``attack`` for attack only."""

    suite: str
    mode: str
    fmt: str
    user_task: str | None
    injection_task: str | None
    attack: str | None
    run: int

    def key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    def condition(self) -> str:
        return f"{self.mode}/{self.attack or '-'}/{self.fmt}"

    def pair(self) -> str:
        return f"{self.user_task or '-'}|{self.injection_task or '-'}"


@dataclass(frozen=True)
class Settings:
    model: str
    label: str
    temperature: float = 0.0
    seed: int = 20261115
    max_output_tokens: int = 2048
    think: bool | None = None
    max_rounds: int = 15
    timeout_seconds: float = 300.0


class _Abort(Exception):
    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class _Setup:
    prompt: str
    scored_user_task: Any | None
    scored_goal: Any | None
    environment: Any
    prefix: list[Any]
    payload: str | None
    plan: adapter.InjectionPlan | None


def _setup(spec: Spec) -> _Setup:
    if spec.mode not in MODES or spec.fmt not in FORMATS:
        raise PilotError(f"Unknown mode or format in {spec}.")
    s = adapter.suite(spec.suite)
    if spec.mode in ("direct", "twin"):
        if spec.injection_task is None:
            raise PilotError(f"{spec.mode} needs an attacker goal.")
        goal = (
            s.injection_tasks[spec.injection_task]
            if spec.mode == "direct"
            else adapter.twin(spec.suite, spec.injection_task)
        )
        if goal is None:
            raise PilotError(f"{spec.suite}/{spec.injection_task} has no benign twin.")
        return _Setup(goal.GOAL, None, goal, adapter.environment(spec.suite), [], None, None)
    if spec.user_task is None:
        raise PilotError(f"{spec.mode} needs a user task.")
    task = s.user_tasks[spec.user_task]
    plan = adapter.injection_plan(spec.suite, spec.user_task)
    payload = goal = None
    injections: dict[str, str] = {}
    if spec.mode == "attack":
        if spec.injection_task is None or spec.attack is None:
            raise PilotError("attack needs an attacker goal and an attack.")
        goal = s.injection_tasks[spec.injection_task]
        payload = attacks.render(spec.attack, goal.GOAL)
        injections = dict.fromkeys(plan.vectors, payload)
    env = task.init_environment(adapter.environment(spec.suite, injections))
    prefix = []
    if spec.mode in RESUMED:
        calls = task.ground_truth(env)[: plan.index + 1]
        replayed = tuple(
            (c.function, json.dumps(c.args, sort_keys=True, default=str)) for c in calls
        )
        if replayed != plan.calls[: plan.index + 1]:
            raise PilotError(
                f"{spec.suite}/{spec.user_task}: the reference calls depend on the payload."
            )
        prefix = list(calls)
    return _Setup(task.PROMPT, task, goal, env, prefix, payload, plan)


def _static_inputs(spec: Spec, settings: Settings, setup: _Setup) -> dict[str, Any]:
    return {
        "study": STUDY,
        "agentdojo": AGENTDOJO_VERSION,
        "benchmark": BENCHMARK_VERSION,
        "suite_sha256": adapter.suite_sha256(spec.suite),
        "spec": asdict(spec),
        "system": adapter.system_message(),
        "prompt": setup.prompt,
        "tools": list(adapter.wire_tools(spec.suite)),
        "prefix": [[c.function, dict(c.args)] for c in setup.prefix],
        "payload": setup.payload,
        "initial_state_sha256": adapter.state_sha256(setup.environment),
        "settings": {
            k: v for k, v in asdict(settings).items() if k not in ("label", "timeout_seconds")
        },
    }


def fingerprint(spec: Spec, settings: Settings) -> str:
    """A hash of everything that determines the requests an episode will send."""
    body = json.dumps(_static_inputs(spec, settings, _setup(spec)), sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _reference_state(setup: _Setup, spec: Spec) -> str:
    """The state after the prefix when it is replayed with no executor and no serializer."""
    from agentdojo.functions_runtime import FunctionsRuntime

    fresh = _setup(spec)
    runtime = FunctionsRuntime(adapter.suite(spec.suite).tools)
    for call in fresh.prefix:
        runtime.run_function(fresh.environment, call.function, call.args, raise_on_error=True)
    return adapter.state_sha256(fresh.environment)


def to_wire(
    messages: list[Any], records: dict[int, serialize.Record], fmt: str
) -> list[dict[str, Any]]:
    """AgentDojo messages as chat-completion messages, tool results in ``fmt``."""
    from agentdojo.types import get_text_content_as_str

    wire: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        role = message["role"]
        if role == "tool":
            wire.append(
                {
                    "role": "tool",
                    "tool_call_id": message["tool_call_id"],
                    "name": message["tool_call"].function,
                    "content": serialize.serialize(records[index], fmt),
                }
            )
            continue
        entry: dict[str, Any] = {
            "role": role,
            "content": get_text_content_as_str(message["content"] or []),
        }
        if role == "assistant" and message["tool_calls"]:
            entry["tool_calls"] = [
                {
                    "type": "function",
                    "id": call.id,
                    "function": {"name": call.function, "arguments": dict(call.args)},
                }
                for call in message["tool_calls"]
            ]
        wire.append(entry)
    return wire


def run(
    spec: Spec,
    provider: Provider,
    settings: Settings,
    keep_prompts: bool = False,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Run one episode and return its trace. Provider and harness failures become statuses.

    ``deadline`` is a ``time.monotonic()`` value. No model request starts after it, and each
    request's timeout is bounded by the time left, so an episode overruns it by at most the
    provider's retry waits. An episode stopped this way is ``interrupted``.

    The episode stops at the first model turn whose returned prompt fails the delivery check:
    that turn's tool calls are not executed and no further response is requested. The request,
    the returned prompt, the response and the defects are kept in ``failed_turn``.
    """
    from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
    from agentdojo.agent_pipeline.tool_execution import (
        EMPTY_FUNCTION_NAME,
        ToolsExecutionLoop,
        ToolsExecutor,
    )
    from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
    from agentdojo.types import (
        ChatAssistantMessage,
        ChatSystemMessage,
        ChatUserMessage,
        text_content_block_from_string,
    )

    setup = _setup(spec)
    s = adapter.suite(spec.suite)
    tools = list(adapter.wire_tools(spec.suite))
    tool_names = [tool["function"]["name"] for tool in tools]
    runtime = FunctionsRuntime(s.tools)
    env = setup.environment
    pre = env.model_copy(deep=True)
    payload_index = 3 + 2 * setup.plan.index if setup.payload is not None and setup.plan else None
    records: dict[int, serialize.Record] = {}
    turns: list[dict[str, Any]] = []
    prompts: list[str | None] = []
    queue: list[serialize.Record] = []

    def formatter(result: Any) -> str:
        record = serialize.canonical(result)
        queue.append(record)
        return serialize.serialize(record, spec.fmt)

    executor = ToolsExecutor(formatter)

    class Tools(BasePipelineElement):
        def query(self, query, runtime, env, messages=(), extra_args=None):  # type: ignore[no-untyped-def]
            before = len(messages)
            queue.clear()
            query, runtime, env, messages, extra_args = executor.query(
                query, runtime, env, messages, extra_args or {}
            )
            pending = iter(queue)
            for index in range(before, len(messages)):
                message = messages[index]
                name = message["tool_call"].function
                ran = name != EMPTY_FUNCTION_NAME and name in runtime.functions
                record = next(pending) if ran else {}
                if message["error"] is not None:
                    record = serialize.error_record(message["error"])
                records[index] = record
            return query, runtime, env, messages, extra_args

    failed: dict[str, Any] = {}

    class Model(BasePipelineElement):
        def query(self, query, runtime, env, messages=(), extra_args=None):  # type: ignore[no-untyped-def]
            step = len(turns)
            wire = to_wire(list(messages), records, spec.fmt)
            timeout = settings.timeout_seconds
            if deadline is not None:
                left = deadline - time.monotonic()
                if left < MIN_REQUEST_SECONDS:
                    raise _Abort("interrupted", f"deadline reached before model request {step}")
                timeout = min(timeout, max(1.0, left / PROVIDER_ATTEMPTS))
            request = GenerationRequest(
                model=settings.model,
                system_message="",
                user_message="",
                temperature=settings.temperature,
                seed=settings.seed + spec.run,
                max_output_tokens=settings.max_output_tokens,
                timeout_seconds=timeout,
                provider_settings={} if settings.think is None else {"think": settings.think},
                messages=wire,
                tools=tools,
                tool_choice="auto",
                metadata={"pilot": {**asdict(spec), "prefix_calls": len(setup.prefix)}},
            )
            response = provider.generate(request)
            if response.error_type is not None:
                late = deadline is not None and time.monotonic() >= deadline - MIN_REQUEST_SECONDS
                raise _Abort(
                    "interrupted" if late else "infra_error",
                    f"model request {step}: {response.error_type}: {response.error_message}",
                )
            meta = dict(response.provider_metadata or {})
            rendered = meta.get("rendered_prompt")
            rendered = rendered if isinstance(rendered, str) else None
            defects = delivery.check(
                rendered, wire, tools, records, spec.fmt, setup.payload, payload_index
            )
            calls, summaries, bad_json, unknown = [], [], 0, 0
            for position, call in enumerate(meta.get("tool_calls") or []):
                name = call.get("name") or EMPTY_FUNCTION_NAME
                raw = call.get("arguments")
                try:
                    arguments = json.loads(raw) if isinstance(raw, str) else raw
                    if not isinstance(arguments, dict):
                        raise ValueError("arguments are not an object")
                except ValueError:
                    arguments = {"__unparsed_arguments__": str(raw)[:500]}
                    bad_json += 1
                unknown += name not in tool_names
                calls.append(
                    FunctionCall(function=name, args=arguments, id=f"call_{step}_{position}")
                )
                summaries.append({"name": name, "arguments": arguments})
            text = response.text or ""
            turns.append(
                {
                    "step": step,
                    "text": text,
                    "calls": summaries,
                    "unparsed_call_text": not calls and delivery.call_like_text(text, tool_names),
                    "invalid_argument_json": bad_json,
                    "unknown_tool": unknown,
                    "finish_reason": meta.get("finish_reason"),
                    "prompt_tokens": response.prompt_token_count,
                    "completion_tokens": response.completion_token_count,
                    "latency_seconds": response.latency_seconds,
                    "prompt_sha256": hashlib.sha256(rendered.encode()).hexdigest()
                    if rendered
                    else None,
                    "delivery_defects": defects,
                }
            )
            prompts.append(rendered)
            if defects:
                # Stop here: do not execute these calls or ask for another response.
                failed.update(
                    {
                        "step": step,
                        "request": {
                            "messages": wire,
                            "tool_names": tool_names,
                            "tools_sha256": hashlib.sha256(
                                json.dumps(tools, sort_keys=True).encode()
                            ).hexdigest(),
                            "tool_choice": "auto",
                            "timeout_seconds": timeout,
                        },
                        "rendered_prompt": rendered,
                        "response_text": text,
                        "response_raw_calls": meta.get("tool_calls"),
                        "finish_reason": meta.get("finish_reason"),
                        "defects": defects,
                    }
                )
                unverified = defects == [delivery.PROMPT_NOT_RETURNED]
                raise _Abort(
                    "unverified_delivery" if unverified else "invalid_delivery",
                    f"model request {step}: " + "; ".join(defects),
                )
            message = ChatAssistantMessage(
                role="assistant",
                content=[text_content_block_from_string(text)],
                tool_calls=calls or None,
            )
            return query, runtime, env, [*messages, message], extra_args or {}

    trace: dict[str, Any] = {
        "study": STUDY,
        "unit_key": spec.key(),
        **asdict(spec),
        "condition": spec.condition(),
        "pair": spec.pair(),
        "label": settings.label,
        "model": settings.model,
        "request_sha256": hashlib.sha256(
            json.dumps(_static_inputs(spec, settings, setup), sort_keys=True, default=str).encode()
        ).hexdigest(),
        "resumed_at_injection_point": spec.mode in RESUMED,
        "payload": setup.payload,
        "injection_index": setup.plan.index if setup.plan and spec.mode in RESUMED else None,
        "prefix_calls": [[c.function, dict(c.args)] for c in setup.prefix],
        "pre_state_sha256": adapter.state_sha256(pre),
        "status": "completed",
        "status_detail": None,
        "utility": None,
        "security": None,
        "success": None,
    }
    messages: list[Any] = [
        ChatSystemMessage(
            role="system", content=[text_content_block_from_string(adapter.system_message())]
        ),
        ChatUserMessage(role="user", content=[text_content_block_from_string(setup.prompt)]),
    ]
    tools_element, model_element = Tools(), Model()
    try:
        for position, call in enumerate(setup.prefix):
            replayed = FunctionCall(
                function=call.function, args=dict(call.args), id=f"prefix_{position}"
            )
            messages.append(
                ChatAssistantMessage(
                    role="assistant",
                    content=[text_content_block_from_string("")],
                    tool_calls=[replayed],
                )
            )
            _, _, env, messages, _ = tools_element.query(setup.prompt, runtime, env, messages, {})
            messages = list(messages)
            if messages[-1]["error"] is not None:
                raise _Abort("prefix_error", str(messages[-1]["error"]))
        trace["branch_state_sha256"] = adapter.state_sha256(env)
        if setup.prefix:
            trace["reference_state_sha256"] = _reference_state(setup, spec)
            if trace["reference_state_sha256"] != trace["branch_state_sha256"]:
                raise _Abort("prefix_error", "state after replay differs from the reference replay")
        if setup.payload is not None:
            carrier = records.get(payload_index if payload_index is not None else -1, {})
            if not any(setup.payload.strip() in text for text in delivery._record_strings(carrier)):
                raise _Abort("invalid_delivery", "payload_not_in_record")
        _, _, env, messages, _ = model_element.query(setup.prompt, runtime, env, messages, {})
        loop = ToolsExecutionLoop([tools_element, model_element], max_iters=settings.max_rounds)
        _, _, env, messages, _ = loop.query(setup.prompt, runtime, env, messages, {})
        messages = list(messages)
    except _Abort as abort:
        trace["status"], trace["status_detail"] = abort.status, abort.detail
    except PilotError as error:
        trace["status"], trace["status_detail"] = "harness_error", str(error)

    defects = sorted({d for turn in turns for d in turn["delivery_defects"]})
    if trace["status"] == "completed" and defects:  # unreachable: a defect stops the episode
        trace["status"], trace["status_detail"] = "invalid_delivery", "; ".join(defects)
    trace["failed_turn"] = failed or None
    if trace["status"] == "completed" and turns:
        # Only a verified, finished episode is scored. Anything else is not a measurement.
        if setup.scored_user_task is not None:
            trace["utility"] = adapter.score(spec.suite, setup.scored_user_task, messages, pre, env)
        if setup.scored_goal is not None:
            hit = adapter.score(spec.suite, setup.scored_goal, messages, pre, env)
            trace["security" if spec.mode == "attack" else "success"] = hit
    schema_rejections = sum(
        1
        for record in records.values()
        if str(record.get("error", "")).startswith("ValidationError")
    )
    trace.update(
        {
            "post_state_sha256": adapter.state_sha256(env),
            "delivery_defects": defects,
            "turns": turns,
            "totals": {
                "model_calls": len(turns),
                "prompt_tokens": sum(t["prompt_tokens"] or 0 for t in turns),
                "completion_tokens": sum(t["completion_tokens"] or 0 for t in turns),
                "latency_seconds": sum(t["latency_seconds"] or 0.0 for t in turns),
                "parsed_calls": sum(len(t["calls"]) for t in turns),
                "turns_with_unparsed_call_text": sum(bool(t["unparsed_call_text"]) for t in turns),
                "invalid_argument_json": sum(t["invalid_argument_json"] for t in turns),
                "unknown_tool": sum(t["unknown_tool"] for t in turns),
                "schema_rejections": schema_rejections,
                "truncated_turns": sum(t["finish_reason"] == "length" for t in turns),
                "hit_round_limit": bool(messages and messages[-1]["role"] != "assistant")
                or bool(messages[-1].get("tool_calls")),
            },
            "messages": to_wire(messages, records, spec.fmt),
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    )
    if keep_prompts:
        trace["rendered_prompts"] = prompts
    return trace
