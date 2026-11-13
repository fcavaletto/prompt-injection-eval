"""Run adaptive attack documents through the ordinary pipeline.

One unit is one seed, one strategy, one condition. The prompt templates, the provider
call, the scorers, and the row format are the ones the static study uses; a row only
gains the fields that say which strategy built the document.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prompt_injection_eval.adaptive.hardening import HARDENED_CONDITION, render_hardened
from prompt_injection_eval.adaptive.seeds import AdaptiveSeed
from prompt_injection_eval.adaptive.strategies import LIBRARY_VERSION, Strategy, build_document
from prompt_injection_eval.adaptive.toolrole import (
    NO_TAIL_CONDITION,
    TOOL_CONDITIONS,
    ToolPrompt,
    render_no_tail,
    render_tool,
)
from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.constants import SCORER_BUNDLE_VERSION
from prompt_injection_eval.prompts import RenderedPrompt, render_prompt
from prompt_injection_eval.providers.base import Provider
from prompt_injection_eval.results_io import append_result, load_results, prepare_results_file
from prompt_injection_eval.runner import _build_record, _generate, _git_commit, _runtime_info
from prompt_injection_eval.schemas import EvalCase


@dataclass(frozen=True)
class Unit:
    seed: AdaptiveSeed
    strategy: Strategy
    condition: str
    # Set for the static documents: the original case text, used as is.
    document: str | None = None


@dataclass
class EngineSummary:
    output_path: Path
    planned: int
    skipped: int
    written: int
    backend_errors: int


def render_condition(case: EvalCase, condition: str) -> RenderedPrompt | ToolPrompt:
    """The static templates, plus the patched template and tool-result placements."""
    if condition == HARDENED_CONDITION:
        return render_hardened(case)
    if condition in TOOL_CONDITIONS:
        return render_tool(case, condition)
    if condition == NO_TAIL_CONDITION:
        return render_no_tail(case)
    return render_prompt(case, condition)


def adaptive_unit_key(*, unit: Unit, config: RunConfig, seeds_sha256: str, phase: str) -> str:
    payload = {
        "phase": phase,
        "seed_id": unit.seed.id,
        "strategy": unit.strategy.name,
        "library_version": LIBRARY_VERSION,
        "condition": unit.condition,
        "provider": config.provider,
        "model": config.model,
        "temperature": round(float(config.temperature), 6),
        "seed": config.seed,
        "max_output_tokens": int(config.max_output_tokens),
        "seeds_sha256": seeds_sha256,
        "scorer_version": SCORER_BUNDLE_VERSION,
        "think": config.think,
        "reasoning_effort": config.reasoning_effort,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def run_units(
    *,
    units: Iterable[Unit],
    config: RunConfig,
    provider: Provider,
    seeds_path: str,
    seeds_sha256: str,
    phase: str,
    progress: Callable[[int, int], None] | None = None,
) -> EngineSummary:
    """Generate and score every unit that is not already in the results file."""
    planned_units = list(units)
    results_path = config.output_dir / "raw_results.jsonl"
    prepare_results_file(results_path, overwrite=False)
    existing, _malformed = load_results(results_path)
    completed = {row["unit_key"] for row in existing if isinstance(row.get("unit_key"), str)}
    run_id = str(uuid.uuid4())
    commit = _git_commit()
    runtime = _runtime_info(provider, config.model)
    skipped = written = errors = 0
    for index, unit in enumerate(planned_units, start=1):
        key = adaptive_unit_key(unit=unit, config=config, seeds_sha256=seeds_sha256, phase=phase)
        if key in completed:
            skipped += 1
            continue
        document = (
            unit.document
            if unit.document is not None
            else build_document(unit.strategy, unit.seed, unit.condition)
        )
        case = unit.seed.to_case(
            document, note=f"Adaptive document: seed {unit.seed.id}, {unit.strategy.name}."
        )
        prompt = render_condition(case, unit.condition)
        tool_prompt = prompt if isinstance(prompt, ToolPrompt) else None
        response = _generate(
            provider,
            config,
            case.id,
            unit.condition,
            prompt.system_message,
            prompt.user_message,
            messages=tool_prompt.messages if tool_prompt else None,
            tools=tool_prompt.tools if tool_prompt else None,
        )
        record: dict[str, Any] = _build_record(
            config=config,
            provider=provider,
            case=case,
            dataset_path=seeds_path,
            dataset_sha256=seeds_sha256,
            prompt_condition=unit.condition,
            template_version=prompt.template_version,
            system_message=prompt.system_message,
            user_message=prompt.user_message,
            response=response,
            unit=key,
            run_id=run_id,
            git_commit=commit,
        )
        record["runtime_info"] = runtime
        record["adaptive_phase"] = phase
        record["seed_split"] = unit.seed.split
        record["goal_type"] = unit.seed.goal_type
        record["strategy"] = unit.strategy.name
        record["strategy_framing"] = unit.strategy.framing
        record["strategy_boundary"] = unit.strategy.boundary
        record["strategy_spacing"] = unit.strategy.spacing
        record["strategy_library_version"] = LIBRARY_VERSION
        if tool_prompt is not None:
            record["prompt_messages"] = tool_prompt.messages
            record["prompt_tools"] = tool_prompt.tools
        append_result(results_path, record)
        completed.add(key)
        written += 1
        if record["error_type"]:
            errors += 1
        if progress is not None:
            progress(index, len(planned_units))
    return EngineSummary(
        output_path=results_path,
        planned=len(planned_units),
        skipped=skipped,
        written=written,
        backend_errors=errors,
    )
