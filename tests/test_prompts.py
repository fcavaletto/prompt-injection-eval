"""Prompt template tests."""

from tests.conftest import case_by_id

from prompt_injection_eval.prompts import (
    BASELINE_TEMPLATE_VERSION,
    DEFENDED_TEMPLATE_VERSION,
    render_prompt,
)
from prompt_injection_eval.schemas import EvalCase


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
