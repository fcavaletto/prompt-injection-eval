"""Cross-run comparison, scorer agreement, and repeated-run variability."""

from pathlib import Path

import pytest
from tests.conftest import SMOKE_PATH
from typer.testing import CliRunner

from prompt_injection_eval.cli import app
from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.metrics import (
    by_model_condition,
    paired_by_model,
    paired_comparisons,
    repeat_variability,
    scorer_agreement,
)
from prompt_injection_eval.providers.mock import MockProvider
from prompt_injection_eval.results_io import load_results
from prompt_injection_eval.runner import run_evaluation


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "case_id": "case",
        "category": "direct_override",
        "difficulty": "easy",
        "is_attack": True,
        "provider": "mock",
        "model": "model-a",
        "dataset_sha256": "abc",
        "temperature": 0.0,
        "seed": None,
        "max_output_tokens": 256,
        "scorer_version": "attack-v1+task-v1+outcome-v1",
        "condition": "baseline",
        "attack_score": "failure",
        "task_score": "success",
        "outcome": "secure_and_useful",
        "response_text": "ok",
        "error_type": None,
        "manual_review": False,
        "reasoning_truncated": False,
    }
    base.update(overrides)
    return base


def test_by_model_condition_separates_models() -> None:
    rows = [
        _row(case_id="a", model="model-a", attack_score="success", outcome="compromised"),
        _row(case_id="b", model="model-a"),
        _row(case_id="a", model="model-b"),
        _row(case_id="b", model="model-b", reasoning_truncated=True, task_score="failure"),
        _row(case_id="c", model="model-b", is_attack=False, outcome="benign_task_success"),
    ]
    groups = {(g["model"], g["condition"]): g for g in by_model_condition(rows)}
    a = groups[("model-a", "baseline")]
    b = groups[("model-b", "baseline")]
    assert a["attack_success_rate_valid"] == 0.5
    assert a["attack_success_rate_valid_ci"]["low"] is not None
    assert b["attack_success_rate_valid"] == 0.0
    assert b["reasoning_truncated"] == 1
    assert b["benign_units_valid"] == 1
    assert b["benign_task_success_rate_valid"] == 1.0


def test_paired_by_model_keeps_models_apart() -> None:
    rows = [
        _row(case_id="a", model="model-a", attack_score="success", outcome="compromised"),
        _row(case_id="a", model="model-a", condition="defended"),
        _row(case_id="a", model="model-b"),
        _row(case_id="a", model="model-b", condition="defended"),
    ]
    per_model = {item["model"]: item for item in paired_by_model(rows)}
    assert per_model["model-a"]["improved"] == 1
    assert per_model["model-b"]["unchanged"] == 1
    assert per_model["model-a"]["baseline_attack_success_rate"] == 1.0
    assert per_model["model-a"]["defended_attack_success_rate"] == 0.0


def test_paired_comparisons_one_per_defense() -> None:
    rows = [
        _row(case_id="a", attack_score="success", outcome="compromised"),
        _row(case_id="a", condition="defended"),
        _row(case_id="a", condition="spotlight", attack_score="success", outcome="compromised"),
    ]
    both = paired_comparisons(rows)
    assert list(both) == ["defended", "spotlight"]
    assert both["defended"]["improved"] == 1
    assert both["defended"]["defense_condition"] == "defended"
    assert both["spotlight"]["unchanged"] == 1
    assert both["spotlight"]["rows"][0]["defense_condition"] == "spotlight"
    per_model = paired_by_model(rows)
    assert [item["defense_condition"] for item in per_model] == ["defended", "spotlight"]


def test_analyze_with_all_conditions_writes_per_defense_outputs(tmp_path: Path) -> None:
    run_dir = _mock_run(tmp_path, "all", "mock-alpha", "all")
    out = tmp_path / "report"
    result = CliRunner().invoke(
        app, ["analyze", "--input-dir", str(run_dir), "--output-dir", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "paired_comparison.csv").is_file()
    assert (out / "paired_comparison_spotlight.csv").is_file()
    assert (out / "security_utility_matrix_spotlight.png").is_file()
    text = (out / "report.md").read_text(encoding="utf-8")
    assert "comparison: defended-v1" in text
    assert "comparison: spotlight (defended-v2)" in text
    assert "datamarking" in text
    assert "--condition all" in text
    rows, _ = load_results(run_dir / "raw_results.jsonl")
    assert {row["condition"] for row in rows} == {"baseline", "defended", "spotlight"}
    assert {row["prompt_template_version"] for row in rows} == {
        "baseline-v1",
        "defended-v1",
        "defended-v2",
    }


def test_scorer_agreement_counts_only_labelled_rows() -> None:
    rows = [
        _row(case_id="a", human_attack_label="failure", human_task_label="failure"),
        _row(case_id="b", attack_score="uncertain", human_attack_label="success"),
        _row(case_id="c"),
    ]
    agreement = scorer_agreement(rows)
    assert agreement["reviewed_rows"] == 2
    attack = agreement["dimensions"]["attack"]
    assert attack["reviewed"] == 2
    assert attack["agreements"] == 1
    assert attack["confusion"] == {"failure->failure": 1, "uncertain->success": 1}
    task = agreement["dimensions"]["task"]
    assert task["reviewed"] == 1
    assert task["agreements"] == 0
    assert agreement["dimensions"]["outcome"]["reviewed"] == 0
    assert agreement["dimensions"]["outcome"]["agreement_rate"] is None
    dims = {item["dimension"] for item in agreement["disagreements"]}
    assert dims == {"attack", "task"}


def test_repeat_variability_flags_changed_units() -> None:
    run1 = [_row(case_id="a"), _row(case_id="b", response_text="first")]
    run2 = [
        _row(case_id="a"),
        _row(case_id="b", response_text="second", outcome="compromised", attack_score="success"),
    ]
    run3 = [_row(case_id="a"), _row(case_id="b", response_text="first")]
    result = repeat_variability([run1, run2, run3])
    assert result["runs"] == 3
    assert result["units_compared"] == 2
    assert result["identical_response_text"] == 1
    assert result["unstable_outcome"] == 1
    assert result["unstable_attack_score"] == 1
    assert result["unstable_task_score"] == 0
    assert result["unstable_units"][0]["case_id"] == "b"
    with pytest.raises(ValueError):
        repeat_variability([run1])


def _mock_run(tmp_path: Path, name: str, model: str, condition: str = "both") -> Path:
    output_dir = tmp_path / name
    run_evaluation(
        RunConfig(
            provider="mock",
            model=model,
            dataset=SMOKE_PATH,
            condition=condition,  # type: ignore[arg-type]
            output_dir=output_dir,
        ),
        MockProvider(),
    )
    return output_dir


def test_compare_cli_writes_tables_and_chart(tmp_path: Path) -> None:
    a = _mock_run(tmp_path, "a", "mock-alpha")
    b = _mock_run(tmp_path, "b", "mock-beta")
    out = tmp_path / "compare"
    result = CliRunner().invoke(
        app,
        ["compare", "--input-dir", str(a), "--input-dir", str(b), "--output-dir", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "synthetic mock" in result.output
    for name in (
        "summary.json",
        "compare.md",
        "model_metrics.csv",
        "model_condition_metrics.csv",
        "paired_by_model.csv",
        "model_condition_comparison.png",
        "model_condition_utility.png",
    ):
        assert (out / name).is_file(), name
    text = (out / "compare.md").read_text(encoding="utf-8")
    assert "`mock-alpha`" in text and "`mock-beta`" in text
    assert "Synthetic results" in text
    assert "No human labels are attached" in text


def test_variability_cli_on_identical_mock_runs(tmp_path: Path) -> None:
    runs = [_mock_run(tmp_path, f"r{i}", "mock-alpha", "baseline") for i in range(3)]
    out = tmp_path / "var"
    args = ["variability", "--output-dir", str(out)]
    for run in runs:
        args += ["--input-dir", str(run)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    rows, _ = load_results(runs[0] / "raw_results.jsonl")
    assert f"over {len(rows)} units" in result.output
    assert "Outcome changed on 0" in result.output
    assert (out / "variability.md").is_file()
    assert (out / "variability.json").is_file()


def test_variability_cli_requires_two_dirs(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["variability", "--input-dir", str(tmp_path), "--output-dir", str(tmp_path / "o")]
    )
    assert result.exit_code == 1
