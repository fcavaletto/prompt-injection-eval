"""Incremental JSONL result files, resume keys, and interrupted-write recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from prompt_injection_eval.constants import SCORER_BUNDLE_VERSION


class ResultsError(ValueError):
    """The results file could not be read or written safely."""


def unit_key(
    *,
    case_id: str,
    condition: str,
    provider: str,
    model: str,
    temperature: float,
    seed: int | None,
    max_output_tokens: int,
    prompt_template_version: str,
    dataset_sha256: str,
    scorer_version: str = SCORER_BUNDLE_VERSION,
    think: bool | None = None,
) -> str:
    payload = {
        "case_id": case_id,
        "condition": condition,
        "provider": provider,
        "model": model,
        "temperature": round(float(temperature), 6),
        "seed": seed,
        "max_output_tokens": int(max_output_tokens),
        "prompt_template_version": prompt_template_version,
        "dataset_sha256": dataset_sha256,
        "scorer_version": scorer_version,
        "think": think,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def load_results(path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    """Load valid JSON objects. Malformed lines are reported and left untouched."""
    if not path.exists():
        return [], []
    rows: list[dict[str, Any]] = []
    malformed: list[int] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(lineno)
            continue
        if not isinstance(payload, dict):
            malformed.append(lineno)
            continue
        rows.append(payload)
    return rows, malformed


def append_result(path: Path, record: dict[str, Any]) -> None:
    """Write one record immediately so an interruption keeps earlier rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.name != "raw_results.jsonl":
        raise ResultsError(f"Refusing to append to unexpected file: {path.name}")
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def prepare_results_file(path: Path, *, overwrite: bool) -> None:
    """Create or replace only raw_results.jsonl. Other files in the directory stay."""
    if path.name != "raw_results.jsonl":
        raise ResultsError("Results must be written to raw_results.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        temporary = path.with_suffix(".jsonl.tmp")
        temporary.write_text("", encoding="utf-8")
        temporary.replace(path)
    elif not path.exists():
        path.write_text("", encoding="utf-8")
