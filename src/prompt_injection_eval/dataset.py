"""JSONL loading, safety checks, and dataset summaries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from prompt_injection_eval.constants import SCHEMA_VERSION, SYNTHETIC_SECRET
from prompt_injection_eval.hashing import sha256_file
from prompt_injection_eval.schemas import CATEGORY_ORDER, EvalCase

_CREDENTIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bpassword\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bsecret\s*[:=]\s*(?!SYNTHETIC_SECRET_4C91\b)\S+"),
)
_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|/etc/|/var/|~\/|[A-Za-z]:\\)")
_SECRET_TOKEN = re.compile(r"SYNTHETIC_SECRET_[A-Z0-9]+")
_UNSAFE_OBJECTIVE = re.compile(
    r"(?i)\b(rm\s+-rf|subprocess|os\.system|eval\(|exec\(|curl\s+https?://|wget\s+https?://)\b"
)


class DatasetError(ValueError):
    """A dataset file could not be loaded or failed validation."""


@dataclass
class ValidationResult:
    path: str
    valid: bool
    cases: int
    attack_cases: int
    benign_controls: int
    categories: int
    unique_ids: int
    schema_version: str
    sha256: str
    category_counts: dict[str, int]
    errors: list[str] = field(default_factory=list)


def load_cases(path: Path) -> list[EvalCase]:
    """Parse a JSONL dataset. Raises DatasetError with a line number on failure."""
    if not path.is_file():
        raise DatasetError(f"Dataset file not found: {path.name}")
    text = path.read_text(encoding="utf-8")
    cases: list[EvalCase] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(
                f"Dataset validation failed on line {lineno}: invalid JSON ({exc.msg})"
            ) from exc
        try:
            cases.append(EvalCase.model_validate(payload))
        except ValidationError as exc:
            raise DatasetError(
                f"Dataset validation failed on line {lineno}: {exc.errors()[0]['msg']}"
            ) from exc
    return cases


def safety_issues(case: EvalCase, raw_text: str | None = None) -> list[str]:
    """Return methodological safety problems for one case. Empty means acceptable."""
    blob = raw_text if raw_text is not None else case.model_dump_json()
    issues: list[str] = []
    for pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(blob):
            issues.append(f"{case.id}: credential-like pattern detected")
            break
    if _PATH_PATTERN.search(blob):
        issues.append(f"{case.id}: local filesystem path detected")
    if _UNSAFE_OBJECTIVE.search(blob):
        issues.append(f"{case.id}: attack objective is not a harmless synthetic instruction")
    tokens = set(_SECRET_TOKEN.findall(blob))
    unexpected = tokens - {SYNTHETIC_SECRET}
    if unexpected:
        issues.append(f"{case.id}: unexpected secret token {sorted(unexpected)}")
    if case.system_instruction and SYNTHETIC_SECRET not in case.system_instruction:
        # The trusted context for this benchmark always carries the synthetic secret.
        issues.append(f"{case.id}: trusted synthetic secret is missing from the system instruction")
    if SYNTHETIC_SECRET not in blob and case.category.value == "synthetic_secret_exfiltration":
        issues.append(f"{case.id}: exfiltration case does not reference the synthetic secret")
    return issues


def validate_dataset(path: Path) -> tuple[list[EvalCase], ValidationResult]:
    display = path.as_posix()
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
        display = relative.as_posix()
    except ValueError:
        display = path.name
    digest = sha256_file(path) if path.is_file() else ""
    try:
        cases = load_cases(path)
    except DatasetError as exc:
        result = ValidationResult(
            path=display,
            valid=False,
            cases=0,
            attack_cases=0,
            benign_controls=0,
            categories=0,
            unique_ids=0,
            schema_version=SCHEMA_VERSION,
            sha256=digest,
            category_counts={},
            errors=[str(exc)],
        )
        return [], result

    errors: list[str] = []
    ids = [case.id for case in cases]
    unique_ids = set(ids)
    if len(unique_ids) != len(ids):
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        errors.append(f"Duplicate case IDs: {', '.join(duplicates)}")
    counts: dict[str, int] = {name: 0 for name in CATEGORY_ORDER}
    for case in cases:
        counts[case.category.value] = counts.get(case.category.value, 0) + 1
        errors.extend(safety_issues(case))
    present = {name: count for name, count in counts.items() if count}
    attack_cases = sum(1 for case in cases if case.is_attack)
    benign = sum(1 for case in cases if not case.is_attack)
    result = ValidationResult(
        path=display,
        valid=not errors,
        cases=len(cases),
        attack_cases=attack_cases,
        benign_controls=benign,
        categories=len(present),
        unique_ids=len(unique_ids),
        schema_version=SCHEMA_VERSION,
        sha256=digest,
        category_counts=present,
        errors=errors,
    )
    return cases, result


def format_validation_report(result: ValidationResult) -> str:
    if not result.valid:
        lines = [f"Dataset invalid: {result.path}"]
        lines.extend(result.errors)
        return "\n".join(lines)
    lines = [
        f"Dataset valid: {result.path}",
        f"Cases: {result.cases}",
        f"Attack cases: {result.attack_cases}",
        f"Benign controls: {result.benign_controls}",
        f"Categories: {result.categories}",
        f"Unique IDs: {result.unique_ids}",
        f"Schema version: {result.schema_version}",
        f"SHA-256: {result.sha256}",
        "Category distribution:",
    ]
    for name in CATEGORY_ORDER:
        if name in result.category_counts:
            lines.append(f"{name}: {result.category_counts[name]}")
    return "\n".join(lines)


def filter_cases(
    cases: list[EvalCase],
    *,
    case_ids: list[str] | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    limit: int | None = None,
) -> list[EvalCase]:
    selected = list(cases)
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if case.id in wanted]
        missing = wanted - {case.id for case in selected}
        if missing:
            raise DatasetError(f"Unknown case IDs: {', '.join(sorted(missing))}")
    if category:
        if category not in CATEGORY_ORDER:
            raise DatasetError(f"Unknown category: {category}")
        selected = [case for case in selected if case.category.value == category]
    if difficulty:
        if difficulty not in {"easy", "medium", "hard"}:
            raise DatasetError(f"Unknown difficulty: {difficulty}")
        selected = [case for case in selected if case.difficulty.value == difficulty]
    if limit is not None:
        if limit < 0:
            raise DatasetError("--limit must be zero or greater")
        selected = selected[:limit]
    return selected
