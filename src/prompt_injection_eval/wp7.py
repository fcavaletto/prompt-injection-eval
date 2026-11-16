"""WP7: does a harness deliver a fixed conversation to the model as intended?

A harness under audit is given the common fixture (``data/wp7/fixture.json``) through
its own message-building code, and the result is rendered through the chat template the
published configuration would use. ``check`` then asks, of the rendered prompt:

- **definitions**: every tool name and its description and parameter markers are present;
- **call**: the completed call's tool name and argument marker appear after the user turn;
- **result**: the benign part of the tool result appears after the call;
- **payload**: the attack payload appears after the call, and in which encoding;
- **order**: system, user, call and result markers appear in that order.

Recognized encodings of the payload, so that a semantically valid representation is not
scored as a loss: verbatim; JSON string escaping (with or without ASCII escapes), once
or twice; YAML scalar styles as ``yaml.safe_dump`` writes them (plain, single- or
double-quoted, folded at any width, with or without Unicode escapes); a Python ``repr``.
If none matches exactly, a normalized match (escape sequences decoded, whitespace
collapsed) is reported as ``normalized``, and the payload counts as delivered but altered.

The checker reports what it saw. A failed check is a lead, not a proof of a harness
defect: the audit page explains each one against the harness's intended interface.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "wp7" / "fixture.json"


def load_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    fixture: dict[str, Any] = json.loads(path.read_text())
    for record in fixture["result"]:
        if record["body"] == "<<PAYLOAD>>":
            record["body"] = fixture["payload"]
    return fixture


class _PristineDumper(yaml.Dumper):
    """yaml.Dumper with PyYAML's own representers, immune to global registrations.

    Libraries may change ``yaml.dump`` for a whole process: AgentDojo's
    ``yaml_loader`` registers a quoting representer for ``str`` on ``yaml.Dumper``. The
    checker must not depend on what else has been imported.
    """

    yaml_representers = yaml.representer.Representer.yaml_representers.copy()
    yaml_multi_representers = yaml.representer.Representer.yaml_multi_representers.copy()


class _PristineSafeDumper(yaml.SafeDumper):
    yaml_representers = yaml.representer.SafeRepresenter.yaml_representers.copy()
    yaml_multi_representers = yaml.representer.SafeRepresenter.yaml_multi_representers.copy()


def _yaml_forms(text: str) -> list[str]:
    """The payload as a YAML scalar, as ``yaml.dump``/``safe_dump`` write it in a mapping,
    in a list of mappings, and one level deeper, at two widths, with and without
    Unicode escapes. The scalar is cut out between its key and a sentinel key."""
    contexts = (
        lambda v: {"k": v, "z": "SENTINEL"},
        lambda v: [{"k": v, "z": "SENTINEL"}],
        lambda v: {"a": [{"k": v, "z": "SENTINEL"}]},
    )
    forms = []
    for dumper in (_PristineSafeDumper, _PristineDumper):
        for allow_unicode in (False, True):
            for width in (80, 8192):
                for context in contexts:
                    dumped = yaml.dump(
                        context(text),
                        Dumper=dumper,
                        allow_unicode=allow_unicode,
                        width=width,
                        default_flow_style=False,
                    )
                    start = dumped.index("k: ") + len("k: ")
                    end = dumped.index("z: SENTINEL")
                    form = dumped[start:end].rstrip(" \n")
                    if form not in forms:
                        forms.append(form)
    return forms


def payload_forms(payload: str) -> dict[str, str]:
    """Exact encodings of the payload that a harness may legitimately produce."""
    once = json.dumps(payload, ensure_ascii=False)[1:-1]
    once_ascii = json.dumps(payload)[1:-1]
    forms = {
        "verbatim": payload,
        "json-escaped": once,
        "json-escaped-ascii": once_ascii,
        "json-escaped-twice": json.dumps(once, ensure_ascii=False)[1:-1],
        "json-escaped-twice-ascii": json.dumps(once_ascii)[1:-1],
        "python-repr": repr(payload)[1:-1],
    }
    for i, form in enumerate(_yaml_forms(payload)):
        forms[f"yaml-{i}"] = form
        # A YAML-formatted result carried inside a JSON string (e.g. {"result": "..."}).
        forms[f"yaml-{i}-json-escaped"] = json.dumps(form, ensure_ascii=False)[1:-1]
        forms[f"yaml-{i}-json-escaped-ascii"] = json.dumps(form)[1:-1]
        # ... and that JSON text JSON-encoded once more (e.g. by a template's tojson).
        once_ascii = json.dumps(form)[1:-1]
        forms[f"yaml-{i}-json-escaped-twice-ascii"] = json.dumps(once_ascii)[1:-1]
    return forms


_ESCAPES = re.compile(r"\\u([0-9a-fA-F]{4})|\\(.)")


_YAML_CONTINUATION = re.compile(r"\\\n[ \t]*(\\ )?")


def _normalize(text: str) -> str:
    """Join YAML double-quoted line continuations, decode common escapes repeatedly, drop
    quote characters, collapse whitespace."""
    for _ in range(3):
        text = _YAML_CONTINUATION.sub(lambda m: " " if m.group(1) else "", text)
        text = _ESCAPES.sub(
            lambda m: (
                chr(int(m.group(1), 16))
                if m.group(1)
                else {"n": " ", "t": " ", "r": " "}.get(m.group(2), m.group(2))
            ),
            text,
        )
    text = text.replace('"', "").replace("'", "")
    return re.sub(r"\s+", " ", text).strip()


def find_payload(prompt: str, payload: str, start: int = 0) -> tuple[str | None, int]:
    """The encoding in which the payload appears at or after ``start``, and where."""
    for name, form in payload_forms(payload).items():
        at = prompt.find(form, start)
        if at >= 0:
            return name, at
    if _normalize(payload) in _normalize(prompt[start:]):
        marker_at = prompt.find("MARK-PAYLOAD", start)
        return "normalized", marker_at
    return None, -1


def _first(prompt: str, needle: str, start: int = 0) -> int:
    return prompt.find(needle, start)


@dataclass
class Check:
    definitions: bool
    parameters: bool
    call: bool
    result: bool
    payload: bool
    payload_form: str | None
    order: bool
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            (self.definitions, self.parameters, self.call, self.result, self.payload, self.order)
        )

    def row(self) -> dict[str, Any]:
        out = asdict(self)
        out["passed"] = self.passed
        return out


def check(prompt: str, fixture: dict[str, Any] | None = None) -> Check:
    fx = fixture or load_fixture()
    marks = fx["markers"]
    missing: list[str] = []
    notes: list[str] = []
    for tool in fx["tools"]:
        if tool["name"] not in prompt:
            missing.append(f"tool name {tool['name']}")
    for marker in marks["descriptions"]:
        if marker not in prompt:
            missing.append(f"description {marker}")
    definitions = not any(m.startswith(("tool name", "description")) for m in missing)
    params_missing = [p for p in marks["parameters"] if p not in prompt]
    missing += [f"parameter {p}" for p in params_missing]
    user_at = _first(prompt, marks["user"])
    sys_at = _first(prompt, marks["system"])
    call_at = _first(prompt, marks["call_argument"], max(user_at, 0))
    name_ok = fx["call"]["name"] in prompt[max(user_at, 0) :] if user_at >= 0 else False
    call = user_at >= 0 and call_at >= 0 and name_ok
    if not call:
        missing.append("completed call after the user turn")
    result_at = _first(prompt, marks["result"], max(call_at, 0)) if call else -1
    result = result_at >= 0
    if not result:
        missing.append("tool result after the call")
    form, payload_at = find_payload(prompt, fx["payload"], max(call_at, 0) if call else 0)
    payload = form is not None
    if not payload:
        missing.append("payload")
    elif form == "normalized":
        notes.append("payload recoverable only after normalization: delivered but altered")
    order = all(a >= 0 for a in (sys_at, user_at, call_at, result_at)) and (
        sys_at < user_at < call_at < result_at
    )
    if sys_at < 0:
        missing.append("system text")
    return Check(
        definitions=definitions,
        parameters=not params_missing,
        call=call,
        result=result,
        payload=payload,
        payload_form=form,
        order=order,
        missing=missing,
        notes=notes,
    )


def missing_outcome_bounds(planned: int, successes: int, missing: int) -> dict[str, Any]:
    """Conditional bounds on a success rate when some outcomes are missing. Not a CI.

    ``planned`` episodes (N), of which ``missing`` (M) have no trustworthy outcome and
    ``successes`` (S) are observed successes among the rest. Holding every other outcome
    fixed, the full-benchmark rate lies between S/N (every missing episode a failure)
    and (S + M)/N (every one a success). The complete-case estimate S/(N - M) drops the
    missing episodes; it lies inside the bounds, and it is unbiased only if the missing
    episodes would have succeeded at the same rate as the others. When missingness
    depends on request length, as suspected here, that need not hold.
    """
    if not 0 <= missing <= planned or not 0 <= successes <= planned - missing:
        raise ValueError("Need 0 <= M <= N and 0 <= S <= N - M.")
    return {
        "planned": planned,
        "observed_successes": successes,
        "missing": missing,
        "lower_bound_pct": 100 * successes / planned,
        "upper_bound_pct": 100 * (successes + missing) / planned,
        "complete_case_pct": 100 * successes / (planned - missing) if planned > missing else None,
        "kind": (
            "conditional missing-outcome bounds (other outcomes held fixed); "
            "not a confidence interval"
        ),
    }
