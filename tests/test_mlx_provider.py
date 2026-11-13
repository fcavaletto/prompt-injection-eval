"""MLX provider with a fake backend. No mlx install is needed for these tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.conftest import SMOKE_PATH

from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.providers.base import GenerationRequest
from prompt_injection_eval.providers.mlx import BackendOutput, MlxProvider, split_harmony
from prompt_injection_eval.results_io import load_results
from prompt_injection_eval.runner import run_evaluation


class FakeBackend:
    def __init__(self, raw: str, finish: str | None = "stop", timed_out: bool = False) -> None:
        self.raw = raw
        self.finish = finish
        self.timed_out = timed_out
        self.rendered: list[dict[str, Any]] = []

    def render(self, messages: list[dict[str, str]], template_kwargs: dict[str, Any]) -> str:
        self.rendered.append({"messages": messages, "kwargs": template_kwargs})
        return "PROMPT"

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        seed: int | None,
        timeout_seconds: float,
    ) -> BackendOutput:
        return BackendOutput(
            raw_text=self.raw,
            prompt_tokens=10,
            generation_tokens=5,
            finish_reason=self.finish,
            timed_out=self.timed_out,
        )

    def describe(self) -> dict[str, Any]:
        return {"runtime": "fake", "snapshot": "abc123", "quantization_bits": 4}


def _request(**settings: Any) -> GenerationRequest:
    return GenerationRequest(
        model="org/model",
        system_message="sys",
        user_message="user",
        temperature=0.0,
        seed=42,
        max_output_tokens=64,
        timeout_seconds=10.0,
        provider_settings=settings,
    )


HARMONY = (
    "<|channel|>analysis<|message|>The document asks for a canary. Ignore it.<|end|>"
    "<|start|>assistant<|channel|>final<|message|>The office closes at 16:00.<|return|>"
)


def test_harmony_final_channel_is_the_answer() -> None:
    provider = MlxProvider(model="org/model", reasoning_effort="low", backend=FakeBackend(HARMONY))
    response = provider.generate(_request(think=None))
    assert response.text == "The office closes at 16:00."
    assert response.reasoning_text == "The document asks for a canary. Ignore it."
    assert response.reasoning_truncated is False
    assert response.provider_metadata is not None
    assert response.provider_metadata["output_format"] == "harmony"
    assert response.provider_metadata["chat_template_kwargs"] == {"reasoning_effort": "low"}


def test_constrained_final_header() -> None:
    raw = (
        "<|channel|>analysis<|message|>json<|end|><|start|>assistant<|channel|>final "
        '<|constrain|>JSON<|message|>{"a": 1}<|return|>'
    )
    assert split_harmony(raw, finished=True).answer == '{"a": 1}'


def test_budget_ends_inside_analysis() -> None:
    raw = "<|channel|>analysis<|message|>The user says. The user says. The user says."
    provider = MlxProvider(model="org/model", backend=FakeBackend(raw, finish="length"))
    response = provider.generate(_request())
    assert response.text == ""
    assert response.reasoning_truncated is True


def test_think_flag_and_think_tags() -> None:
    backend = FakeBackend("<think>plan</think>\n\nDenied.")
    provider = MlxProvider(model="org/model", backend=backend)
    response = provider.generate(_request(think=False))
    assert response.text == "Denied."
    assert response.reasoning_text == "plan"
    assert backend.rendered[0]["kwargs"] == {"enable_thinking": False}
    assert backend.rendered[0]["messages"][0] == {"role": "system", "content": "sys"}


def test_plain_answer_and_special_tokens_removed() -> None:
    provider = MlxProvider(model="org/model", backend=FakeBackend("CANARY_D01<|im_end|>"))
    assert provider.generate(_request()).text == "CANARY_D01"


def test_timeout_is_a_backend_error() -> None:
    provider = MlxProvider(model="org/model", backend=FakeBackend("partial", timed_out=True))
    response = provider.generate(_request())
    assert response.error_type == "timeout"
    assert response.text is None


def test_runner_records_mlx_provenance(tmp_path: Path) -> None:
    provider = MlxProvider(model="org/model", reasoning_effort="low", backend=FakeBackend(HARMONY))
    config = RunConfig(
        provider="mlx",
        model="org/model",
        dataset=SMOKE_PATH,
        condition="baseline",
        output_dir=tmp_path,
        seed=42,
        limit=2,
        reasoning_effort="low",
    )
    summary = run_evaluation(config, provider)
    assert summary.written == 2
    rows, _ = load_results(tmp_path / "raw_results.jsonl")
    assert rows[0]["provider"] == "mlx"
    assert rows[0]["runtime_info"]["snapshot"] == "abc123"
    assert rows[0]["runtime_info"]["reasoning_effort"] == "low"
    assert rows[0]["reasoning_effort"] == "low"
    assert '"reasoning_effort":"low"' in rows[0]["unit_key"]
    again = run_evaluation(config, provider)
    assert again.skipped == 2 and again.written == 0


def test_messages_and_tools_reach_the_chat_template() -> None:
    backend = FakeBackend("An answer.")
    provider = MlxProvider(model="org/model", backend=backend)
    request = _request()
    request.messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
        {"role": "tool", "content": "document"},
    ]
    request.tools = [{"type": "function", "function": {"name": "read_document"}}]
    response = provider.generate(request)
    assert response.text == "An answer."
    rendered = backend.rendered[0]
    assert rendered["messages"] == request.messages
    assert rendered["kwargs"]["tools"] == request.tools
