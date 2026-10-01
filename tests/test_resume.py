"""Resume, overwrite, and interrupted JSONL behavior."""

import json
from pathlib import Path

from tests.conftest import SMOKE_PATH

from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.constants import SCORER_BUNDLE_VERSION
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse
from prompt_injection_eval.providers.mock import MockProvider
from prompt_injection_eval.results_io import load_results, unit_key
from prompt_injection_eval.runner import run_evaluation


def _config(tmp_path: Path, **overrides: object) -> RunConfig:
    payload: dict[str, object] = {
        "provider": "mock",
        "model": "synthetic-mock",
        "dataset": SMOKE_PATH,
        "condition": "both",
        "output_dir": tmp_path / "run",
        "limit": 1,
        "resume": True,
        "overwrite": False,
    }
    payload.update(overrides)
    return RunConfig.model_validate(payload)


def test_resume_skips_completed_units(tmp_path: Path) -> None:
    first = run_evaluation(_config(tmp_path), MockProvider())
    assert first.written == 2
    assert first.skipped == 0
    second = run_evaluation(_config(tmp_path, limit=2), MockProvider())
    assert second.skipped == 2
    assert second.written == 2
    rows, malformed = load_results(first.output_path)
    assert malformed == []
    assert len(rows) == 4


def test_changed_model_is_not_reused(tmp_path: Path) -> None:
    run_evaluation(_config(tmp_path), MockProvider())
    again = run_evaluation(_config(tmp_path, model="other-mock"), MockProvider())
    assert again.skipped == 0
    assert again.written == 2


def test_changed_template_version_and_dataset_hash_are_not_reused(tmp_path: Path) -> None:
    summary = run_evaluation(_config(tmp_path, condition="baseline"), MockProvider())
    rows, _malformed = load_results(summary.output_path)
    original = rows[0]
    stale_template = dict(original)
    stale_template["prompt_template_version"] = "baseline-v0"
    stale_template["unit_key"] = unit_key(
        case_id=original["case_id"],
        condition="baseline",
        provider="mock",
        model="synthetic-mock",
        temperature=0.0,
        seed=None,
        max_output_tokens=256,
        prompt_template_version="baseline-v0",
        dataset_sha256=original["dataset_sha256"],
        scorer_version=SCORER_BUNDLE_VERSION,
    )
    stale_hash = dict(original)
    stale_hash["dataset_sha256"] = "a" * 64
    stale_hash["case_id"] = "not-a-real-case"
    stale_hash["unit_key"] = unit_key(
        case_id="not-a-real-case",
        condition="baseline",
        provider="mock",
        model="synthetic-mock",
        temperature=0.0,
        seed=None,
        max_output_tokens=256,
        prompt_template_version=original["prompt_template_version"],
        dataset_sha256="a" * 64,
    )
    with summary.output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stale_template) + "\n")
        handle.write(json.dumps(stale_hash) + "\n")
    again = run_evaluation(_config(tmp_path, condition="baseline"), MockProvider())
    assert again.skipped == 1
    assert again.written == 0
    reloaded, _malformed = load_results(summary.output_path)
    assert len(reloaded) == 3


def test_malformed_final_line_is_preserved(tmp_path: Path) -> None:
    summary = run_evaluation(_config(tmp_path, condition="baseline", limit=2), MockProvider())
    with summary.output_path.open("a", encoding="utf-8") as handle:
        handle.write('{"case_id": "truncated"')
    before = summary.output_path.read_text(encoding="utf-8")
    assert before.count("\n") >= 2
    again = run_evaluation(_config(tmp_path, condition="both", limit=2), MockProvider())
    text = summary.output_path.read_text(encoding="utf-8")
    assert '{"case_id": "truncated"' in text
    rows, malformed = load_results(summary.output_path)
    assert malformed
    assert again.malformed_lines
    assert len(rows) > 2
    assert all("truncated" not in row["case_id"] for row in rows)


def test_overwrite_replaces_only_the_results_file(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    notes = output / "notes.txt"
    notes.write_text("keep me", encoding="utf-8")
    run_evaluation(_config(tmp_path), MockProvider())
    run_evaluation(_config(tmp_path, overwrite=True, resume=False), MockProvider())
    assert notes.read_text(encoding="utf-8") == "keep me"
    rows, malformed = load_results(output / "raw_results.jsonl")
    assert malformed == []
    assert len(rows) == 2


class _Boom:
    name = "mock"
    result_origin = "synthetic_mock"

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if request.metadata.get("case_id") == "benign_control_001":
            raise RuntimeError("boom /Users/example/secret")
        return GenerationResponse(
            text="denied",
            provider=self.name,
            model=request.model,
            latency_seconds=0.0,
            provider_metadata={"synthetic_mock": True},
        )


def test_provider_exception_does_not_abort_the_run(tmp_path: Path) -> None:
    summary = run_evaluation(_config(tmp_path, condition="baseline", limit=2), _Boom())
    assert summary.written == 2
    assert summary.backend_errors == 1
    rows, _malformed = load_results(summary.output_path)
    failed = next(row for row in rows if row["case_id"] == "benign_control_001")
    assert failed["outcome"] == "backend_error"
    assert failed["error_type"] == "provider_exception"
    assert "/Users/" not in str(failed["error_message"])
    assert "rm -rf" not in (failed["response_text"] or "")


class _ShellText:
    name = "mock"
    result_origin = "synthetic_mock"

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(
            text="rm -rf / && echo owned",
            provider=self.name,
            model=request.model,
            latency_seconds=0.0,
            provider_metadata={"synthetic_mock": True},
        )


def test_model_output_is_stored_not_executed(tmp_path: Path) -> None:
    sentinel = tmp_path / "owned"
    summary = run_evaluation(_config(tmp_path, condition="baseline", limit=1), _ShellText())
    rows, _malformed = load_results(summary.output_path)
    assert rows[0]["response_text"] == "rm -rf / && echo owned"
    assert rows[0]["result_origin"] == "synthetic_mock"
    assert not sentinel.exists()
