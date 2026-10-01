"""Sequential evaluation runner with incremental writes and resume."""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.constants import PACKAGE_VERSION, SCHEMA_VERSION, SCORER_BUNDLE_VERSION
from prompt_injection_eval.dataset import DatasetError, filter_cases, validate_dataset
from prompt_injection_eval.outcome import classify_outcome
from prompt_injection_eval.privacy import platform_summary, python_version, sanitize_text
from prompt_injection_eval.prompts import conditions_for, render_prompt
from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse, Provider
from prompt_injection_eval.results_io import (
    ResultsError,
    append_result,
    load_results,
    prepare_results_file,
    unit_key,
)
from prompt_injection_eval.schemas import EvalCase
from prompt_injection_eval.scoring.attack import score_attack
from prompt_injection_eval.scoring.task import score_task


class RunnerError(RuntimeError):
    """The run could not start. Per-case inference errors are recorded instead."""


@dataclass
class RunSummary:
    output_path: Path
    planned_units: int
    skipped: int
    written: int
    backend_errors: int
    malformed_lines: list[int] = field(default_factory=list)
    dataset_sha256: str = ""


def run_evaluation(config: RunConfig, provider: Provider) -> RunSummary:
    if config.concurrency != 1:
        raise RunnerError("Only sequential inference is implemented. Keep concurrency at 1.")
    if config.overwrite and config.resume:
        # Overwrite is the explicit request to recreate raw_results.jsonl.
        config = config.model_copy(update={"resume": False})
    cases, validation = validate_dataset(config.dataset)
    if not validation.valid:
        raise RunnerError("\n".join(validation.errors))
    try:
        selected = filter_cases(
            cases,
            case_ids=config.case_ids or None,
            category=config.category,
            difficulty=config.difficulty,
            limit=config.limit,
        )
    except DatasetError as exc:
        raise RunnerError(str(exc)) from exc
    condition_names = conditions_for(config.condition)
    results_path = config.output_dir / "raw_results.jsonl"
    if results_path.exists() and not config.resume and not config.overwrite:
        raise RunnerError(
            "Results already exist. Re-run with --resume to skip completed units "
            "or --overwrite to replace raw_results.jsonl."
        )
    try:
        prepare_results_file(results_path, overwrite=config.overwrite)
    except ResultsError as exc:
        raise RunnerError(str(exc)) from exc

    existing, malformed = ([], []) if config.overwrite else load_results(results_path)
    completed = {row["unit_key"] for row in existing if isinstance(row.get("unit_key"), str)}
    run_id = str(uuid.uuid4())
    commit = _git_commit()
    skipped = 0
    written = 0
    backend_errors = 0
    planned = len(selected) * len(condition_names)

    for case in selected:
        for condition in condition_names:
            prompt = render_prompt(case, condition)
            key = unit_key(
                case_id=case.id,
                condition=condition,
                provider=provider.name,
                model=config.model,
                temperature=config.temperature,
                seed=config.seed,
                max_output_tokens=config.max_output_tokens,
                prompt_template_version=prompt.template_version,
                dataset_sha256=validation.sha256,
            )
            if config.resume and key in completed:
                skipped += 1
                continue
            response = _generate(
                provider, config, case.id, condition, prompt.system_message, prompt.user_message
            )
            record = _build_record(
                config=config,
                provider=provider,
                case=case,
                dataset_path=validation.path,
                dataset_sha256=validation.sha256,
                prompt_condition=condition,
                template_version=prompt.template_version,
                system_message=prompt.system_message,
                user_message=prompt.user_message,
                response=response,
                unit=key,
                run_id=run_id,
                git_commit=commit,
            )
            append_result(results_path, record)
            written += 1
            if record["error_type"]:
                backend_errors += 1
    return RunSummary(
        output_path=results_path,
        planned_units=planned,
        skipped=skipped,
        written=written,
        backend_errors=backend_errors,
        malformed_lines=malformed,
        dataset_sha256=validation.sha256,
    )


def _generate(
    provider: Provider,
    config: RunConfig,
    case_id: str,
    condition: str,
    system_message: str,
    user_message: str,
) -> GenerationResponse:
    request = GenerationRequest(
        model=config.model,
        system_message=system_message,
        user_message=user_message,
        temperature=config.temperature,
        seed=config.seed,
        max_output_tokens=config.max_output_tokens,
        timeout_seconds=config.timeout_seconds,
        provider_settings={"keep_alive": config.keep_alive},
        metadata={"case_id": case_id, "condition": condition},
    )
    try:
        return provider.generate(request)
    except Exception as exc:  # noqa: BLE001 - one failed call must not abort the run
        return GenerationResponse(
            text=None,
            provider=provider.name,
            model=config.model,
            latency_seconds=None,
            error_type="provider_exception",
            error_message=sanitize_text(str(exc)),
        )


def _build_record(
    *,
    config: RunConfig,
    provider: Provider,
    case: EvalCase,
    dataset_path: str,
    dataset_sha256: str,
    prompt_condition: str,
    template_version: str,
    system_message: str,
    user_message: str,
    response: GenerationResponse,
    unit: str,
    run_id: str,
    git_commit: str | None,
) -> dict[str, Any]:
    failed = not response.ok
    attack = score_attack(case, response.text, inference_failed=failed)
    task = score_task(case, response.text, inference_failed=failed, mode=config.task_mode)
    outcome = classify_outcome(
        is_attack=case.is_attack,
        attack_label=attack.label,
        task_label=task.label,
        inference_failed=failed,
    )
    reasons = _review_reasons(
        attack.manual_review_reason, task.manual_review_reason, response, config
    )
    return {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result_origin": provider.result_origin,
        "case_id": case.id,
        "category": case.category.value,
        "difficulty": case.difficulty.value,
        "is_attack": case.is_attack,
        "user_task": case.user_task,
        "document": case.document,
        "dataset_path": dataset_path,
        "dataset_sha256": dataset_sha256,
        "dataset_schema_version": SCHEMA_VERSION,
        "provider": provider.name,
        "model": config.model,
        "condition": prompt_condition,
        "prompt_template_version": template_version,
        "system_message": system_message,
        "user_message": user_message,
        "response_text": response.text,
        "temperature": config.temperature,
        "seed": config.seed,
        "max_output_tokens": config.max_output_tokens,
        "timeout_seconds": config.timeout_seconds,
        "task_scoring_mode": config.task_mode,
        "scorer_version": SCORER_BUNDLE_VERSION,
        "attack_scorer_name": attack.scorer_name,
        "attack_scorer_version": attack.scorer_version,
        "attack_score": attack.label,
        "attack_explanation": attack.explanation,
        "attack_evidence": attack.evidence,
        "attack_confidence": attack.confidence,
        "task_scorer_name": task.scorer_name,
        "task_scorer_version": task.scorer_version,
        "task_score": task.label,
        "task_explanation": task.explanation,
        "task_evidence": task.evidence,
        "task_confidence": task.confidence,
        "outcome": outcome,
        "outcome_version": "outcome-v1",
        "manual_review": bool(reasons),
        "manual_review_reason": " | ".join(reasons) if reasons else None,
        "error_type": response.error_type,
        "error_message": response.error_message,
        "latency_seconds": response.latency_seconds,
        "prompt_token_count": response.prompt_token_count,
        "completion_token_count": response.completion_token_count,
        "total_duration_ns": response.total_duration_ns,
        "load_duration_ns": response.load_duration_ns,
        "prompt_eval_duration_ns": response.prompt_eval_duration_ns,
        "eval_duration_ns": response.eval_duration_ns,
        "provider_metadata": response.provider_metadata,
        "package_version": PACKAGE_VERSION,
        "git_commit": git_commit,
        "python_version": python_version(),
        "platform_summary": platform_summary(),
        "unit_key": unit,
    }


def _review_reasons(
    attack_reason: str | None,
    task_reason: str | None,
    response: GenerationResponse,
    config: RunConfig,
) -> list[str]:
    reasons: list[str] = []
    if attack_reason:
        reasons.append(attack_reason)
    if task_reason and task_reason not in reasons:
        reasons.append(task_reason)
    metadata = response.provider_metadata or {}
    done_reason = metadata.get("done_reason")
    truncated = done_reason in {"length", "max_tokens"}
    completion = response.completion_token_count
    if completion is not None and completion >= config.max_output_tokens:
        truncated = True
    if truncated:
        reasons.append("Backend response metadata suggesting truncation.")
    return reasons


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    if commit and all(character in "0123456789abcdef" for character in commit):
        return commit
    return None
