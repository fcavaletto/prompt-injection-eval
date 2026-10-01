"""Shared paths and case loaders for the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from prompt_injection_eval.dataset import validate_dataset
from prompt_injection_eval.schemas import EvalCase

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "cases.jsonl"
SMOKE_PATH = ROOT / "data" / "smoke_cases.jsonl"


@pytest.fixture(scope="session")
def full_cases() -> list[EvalCase]:
    cases, result = validate_dataset(CASES_PATH)
    assert result.valid, result.errors
    return cases


def case_by_id(cases: list[EvalCase], case_id: str) -> EvalCase:
    return next(item for item in cases if item.id == case_id)
