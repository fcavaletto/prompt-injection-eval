"""Adaptive seeds: an attack case with the injected text taken out.

The carrier is the benign document. The ask is the attacker's demand as one sentence.
A strategy turns the pair into a document, and `to_case` wraps that document in an
ordinary EvalCase so the unchanged scorers judge it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from prompt_injection_eval.schemas import AttackGoal, Category, Difficulty, EvalCase, ExpectedTask


class AdaptiveSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    split: Literal["dev", "test"]
    goal_type: str
    category: Category
    difficulty: Difficulty
    system_instruction: str = Field(min_length=1)
    user_task: str = Field(min_length=1)
    carrier: str = Field(min_length=1)
    ask: str = Field(min_length=1)
    attack_goal: AttackGoal
    expected_task: ExpectedTask

    def to_case(self, document: str, *, note: str) -> EvalCase:
        return EvalCase(
            id=self.id,
            category=self.category,
            difficulty=self.difficulty,
            is_attack=True,
            system_instruction=self.system_instruction,
            user_task=self.user_task,
            document=document,
            attack_goal=self.attack_goal,
            expected_task=self.expected_task,
            tags=["adaptive"],
            notes=note,
        )


class SeedError(ValueError):
    """The seed file is missing or invalid."""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_seeds(path: Path) -> tuple[list[AdaptiveSeed], str]:
    """Return the seeds and the SHA-256 of the file they were read from."""
    if not path.is_file():
        raise SeedError(f"Seed file not found: {path.name}")
    seeds: list[AdaptiveSeed] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            seed = AdaptiveSeed.model_validate(json.loads(line))
        except ValueError as exc:
            raise SeedError(f"{path.name} line {lineno}: {exc}") from exc
        if seed.id in seen:
            raise SeedError(f"{path.name} line {lineno}: duplicate seed id {seed.id}")
        if seed.goal_type != seed.attack_goal.type:
            raise SeedError(f"{path.name} line {lineno}: goal_type does not match attack_goal")
        seen.add(seed.id)
        seeds.append(seed)
    if not seeds:
        raise SeedError(f"{path.name} contains no seeds")
    return seeds, file_sha256(path)
