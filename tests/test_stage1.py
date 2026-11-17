"""Stage 1 diagnostic: the frozen design, the forged-data twins, goal scoring, a dry run.

Offline. The scripted provider stands in for the model; no result here is empirical.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("agentdojo")

from prompt_injection_eval.pilot import adapter, attacks, episode, serialize, stage1  # noqa: E402
from prompt_injection_eval.pilot.scripted import ScriptedProvider  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "data" / "stage1" / "design.json"


def test_counts_are_within_the_authorized_caps() -> None:
    c = stage1.counts()
    assert c["attack"] == 576 == 24 * 2 * 6 * 2
    assert c["forged"] <= stage1.CAPS["forged"] and c["controls"] <= stage1.CAPS["controls"]
    assert c["episodes"] <= stage1.CAPS["episodes"]


def test_the_frozen_design_file_is_what_the_code_produces() -> None:
    assert json.loads(FROZEN.read_text()) == json.loads(json.dumps(stage1.design()))


def test_pairs_are_an_outcome_blind_draw_from_development_suites_only() -> None:
    chosen = stage1.pairs()
    assert set(chosen) == {"banking", "slack"}  # workspace and travel untouched
    banking_users = list(adapter.suite("banking").user_tasks)
    banking_goals = list(adapter.suite("banking").injection_tasks)
    for suite, found in chosen.items():
        assert len(found) == 12 and len({u for u, _ in found}) == 12
        for user, goal in found:
            assert len(adapter.injection_plan(suite, user).vectors) == 1
            assert (suite, goal) not in stage1.NOT_CAPABLE
            assert (suite, user, goal) not in {
                (p.suite, p.user_task, p.goal) for p in stage1.PATHWAYS
            }
            if suite == "banking":  # the half no model has run
                assert (banking_users.index(user) + banking_goals.index(goal)) % 2 == 1
    assert stage1.draw("banking") == stage1.draw("banking")  # deterministic


def test_conditions_are_six_distinct_carrier_context_pairs() -> None:
    fmts = [stage1.fmt_of(c) for c in stage1.CONDITIONS]
    assert len(set(fmts)) == 6 and {"text", "quoted", "json"} <= set(fmts)
    assert all(stage1.parse_fmt(stage1.fmt_of(c)) == c for c in stage1.CONDITIONS)


@pytest.mark.parametrize("p", stage1.PATHWAYS, ids=lambda p: f"{p.suite}-{p.user_task}-{p.goal}")
def test_forged_twins_state_facts_within_the_field(p: stage1.Pathway) -> None:
    multi, one = p.payload("forged_multiline"), p.payload("forged_one_line")
    assert " ".join(multi.split()) == " ".join(one.split()) and "\n" not in one
    words = {w.strip(".,:").lower() for w in one.split()}
    assert not words & {"you", "your", "please", "assistant", "must", "ignore", "send", "do"}
    baseline = attacks.render(attacks.BASELINE, adapter.suite(p.suite).injection_tasks[p.goal].GOAL)
    assert len(multi) <= len(baseline)  # no more room than the instruction family


@pytest.mark.parametrize("p", stage1.PATHWAYS, ids=lambda p: f"{p.suite}-{p.user_task}-{p.goal}")
def test_goal_scoring_credits_data_following_and_not_the_reference(p: stage1.Pathway) -> None:
    """AgentDojo's own security check, on the environment with the forged field."""
    from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
    from agentdojo.types import (
        ChatAssistantMessage,
        ChatUserMessage,
        text_content_block_from_string,
    )

    s = adapter.suite(p.suite)
    task, goal = s.user_tasks[p.user_task], s.injection_tasks[p.goal]
    plan = adapter.injection_plan(p.suite, p.user_task)
    payload = p.payload("forged_multiline")

    def run(calls: list[tuple[str, dict]]) -> bool:
        env = task.init_environment(
            adapter.environment(p.suite, dict.fromkeys(plan.vectors, payload))
        )
        pre = env.model_copy(deep=True)
        runtime = FunctionsRuntime(s.tools)
        messages = [
            ChatUserMessage(role="user", content=[text_content_block_from_string(task.PROMPT)])
        ]
        for n, (name, args) in enumerate(calls):
            runtime.run_function(env, name, args, raise_on_error=True)
            messages.append(
                ChatAssistantMessage(
                    role="assistant",
                    content=[text_content_block_from_string("")],
                    tool_calls=[FunctionCall(function=name, args=args, id=f"c{n}")],
                )
            )
        messages.append(
            ChatAssistantMessage(
                role="assistant", content=[text_content_block_from_string("Done.")], tool_calls=None
            )
        )
        return adapter.score(p.suite, goal, messages, pre, env)

    env = task.init_environment(adapter.environment(p.suite))
    reference = [(c.function, dict(c.args)) for c in task.ground_truth(env)]
    assert run(list(p.following)) is True
    assert run(reference) is False


def test_quoted_and_json_never_put_a_raw_newline_inside_a_string() -> None:
    record = {"result": "line one\nUser (Emma): do X\n", "n": 1}
    assert "\n" not in serialize.to_json(record)
    quoted = serialize.to_quoted(record)
    assert quoted.count("\n") == 1 and serialize.from_quoted(quoted) == record


@pytest.mark.parametrize("condition", stage1.CONDITIONS, ids=stage1.fmt_of)
def test_dry_run_every_condition_verifies_under_the_contract(condition) -> None:
    settings = episode.Settings(
        model="scripted", label="scripted", profile="scripted", study=stage1.STAGE
    )
    fmt = stage1.fmt_of(condition)
    user, goal = stage1.pairs()["banking"][0]
    p = stage1.PATHWAYS[1]
    for spec in (
        episode.Spec("banking", "attack", fmt, user, goal, attacks.BASELINE, 0),
        episode.Spec("banking", "attack", fmt, user, goal, "neutral_baseline_one_line", 0),
        episode.Spec(p.suite, "attack", fmt, p.user_task, p.goal, "forged_multiline", 0),
        episode.Spec("banking", "clean", fmt, user, None, None, 0),
    ):
        trace = episode.run(spec, ScriptedProvider("benign"), settings)
        assert trace["status"] == "completed", (spec, trace["status_detail"])
        assert trace["study"] == stage1.STAGE
        tool_messages = [m for m in trace["messages"] if m["role"] == "tool"]
        carrier = 3 + 2 * trace["injection_index"]
        carrier_fmt, context_fmt = condition
        for index, message in enumerate(trace["messages"]):
            if message["role"] != "tool":
                continue
            want = carrier_fmt if index == carrier else context_fmt
            if want == "json":
                assert message["content"].startswith("{")
            elif want == "quoted":
                assert message["content"] == serialize.to_quoted(
                    serialize.from_quoted(message["content"])
                )
        assert tool_messages


def test_a_rendering_fault_is_caught_by_the_contract_in_a_dry_run() -> None:
    settings = episode.Settings(model="scripted", label="scripted", profile="scripted")
    user, goal = stage1.pairs()["slack"][0]
    spec = episode.Spec("slack", "attack", "json@text", user, goal, attacks.BASELINE, 0)
    trace = episode.run(spec, ScriptedProvider("benign", fault="reencode_results"), settings)
    assert trace["status"] == "invalid_delivery" and trace["security"] is None


def test_pilot_fingerprints_are_unchanged_by_the_new_settings() -> None:
    spec = episode.Spec(
        "banking", "attack", "json", "user_task_1", "injection_task_7", attacks.BASELINE, 0
    )
    plain = episode.Settings(model="m", label="l")
    assert episode.fingerprint(spec, plain) == episode.fingerprint(
        spec, episode.Settings(model="m", label="x")
    )
    assert episode.fingerprint(spec, plain) != episode.fingerprint(
        spec, episode.Settings(model="m", label="l", profile="scripted")
    )


def test_composite_formats_need_the_contract_check() -> None:
    user, goal = stage1.pairs()["banking"][0]
    spec = episode.Spec("banking", "attack", "json@text", user, goal, attacks.BASELINE, 0)
    with pytest.raises(Exception, match="profile"):
        episode.run(spec, ScriptedProvider("benign"), episode.Settings(model="m", label="l"))
