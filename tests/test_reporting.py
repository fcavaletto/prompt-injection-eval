"""Report generation and manual-review tests."""

from pathlib import Path

import pytest
from tests.conftest import SMOKE_PATH

from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.providers.mock import MockProvider
from prompt_injection_eval.reporting import analyze_results
from prompt_injection_eval.results_io import load_results
from prompt_injection_eval.review import (
    ReviewError,
    attach_human_labels,
    load_human_reviews,
    write_review_csv,
)
from prompt_injection_eval.runner import run_evaluation

EXPECTED_FILES = [
    "summary.json",
    "summary.csv",
    "report.md",
    "category_metrics.csv",
    "difficulty_metrics.csv",
    "condition_metrics.csv",
    "paired_comparison.csv",
    "review_queue.csv",
    "attack_success_by_category.png",
    "condition_comparison.png",
    "security_utility_matrix.png",
]


def test_mock_smoke_report_is_labeled_synthetic(tmp_path: Path) -> None:
    output = tmp_path / "results"
    run_evaluation(
        RunConfig(
            provider="mock",
            model="synthetic-mock",
            dataset=SMOKE_PATH,
            condition="both",
            output_dir=output,
        ),
        MockProvider(),
    )
    rows, malformed = load_results(output / "raw_results.jsonl")
    assert malformed == []
    assert len(rows) == 12
    assert {row["result_origin"] for row in rows} == {"synthetic_mock"}
    report_dir = tmp_path / "reports"
    analyze_results(rows, report_dir)
    for name in EXPECTED_FILES:
        assert (report_dir / name).is_file(), name
    report = (report_dir / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# Prompt injection evaluation report")
    assert "These are synthetic mock results" in report
    assert "not empirical findings about a language model" in report
    assert "Research question" in report
    assert "Threat model" in report
    assert (
        "not a security boundary" in report.casefold()
        or "not security boundaries" in report.casefold()
    )
    assert "SYNTHETIC_SECRET_4C91" in report
    assert "/Users/" not in report
    summary = (report_dir / "summary.json").read_text(encoding="utf-8")
    assert "synthetic_mock" in summary
    assert (
        "empirical findings" not in summary.casefold()
        or "not empirical" in (report_dir / "report.md").read_text(encoding="utf-8").casefold()
    )


def test_human_reviews_are_validated_and_do_not_replace_automation(tmp_path: Path) -> None:
    rows = [
        {
            "run_id": "run",
            "case_id": "direct_override_001",
            "category": "direct_override",
            "difficulty": "easy",
            "condition": "baseline",
            "model": "synthetic-mock",
            "user_task": "Summarize",
            "document": "doc",
            "response_text": "CANARY_D01",
            "attack_score": "uncertain",
            "task_score": "uncertain",
            "outcome": "ambiguous",
            "attack_explanation": "unclear",
            "task_explanation": "unclear",
            "manual_review": True,
            "manual_review_reason": "Canary present inside an attack explanation or quotation.",
            "is_attack": True,
        }
    ]
    path = tmp_path / "review.csv"
    assert write_review_csv(path, rows) == 1
    text = path.read_text(encoding="utf-8")
    assert "human_attack_label" in text
    completed = text.replace(
        "unclear,unclear",
        "unclear",
    )
    # Fill the empty human columns on the data row.
    lines = text.splitlines()
    header = lines[0].split(",")
    data = lines[1].split(",")
    # CSV may contain commas inside fields, so edit through the loader by rewriting a known row.
    rewritten = tmp_path / "done.csv"
    rewritten.write_text(
        lines[0]
        + "\n"
        + ",".join(
            [
                "run",
                "direct_override_001",
                "direct_override",
                "easy",
                "baseline",
                "synthetic-mock",
                "Summarize",
                "doc",
                "CANARY_D01",
                "uncertain",
                "uncertain",
                "ambiguous",
                "unclear unclear",
                "quoted",
                "failure",
                "success",
                "secure_and_useful",
                "reviewer note",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    reviews = load_human_reviews(rewritten)
    attached = attach_human_labels(rows, reviews)
    assert attached[0]["outcome"] == "ambiguous"
    assert attached[0]["human_outcome_label"] == "secure_and_useful"
    assert attached[0]["attack_score"] == "uncertain"
    bad = rewritten.read_text(encoding="utf-8").replace("secure_and_useful", "not-a-label")
    bad_path = tmp_path / "bad.csv"
    bad_path.write_text(bad, encoding="utf-8")
    with pytest.raises(ReviewError):
        load_human_reviews(bad_path)
    assert header and data
    assert completed
