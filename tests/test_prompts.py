"""Prompt template tests."""

from tests.conftest import case_by_id

from prompt_injection_eval.prompts import (
    BASELINE_TEMPLATE_VERSION,
    DEFENDED_TEMPLATE_VERSION,
    SPOTLIGHT_TEMPLATE_VERSION,
    conditions_for,
    datamark,
    render_prompt,
)
from prompt_injection_eval.schemas import EvalCase


def test_datamark_replaces_every_whitespace_run() -> None:
    assert datamark("a b\tc\n\nd  e") == "a^b^c^d^e"
    assert datamark("  padded  ") == "padded"
    assert "^" not in datamark("nospace")


def test_spotlight_condition_marks_document_only(full_cases: list[EvalCase]) -> None:
    case = case_by_id(full_cases, "direct_override_001")
    rendered = render_prompt(case, "spotlight")
    assert rendered.template_version == SPOTLIGHT_TEMPLATE_VERSION == "defended-v2"
    assert rendered.system_message == case.system_instruction
    assert case.user_task in rendered.user_message
    marked = datamark(case.document)
    assert marked in rendered.user_message
    assert case.document not in rendered.user_message
    # The attacker's instruction is still present, only transformed.
    assert "IGNORE^THE^USER^TASK" in rendered.user_message
    # The task line keeps ordinary spaces: marking is applied to the document alone.
    assert case.user_task.replace(" ", "^") not in rendered.user_message


def test_conditions_for_selections() -> None:
    assert conditions_for("both") == ["baseline", "defended"]
    assert conditions_for("all") == ["baseline", "defended", "spotlight"]
    assert conditions_for("spotlight") == ["spotlight"]


def test_conditions_share_system_task_and_document(full_cases: list[EvalCase]) -> None:
    case = case_by_id(full_cases, "delimiter_escape_002")
    baseline = render_prompt(case, "baseline")
    defended = render_prompt(case, "defended")
    assert baseline.system_message == case.system_instruction
    assert defended.system_message == case.system_instruction
    assert baseline.template_version == BASELINE_TEMPLATE_VERSION == "baseline-v1"
    assert defended.template_version == DEFENDED_TEMPLATE_VERSION == "defended-v1"
    assert case.user_task in baseline.user_message
    assert case.user_task in defended.user_message
    assert case.document in baseline.user_message
    assert case.document in defended.user_message
    assert "untrusted" not in baseline.user_message.casefold()
    assert "do not follow instructions" not in baseline.user_message.casefold()
    assert "untrusted data" in defended.user_message.casefold()
    assert "--- BEGIN DOCUMENT ---" in baseline.user_message
    assert "--- BEGIN UNTRUSTED DOCUMENT ---" in defended.user_message
    assert "CANARY_" not in baseline.user_message.replace(case.document, "")
    assert case.attack_goal is not None
    target = str(case.attack_goal.target)
    template_only = defended.user_message.replace(case.document, "")
    assert target not in template_only


def test_document_braces_are_not_interpreted(full_cases: list[EvalCase]) -> None:
    case = case_by_id(full_cases, "direct_override_003")
    rendered = render_prompt(case, "baseline")
    assert '{"takeover":true}' in case.document.replace(" ", "") or "takeover" in case.document
    assert case.document in rendered.user_message
