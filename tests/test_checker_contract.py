"""The measurement contract: corpus verdicts, the demonstrated counterexamples, ambiguity.

See docs/measurement-contract.md. Expected verdicts were fixed before the checkers were
changed; these tests pin both the repaired checkers and the limits of the archived ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_injection_eval import wp7
from prompt_injection_eval.pilot import checker_corpus as cc
from prompt_injection_eval.pilot import delivery, serialize

ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "results-published" / "wp7-audit-2026-11-16" / "renders"
CORPUS = list(cc.corpus())


def _contract(case: dict) -> list[str]:
    return delivery.check_contract(
        case["rendered"],
        case["messages"],
        case["tools"],
        case["records"],
        case["fmt"],
        case["payload"],
        case["payload_index"],
        profile=case["profile"],
    )


def _v1(case: dict) -> list[str]:
    return delivery.check(
        case["rendered"],
        case["messages"],
        case["tools"],
        case["records"],
        case["fmt"],
        case["payload"],
        case["payload_index"],
    )


def test_corpus_covers_every_class_on_every_base() -> None:
    assert {m.cls for m, _, _ in CORPUS} == {
        "valid",
        "role",
        "schema",
        "arguments",
        "duplicates",
        "order",
        "association",
        "truncation",
        "payload",
    }
    assert len({b["id"] for _, b, _ in CORPUS}) == 4
    for mutation, base, case in CORPUS:
        if mutation.expected == cc.REJECT:
            assert case["rendered"] != base["rendered"], (base["id"], mutation.id)


@pytest.mark.parametrize(
    ("mutation", "case"),
    [(m, c) for m, _, c in CORPUS],
    ids=[f"{b['id']}:{m.id}" for m, b, _ in CORPUS],
)
def test_contract_verdict_matches_the_expected_verdict(mutation, case) -> None:
    defects = _contract(case)
    assert (cc.REJECT if defects else cc.ACCEPT) == mutation.expected, defects


@pytest.mark.parametrize(
    "mutation_id", ["R1", "R2", "R3", "R5", "R6", "A4", "A5", "D1", "D2", "D3", "T2"]
)
def test_archived_check_misses_these_counterexamples(mutation_id) -> None:
    """The archived pilot check is kept unchanged; these are its demonstrated gaps."""
    found = [c for m, _, c in CORPUS if m.id == mutation_id]
    assert found and all(_v1(c) == [] for c in found)
    assert all(_contract(c) for c in found)


def test_tool_results_in_a_user_turn_are_not_rejected() -> None:
    for mutation, base, case in CORPUS:
        if mutation.id == "V1":
            assert "<tool_response>" in case["rendered"]
            assert _contract(case) == [], base["id"]


def test_strict_equal_distinguishes_json_types() -> None:
    assert delivery.strict_equal({"n": 1}, {"n": 1})
    assert not delivery.strict_equal({"n": 1}, {"n": True})
    assert not delivery.strict_equal({"n": 1}, {"n": 1.0})
    assert not delivery.strict_equal([1, "a"], [1.0, "a"])
    assert {"n": 1} == {"n": True}  # why plain equality was not enough


def test_carrier_only_formats_are_checked_per_message() -> None:
    base = next(c for m, b, c in CORPUS if m.id == "V1" and b["id"] == "qwen3-json")
    formats = {i: "json" for i, m in enumerate(base["messages"]) if m["role"] == "tool"}
    assert _contract(base) == []
    assert (
        delivery.check_contract(
            base["rendered"],
            base["messages"],
            base["tools"],
            base["records"],
            formats,
            base["payload"],
            base["payload_index"],
            profile="qwen3",
        )
        == []
    )
    formats[base["payload_index"]] = "text"
    assert delivery.check_contract(
        base["rendered"],
        base["messages"],
        base["tools"],
        base["records"],
        formats,
        base["payload"],
        base["payload_index"],
        profile="qwen3",
    )


def test_kept_real_prompts_pass_the_contract() -> None:
    stored = json.loads(
        (
            ROOT / "results-published/checker-validation-2026-11-17/kept_prompts_contract.json"
        ).read_text()
    )
    assert stored["tally"]["checked"] >= 787 and "defects" not in stored["tally"]


# WP7 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("render", cc.WP7_RENDERS)
def test_wp7_strict_keeps_every_stored_verdict(render) -> None:
    prompt = (RENDERS / f"{render}.txt").read_text()
    assert wp7.check(prompt).passed
    assert wp7.check(prompt, strict=True).passed


@pytest.mark.parametrize("render", cc.WP7_RENDERS)
@pytest.mark.parametrize(("mid", "_desc", "mutate"), cc.WP7_MUTATIONS)
def test_wp7_strict_rejects_name_type_and_argument_mutations(render, mid, _desc, mutate) -> None:
    prompt = mutate((RENDERS / f"{render}.txt").read_text())
    assert wp7.check(prompt).passed, "the archived WP7 check accepted this counterexample"
    assert not wp7.check(prompt, strict=True).passed, mid


# Free text is structurally ambiguous without the shape ----------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"a": "b: 1\nc: 2"}, {"a": {"b": 1, "c": 2}}),
        ({"a": "- x\n- y"}, {"a": ["x", "y"]}),
        ({"a": "(empty)"}, {"a": {}}),
        ({"a": "5"}, {"a": 5}),
        ({"a": "true"}, {"a": True}),
    ],
)
def test_text_rendering_collides_and_only_the_shape_separates(first, second) -> None:
    assert first != second
    assert serialize.to_text(first) == serialize.to_text(second)
    text = serialize.to_text(first)
    assert serialize.from_text(text, serialize.shape(first)) == first
    assert serialize.from_text(text, serialize.shape(second)) == second
    assert serialize.to_json(first) != serialize.to_json(second)
