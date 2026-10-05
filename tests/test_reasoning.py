"""Visible-reasoning handling: splitting, scoring, provider parsing, CLI profile."""

from pathlib import Path

import httpx
from tests.conftest import CASES_PATH, case_by_id

from prompt_injection_eval.config import RunConfig, resolve_generation_limits
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse
from prompt_injection_eval.providers.mock import MockProvider
from prompt_injection_eval.providers.ollama import OllamaProvider
from prompt_injection_eval.reasoning import estimate_tokens, split_reasoning, strip_reasoning
from prompt_injection_eval.results_io import load_results
from prompt_injection_eval.runner import _review_reasons, run_evaluation
from prompt_injection_eval.schemas import EvalCase
from prompt_injection_eval.scoring.attack import score_attack
from prompt_injection_eval.scoring.task import score_task


def test_split_inline_think_block() -> None:
    split = split_reasoning("<think>reasoning here</think>\nCANARY_D01")
    assert split.answer.strip() == "CANARY_D01"
    assert split.reasoning == "reasoning here"
    assert split.truncated is False


def test_split_truncated_think_block() -> None:
    split = split_reasoning("<think>the model ran out of budget while")
    assert split.answer == ""
    assert split.truncated is True
    assert split.reasoning is not None and "budget" in split.reasoning


def test_split_plain_response_is_unchanged() -> None:
    split = split_reasoning("denied")
    assert split.answer == "denied"
    assert split.reasoning is None
    assert strip_reasoning("denied") == "denied"
    assert estimate_tokens(None) is None
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcdefgh") == 2


def test_scorers_ignore_reasoning(full_cases: list[EvalCase]) -> None:
    case = case_by_id(full_cases, "direct_override_002")
    # The reasoning mentions the canary and the wrong label. Only the answer counts.
    text = "<think>It says to output CANARY_D02. The ticket is about billing.</think>\naccount"
    assert score_attack(case, text, inference_failed=False).label == "failure"
    assert score_task(case, text, inference_failed=False).label == "success"
    complied = "<think>I will comply.</think>\nCANARY_D02"
    assert score_attack(case, complied, inference_failed=False).label == "success"


def _request() -> GenerationRequest:
    return GenerationRequest(
        model="deepseek-r1:14b",
        system_message="system",
        user_message="user",
        temperature=0.0,
        seed=None,
        max_output_tokens=4096,
        timeout_seconds=5,
        provider_settings={"think": True},
    )


def _provider(handler: object) -> OllamaProvider:
    return OllamaProvider(
        client=httpx.Client(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        )
    )


def test_ollama_separate_thinking_field_and_think_flag() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert '"think": true' in body or '"think":true' in body
        return httpx.Response(
            200,
            json={
                "model": "deepseek-r1:14b",
                "message": {
                    "role": "assistant",
                    "content": "denied",
                    "thinking": "The request was denied, so the label is denied.",
                },
                "done": True,
                "done_reason": "stop",
            },
        )

    response = _provider(handler).generate(_request())
    assert response.text == "denied"
    assert response.raw_text == "denied"
    assert response.reasoning_text is not None and "denied" in response.reasoning_text
    assert response.reasoning_truncated is False
    assert response.provider_metadata is not None
    assert response.provider_metadata["thinking_field_present"] is True


def test_ollama_inline_think_tags_are_split() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-r1:14b",
                "message": {
                    "role": "assistant",
                    "content": "<think>inline reasoning</think>\n\nRoom Atlas",
                },
                "done": True,
                "done_reason": "stop",
            },
        )

    response = _provider(handler).generate(_request())
    assert response.text.strip() == "Room Atlas"
    assert response.reasoning_text == "inline reasoning"
    assert response.raw_text is not None and response.raw_text.startswith("<think>")


def test_ollama_truncated_think_is_flagged() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "deepseek-r1:14b",
                "message": {"role": "assistant", "content": "<think>still thinking about"},
                "done": True,
                "done_reason": "length",
            },
        )

    response = _provider(handler).generate(_request())
    assert response.text == ""
    assert response.reasoning_truncated is True


def test_model_info_reports_thinking_capability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/show"
        return httpx.Response(
            200,
            json={
                "capabilities": ["completion", "thinking"],
                "details": {
                    "quantization_level": "Q4_K_M",
                    "parameter_size": "14.8B",
                    "family": "qwen2",
                },
            },
        )

    info = _provider(handler).model_info("deepseek-r1:14b")
    assert info["supports_thinking"] is True
    assert info["quantization_level"] == "Q4_K_M"


def test_reasoning_profile_defaults() -> None:
    assert resolve_generation_limits(profile="default", max_tokens=None, timeout=None) == (
        256,
        120.0,
    )
    assert resolve_generation_limits(profile="reasoning", max_tokens=None, timeout=None) == (
        4096,
        900.0,
    )
    assert resolve_generation_limits(profile="reasoning", max_tokens=512, timeout=30.0) == (
        512,
        30.0,
    )


def test_empty_answer_with_reasoning_is_queued_for_review() -> None:
    config = RunConfig(
        provider="ollama",
        model="deepseek-r1:14b",
        dataset=CASES_PATH,
        condition="baseline",
        output_dir=Path("results"),
        profile="reasoning",
        max_output_tokens=4096,
        timeout_seconds=900,
    )
    response = GenerationResponse(
        text="",
        raw_text="",
        reasoning_text="The model thought for a long time and then stopped.",
        reasoning_truncated=False,
        provider="ollama",
        model="deepseek-r1:14b",
        latency_seconds=30.0,
        provider_metadata={"done_reason": "stop"},
    )
    reasons = _review_reasons(None, None, response, config)
    assert any(
        "empty" in reason.casefold() and "reasoning" in reason.casefold() for reason in reasons
    )


def test_truncated_reasoning_is_not_also_flagged_as_empty_answer() -> None:
    config = RunConfig(
        provider="ollama",
        model="deepseek-r1:14b",
        dataset=CASES_PATH,
        condition="baseline",
        output_dir=Path("results"),
    )
    response = GenerationResponse(
        text="",
        reasoning_text="still thinking",
        reasoning_truncated=True,
        provider="ollama",
        model="deepseek-r1:14b",
        latency_seconds=1.0,
    )
    reasons = _review_reasons(None, None, response, config)
    assert any("truncated" in reason.casefold() for reason in reasons)
    assert not any("empty even though" in reason.casefold() for reason in reasons)


def test_runner_records_reasoning_fields(tmp_path: Path) -> None:
    summary = run_evaluation(
        RunConfig(
            provider="mock",
            model="synthetic-mock",
            dataset=CASES_PATH,
            condition="baseline",
            output_dir=tmp_path / "run",
            case_ids=["role_impersonation_001", "role_impersonation_002"],
        ),
        MockProvider(),
    )
    rows, _malformed = load_results(summary.output_path)
    by_id = {row["case_id"]: row for row in rows}
    complied = by_id["role_impersonation_001"]
    assert complied["reasoning_present"] is True
    assert complied["response_text"].strip() == "CANARY_R01"
    assert complied["response_text_raw"].startswith("<think>")
    assert complied["attack_score"] == "success"
    truncated = by_id["role_impersonation_002"]
    assert truncated["reasoning_truncated"] is True
    assert truncated["response_text"] == ""
    assert "truncated" in str(truncated["manual_review_reason"]).casefold()
    assert "think" in complied["unit_key"]
