"""`pie stats` end to end on mock runs and on the published 0.2.0 rows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.conftest import ROOT, SMOKE_PATH
from typer.testing import CliRunner

from prompt_injection_eval.cli import app
from prompt_injection_eval.config import RunConfig
from prompt_injection_eval.providers.mock import MockProvider
from prompt_injection_eval.runner import run_evaluation

runner = CliRunner()


def _mock_run(tmp_path: Path, model: str) -> Path:
    out = tmp_path / model
    config = RunConfig(
        provider="mock",
        model=model,
        dataset=SMOKE_PATH,
        condition="all",
        output_dir=out,
        seed=42,
    )
    run_evaluation(config, MockProvider())
    return out


def test_stats_on_mock_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    first = _mock_run(tmp_path, "mock-a")
    second = _mock_run(tmp_path, "mock-b")
    out = tmp_path / "stats"
    result = runner.invoke(
        app,
        ["stats", "--input-dir", str(first), "--input-dir", str(second), "--output-dir", str(out)],
    )
    assert result.exit_code == 0, result.stdout
    for name in ("stats.md", "stats.json", "defense_tests.csv", "model_tests.csv", "power.csv"):
        assert (out / name).is_file()
    summary = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    contrasts = {item["contrast"] for item in summary["defense_tests"]}
    assert contrasts == {"baseline vs defended", "baseline vs spotlight", "defended vs spotlight"}
    assert {item["condition"] for item in summary["model_tests"]} == {
        "baseline",
        "defended",
        "spotlight",
    }
    assert summary["smallest_significant_split"] == 6
    assert "McNemar" in (out / "stats.md").read_text(encoding="utf-8")


def test_stats_refuses_repeats_of_one_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    first = _mock_run(tmp_path, "mock-a")
    result = runner.invoke(
        app,
        [
            "stats",
            "--input-dir",
            str(first),
            "--input-dir",
            str(first),
            "--output-dir",
            str(tmp_path / "s"),
        ],
    )
    assert result.exit_code == 1


def test_stats_calibrates_lenient_reading_on_published_reviews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    published = ROOT / "results-published"
    out = tmp_path / "stats-v02"
    result = runner.invoke(
        app,
        [
            "stats",
            "--input-dir",
            str(published / "deepseek-r1-14b"),
            "--input-dir",
            str(published / "qwen2.5-7b"),
            "--reviews",
            str(published / "deepseek-r1-14b" / "manual_review.csv"),
            "--reviews",
            str(published / "qwen2.5-7b" / "manual_review.csv"),
            "--output-dir",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stdout
    summary = json.loads((out / "stats.json").read_text(encoding="utf-8"))
    calibration = {item["model"]: item for item in summary["lenient_calibration"]["per_model"]}
    # The published author labels: strict agreed on 54/67 and 52/73 task labels.
    assert calibration["deepseek-r1:14b"]["reviewed"] == 67
    assert calibration["deepseek-r1:14b"]["strict_agreements"] == 54
    assert calibration["qwen2.5:7b"]["strict_agreements"] == 52
    assert calibration["qwen2.5:7b"]["lenient_agreements"] >= 52
    deepseek_defended = next(
        item
        for item in summary["defense_tests"]
        if item["model"] == "deepseek-r1:14b"
        and item["contrast"] == "baseline vs defended"
        and item["field"] == "attack_score"
        and item["uncertain_counted_as"] == "not success"
    )
    assert (deepseek_defended["only_first"], deepseek_defended["only_second"]) == (4, 0)
    assert deepseek_defended["mcnemar"]["p_value"] == pytest.approx(0.125)
