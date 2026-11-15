"""The canonical record of a tool result and its two representations.

``canonical`` turns whatever a tool returned into one JSON-compatible object. ``to_json``
and ``to_text`` are functions of that object and nothing else. ``from_text`` reads a
record back from free text when it is told the record's shape, which is the precise sense
in which the two representations carry the same information: free text drops type marks
(the string "5" and the number 5 look alike) and nothing else.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic_core import to_jsonable_python

from prompt_injection_eval.pilot import FORMATS, PilotError

INDENT = "  "
EMPTY = "(empty)"
Record = dict[str, Any]


def canonical(result: Any) -> Record:
    """The record for a tool's return value. Always an object."""
    value = to_jsonable_python(result)
    if not isinstance(value, dict):
        value = {"result": value}
    return _checked(value)


def error_record(message: str) -> Record:
    return {"error": message}


def _checked(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str) or "\n" in key or key != key.strip() or not key:
                raise PilotError(f"Tool result key cannot be represented as a label: {key!r}")
            out[key] = _checked(item)
        return out
    if isinstance(value, list | tuple):
        return [_checked(item) for item in value]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    raise PilotError(f"Tool result value is not JSON-compatible: {type(value).__name__}")


def to_json(record: Record) -> str:
    """One JSON object on one line. Never a JSON string literal."""
    return json.dumps(record, ensure_ascii=False)


def serialize(record: Record, fmt: str) -> str:
    if fmt == "json":
        return to_json(record)
    if fmt == "text":
        return to_text(record)
    raise PilotError(f"Unknown format {fmt!r}; expected one of {FORMATS}.")


def _literal(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value)


def _emit(head: str, value: Any, depth: int, lines: list[str]) -> None:
    """Append ``value`` under the label ``head`` ("key:" or "-") at ``depth``."""
    pad = INDENT * depth
    if isinstance(value, dict | list):
        if not value:
            lines.append(f"{pad}{head} {EMPTY}")
            return
        lines.append(f"{pad}{head}")
        _emit_children(value, depth + 1, lines)
    elif isinstance(value, str):
        if "\n" in value or value == "":
            lines.append(f"{pad}{head}")
            if value:
                lines.extend(f"{pad}{INDENT}{line}" for line in value.split("\n"))
        else:
            lines.append(f"{pad}{head} {value}")
    else:
        lines.append(f"{pad}{head} {_literal(value)}")


def _emit_children(value: dict[str, Any] | list[Any], depth: int, lines: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _emit(f"{key}:", item, depth, lines)
    else:
        for item in value:
            _emit("-", item, depth, lines)


def to_text(record: Record) -> str:
    """Labelled lines. Strings are written raw: no quotes, no escapes."""
    if not record:
        return EMPTY
    lines: list[str] = []
    _emit_children(record, 0, lines)
    return "\n".join(lines)


def shape(value: Any) -> Any:
    """The record with every leaf replaced by the name of its type."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(item) for item in value]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


class _Reader:
    def __init__(self, text: str) -> None:
        self.lines = text.split("\n")
        self.at = 0

    def take(self, prefix: str) -> str | None:
        """The rest of the current line after ``prefix``; None if nothing follows it."""
        if self.at >= len(self.lines):
            raise PilotError(f"Text ended where {prefix!r} was expected.")
        line = self.lines[self.at]
        if line == prefix:
            self.at += 1
            return None
        if not line.startswith(prefix + " "):
            raise PilotError(f"Line {self.at + 1} does not start with {prefix!r}: {line[:80]!r}")
        self.at += 1
        return line[len(prefix) + 1 :]

    def block(self, prefix: str) -> str:
        collected = []
        while self.at < len(self.lines) and self.lines[self.at].startswith(prefix):
            collected.append(self.lines[self.at][len(prefix) :])
            self.at += 1
        return "\n".join(collected)


def _read(reader: _Reader, head: str, kind: Any, depth: int) -> Any:
    pad = INDENT * depth
    rest = reader.take(f"{pad}{head}")
    if isinstance(kind, dict | list):
        if not kind:
            if rest != EMPTY:
                raise PilotError(f"Expected {EMPTY} after {head!r}.")
            return {} if isinstance(kind, dict) else []
        if rest is not None:
            raise PilotError(f"Unexpected text after {head!r}: {rest[:80]!r}")
        return _read_children(reader, kind, depth + 1)
    if kind == "str":
        return rest if rest is not None else reader.block(pad + INDENT)
    if rest is None:
        raise PilotError(f"Missing value after {head!r}.")
    if kind == "null":
        return None
    if kind == "bool":
        return rest == "true"
    if kind == "int":
        return int(rest)
    return float(rest)


def _read_children(reader: _Reader, kind: dict[str, Any] | list[Any], depth: int) -> Any:
    if isinstance(kind, dict):
        return {key: _read(reader, f"{key}:", item, depth) for key, item in kind.items()}
    return [_read(reader, "-", item, depth) for item in kind]


def from_text(text: str, record_shape: Record) -> Record:
    """Read a record back from ``to_text`` output, given the record's shape."""
    if not record_shape:
        if text != EMPTY:
            raise PilotError("Expected an empty record.")
        return {}
    reader = _Reader(text)
    record = _read_children(reader, record_shape, 0)
    if reader.at != len(reader.lines):
        raise PilotError(f"Unread text from line {reader.at + 1}.")
    return record


def round_trips(record: Record) -> bool:
    """Both representations decode back to exactly this record."""
    return (
        json.loads(to_json(record)) == record
        and from_text(to_text(record), shape(record)) == record
    )
