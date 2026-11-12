"""The current scorers must reproduce every label stored in results-published/.

The 0.2.0 rows were scored with attack-v1 and task-v1. attack-v2 and task-v2 only add
goal and task types, plus one secret rule. If a change to the scorers altered a
published label, the published tables would no longer follow from the published text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.conftest import CASES_PATH, ROOT

from prompt_injection_eval.dataset import load_cases
from prompt_injection_eval.outcome import classify_outcome
from prompt_injection_eval.scoring.attack import score_attack
from prompt_injection_eval.scoring.task import score_task

PUBLISHED = sorted((ROOT / "results-published").glob("*/raw_results.jsonl"))


@pytest.mark.parametrize("path", PUBLISHED, ids=lambda path: path.parent.name)
def test_published_labels_rescore_identically(path: Path) -> None:
    cases = {case.id: case for case in load_cases(CASES_PATH)}
    changed: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        case = cases[row["case_id"]]
        failed = bool(row.get("error_type"))
        attack = score_attack(case, row["response_text"], inference_failed=failed).label
        task = score_task(
            case, row["response_text"], inference_failed=failed, mode=row["task_scoring_mode"]
        ).label
        outcome = classify_outcome(
            is_attack=case.is_attack, attack_label=attack, task_label=task, inference_failed=failed
        )
        if (attack, task, outcome) != (row["attack_score"], row["task_score"], row["outcome"]):
            changed.append(f"{row['case_id']}/{row['condition']}")
    assert changed == []


def test_published_files_exist() -> None:
    assert len(PUBLISHED) >= 2
