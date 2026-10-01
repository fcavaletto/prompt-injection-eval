"""Dataset schema, safety, and smoke-file integrity tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from tests.conftest import CASES_PATH, SMOKE_PATH, case_by_id

from prompt_injection_eval.constants import SCHEMA_VERSION, SYNTHETIC_SECRET
from prompt_injection_eval.dataset import load_cases, safety_issues, validate_dataset
from prompt_injection_eval.hashing import sha256_file
from prompt_injection_eval.schemas import CATEGORY_ORDER, EvalCase, export_schema

SMOKE_IDS = [
    "benign_control_001",
    "direct_override_001",
    "delimiter_escape_002",
    "metadata_injection_004",
    "output_format_hijack_001",
    "secret_exfiltration_003",
]


def test_full_dataset_counts(full_cases: list[EvalCase]) -> None:
    assert len(full_cases) == 40
    assert sum(case.is_attack for case in full_cases) == 36
    assert sum(not case.is_attack for case in full_cases) == 4
    assert len({case.id for case in full_cases}) == 40
    assert {case.category.value for case in full_cases} == set(CATEGORY_ORDER)
    for category in CATEGORY_ORDER:
        assert sum(case.category.value == category for case in full_cases) == 4


def test_attack_goal_nullability(full_cases: list[EvalCase]) -> None:
    for case in full_cases:
        if case.is_attack:
            assert case.attack_goal is not None
        else:
            assert case.attack_goal is None
        assert case.tags
        assert case.notes.strip()
        assert case.difficulty.value in {"easy", "medium", "hard"}
        assert SYNTHETIC_SECRET in case.system_instruction


def test_only_synthetic_secret_and_no_local_paths(full_cases: list[EvalCase]) -> None:
    blob = CASES_PATH.read_text(encoding="utf-8")
    assert set(re.findall(r"SYNTHETIC_SECRET_[A-Z0-9]+", blob)) == {SYNTHETIC_SECRET}
    for case in full_cases:
        assert safety_issues(case) == []
    flagged = safety_issues(full_cases[0], raw_text='{"path": "/Users/example/secret"}')
    assert any("filesystem path" in issue for issue in flagged)
    credential = safety_issues(full_cases[0], raw_text="api_key=sk-live-not-a-real-key-value")
    assert any("credential-like" in issue for issue in credential)


def test_scorer_fields_present(full_cases: list[EvalCase]) -> None:
    for case in full_cases:
        task = case.expected_task
        if task.type in {"exact_match", "label_match"}:
            assert task.value is not None
        else:
            assert task.values
        if case.attack_goal is not None:
            assert case.attack_goal.target


def test_round_trip_and_unicode_newlines(full_cases: list[EvalCase], tmp_path: Path) -> None:
    for case in full_cases:
        again = EvalCase.model_validate(case.model_dump(mode="json"))
        assert again == case
    newline_case = case_by_id(full_cases, "metadata_injection_002")
    assert "\n" in newline_case.document
    reloaded = load_cases(CASES_PATH)
    assert case_by_id(reloaded, "metadata_injection_002").document == newline_case.document

    payload = full_cases[0].model_dump(mode="json")
    payload["id"] = "unicode_roundtrip"
    payload["document"] = "Café résumé — 東京\nsecond line"
    path = tmp_path / "unicode.jsonl"
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    loaded = load_cases(path)[0]
    assert loaded.document == "Café résumé — 東京\nsecond line"


def test_smoke_records_match_full_dataset(full_cases: list[EvalCase]) -> None:
    smoke, result = validate_dataset(SMOKE_PATH)
    assert result.valid
    assert len(smoke) == 6
    assert [case.id for case in smoke] == SMOKE_IDS
    full_by_id = {case.id: case for case in full_cases}
    for smoke_case in smoke:
        assert smoke_case.model_dump(mode="json") == full_by_id[smoke_case.id].model_dump(
            mode="json"
        )
    assert sha256_file(CASES_PATH) != sha256_file(SMOKE_PATH)


def test_schema_file_matches_pydantic_export() -> None:
    payload = json.loads((CASES_PATH.parent / "schema.json").read_text(encoding="utf-8"))
    assert payload == export_schema()
    assert payload["schema_version"] == SCHEMA_VERSION


def test_validation_report_is_computed(full_cases: list[EvalCase]) -> None:
    _cases, result = validate_dataset(CASES_PATH)
    assert result.cases == len(full_cases)
    assert result.attack_cases == 36
    assert result.benign_controls == 4
    assert result.unique_ids == 40
    assert result.schema_version == "1.0"
    assert len(result.sha256) == 64
    assert result.category_counts["benign_control"] == 4


def test_duplicate_ids_are_rejected(full_cases: list[EvalCase], tmp_path: Path) -> None:
    line = json.dumps(full_cases[0].model_dump(mode="json"))
    path = tmp_path / "dup.jsonl"
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    _cases, result = validate_dataset(path)
    assert not result.valid
    assert any("Duplicate" in error for error in result.errors)


def test_invalid_json_reports_line_number(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "x"}\n{not json\n', encoding="utf-8")
    with pytest.raises(Exception, match="line 1|line 2"):
        load_cases(path)
