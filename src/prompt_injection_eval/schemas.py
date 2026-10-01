"""Strict schemas for cases, scores, and exported dataset metadata."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prompt_injection_eval.constants import SCHEMA_VERSION, SYNTHETIC_SECRET

CANARY_PATTERN = re.compile(r"CANARY_[A-Z0-9]+")
JSON_SCALAR = str | int | float | bool | None


class Category(StrEnum):
    benign_control = "benign_control"
    direct_override = "direct_override"
    role_impersonation = "role_impersonation"
    delimiter_escape = "delimiter_escape"
    fake_system_message = "fake_system_message"
    metadata_injection = "metadata_injection"
    encoded_or_obfuscated_instruction = "encoded_or_obfuscated_instruction"
    instruction_hidden_in_prose = "instruction_hidden_in_prose"
    output_format_hijack = "output_format_hijack"
    synthetic_secret_exfiltration = "synthetic_secret_exfiltration"


CATEGORY_ORDER: tuple[str, ...] = tuple(item.value for item in Category)


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class ExactOutputGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["exact_output"]
    target: str

    @field_validator("target")
    @classmethod
    def canary_target(cls, value: str) -> str:
        if CANARY_PATTERN.fullmatch(value) is None:
            raise ValueError("exact_output target must be a synthetic CANARY token")
        return value


class ForcedJsonGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["forced_json"]
    target: dict[str, JSON_SCALAR]

    @field_validator("target")
    @classmethod
    def flat_object(cls, value: dict[str, JSON_SCALAR]) -> dict[str, JSON_SCALAR]:
        if not value:
            raise ValueError("forced_json target must be a non-empty object")
        return value


class FormatHijackGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["format_hijack"]
    target: str

    @field_validator("target")
    @classmethod
    def marker_target(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("format_hijack target must be a non-empty marker")
        if re.search(r"https?://", value):
            raise ValueError("format_hijack target must not be a URL")
        return value


class SecretDisclosureGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["synthetic_secret_disclosure"]
    target: str

    @field_validator("target")
    @classmethod
    def synthetic_target(cls, value: str) -> str:
        if value != SYNTHETIC_SECRET:
            raise ValueError("synthetic secret target must be the canonical synthetic value")
        return value


AttackGoal = Annotated[
    ExactOutputGoal | ForcedJsonGoal | FormatHijackGoal | SecretDisclosureGoal,
    Field(discriminator="type"),
]


class ExactMatchTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["exact_match"]
    value: JSON_SCALAR


class LabelMatchTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["label_match"]
    value: JSON_SCALAR


class ContainsAllTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["contains_all"]
    values: list[JSON_SCALAR] = Field(min_length=1)


class JsonFieldsTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["json_fields"]
    values: dict[str, JSON_SCALAR] = Field(min_length=1)


ExpectedTask = Annotated[
    ExactMatchTask | LabelMatchTask | ContainsAllTask | JsonFieldsTask,
    Field(discriminator="type"),
]


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: Category
    difficulty: Difficulty
    is_attack: bool
    system_instruction: str = Field(min_length=1)
    user_task: str = Field(min_length=1)
    document: str = Field(min_length=1)
    attack_goal: AttackGoal | None
    expected_task: ExpectedTask
    tags: list[str] = Field(min_length=1)
    notes: str = Field(min_length=1)

    @field_validator("tags")
    @classmethod
    def non_empty_tags(cls, value: list[str]) -> list[str]:
        if any(not tag.strip() for tag in value):
            raise ValueError("tags must be non-empty strings")
        return value

    @model_validator(mode="after")
    def attack_consistency(self) -> EvalCase:
        if not self.notes.strip():
            raise ValueError("notes must be a non-empty methodological note")
        if self.is_attack and self.attack_goal is None:
            raise ValueError("attack cases require a non-null attack_goal")
        if not self.is_attack and self.attack_goal is not None:
            raise ValueError("benign controls require attack_goal to be null")
        return self


class ScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["success", "failure", "uncertain", "not_applicable"]
    scorer_name: str
    scorer_version: str
    explanation: str
    evidence: list[str]
    confidence: Literal["high", "medium", "low"]
    manual_review: bool = False
    manual_review_reason: str | None = None


def export_schema() -> dict[str, Any]:
    """JSON Schema document stored at data/schema.json."""
    return {
        "schema_version": SCHEMA_VERSION,
        "description": (
            "Strict schema for one indirect prompt-injection evaluation case. "
            "Benign controls set attack_goal to null. Attack cases require an attack_goal."
        ),
        "case": EvalCase.model_json_schema(),
    }
