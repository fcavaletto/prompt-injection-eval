"""CLI tests. They use the mock provider and never contact Ollama."""

from pathlib import Path

from tests.conftest import CASES_PATH, SMOKE_PATH
from typer.testing import CliRunner

from prompt_injection_eval.cli import app

runner = CliRunner()


def test_help_and_version() -> None:
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    for command in ("doctor", "validate-data", "list-cases", "run", "analyze", "review", "version"):
        assert command in help_result.stdout
    version = runner.invoke(app, ["version"])
    assert version.exit_code == 0
    assert "0.2.0" in version.stdout


def test_validate_and_list() -> None:
    validated = runner.invoke(app, ["validate-data", "--dataset", str(CASES_PATH)])
    assert validated.exit_code == 0
    assert "Dataset valid:" in validated.stdout
    assert "Cases: 40" in validated.stdout
    assert "Attack cases: 36" in validated.stdout
    assert "Benign controls: 4" in validated.stdout
    assert "Categories: 10" in validated.stdout
    assert "Schema version: 1.0" in validated.stdout
    assert "SHA-256:" in validated.stdout
    assert "direct_override: 4" in validated.stdout
    listed = runner.invoke(
        app,
        ["list-cases", "--dataset", str(CASES_PATH), "--category", "delimiter_escape"],
    )
    assert listed.exit_code == 0
    body = [line for line in listed.stdout.splitlines() if line and not line.startswith("id\t")]
    assert len(body) == 4
    assert all("delimiter_escape" in line for line in body)


def test_doctor_mock_and_smoke_run(tmp_path: Path) -> None:
    doctor = runner.invoke(
        app,
        [
            "doctor",
            "--provider",
            "mock",
            "--dataset",
            str(CASES_PATH),
            "--output-dir",
            str(tmp_path / "results"),
        ],
    )
    assert doctor.exit_code == 0, doctor.stdout
    assert "Ollama is not required" in doctor.stdout
    assert "Doctor checks passed." in doctor.stdout

    output = tmp_path / "mock-smoke"
    run = runner.invoke(
        app,
        [
            "run",
            "--provider",
            "mock",
            "--dataset",
            str(SMOKE_PATH),
            "--condition",
            "both",
            "--limit",
            "1",
            "--output-dir",
            str(output),
        ],
    )
    assert run.exit_code == 0, run.stdout
    assert "Resolved run configuration:" in run.stdout
    assert "not empirical" in run.stdout.casefold()
    assert (output / "raw_results.jsonl").is_file()

    report_dir = tmp_path / "report"
    analyzed = runner.invoke(
        app,
        ["analyze", "--input-dir", str(output), "--output-dir", str(report_dir)],
    )
    assert analyzed.exit_code == 0, analyzed.stdout
    assert "synthetic mock results" in analyzed.stdout.casefold()
    assert (report_dir / "report.md").is_file()

    review = runner.invoke(
        app,
        [
            "review",
            "--input",
            str(output / "raw_results.jsonl"),
            "--output",
            str(output / "manual_review.csv"),
        ],
    )
    assert review.exit_code == 0, review.stdout
    assert (output / "manual_review.csv").is_file()
