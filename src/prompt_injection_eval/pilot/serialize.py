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


QUOTED = "quoted"  # Stage 1 only (docs/protocol-stage1.md); not a pilot format


def serialize(record: Record, fmt: str) -> str:
    if fmt == "json":
        return to_json(record)
    if fmt == "text":
        return to_text(record)
    if fmt == QUOTED:
        return to_quoted(record)
    raise PilotError(f"Unknown format {fmt!r}; expected one of {(*FORMATS, QUOTED)}.")


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


# ---- Labelled text with JSON-quoted string values (Stage 1) ------------------------------
#
# The same labels, indentation, scalar spellings and empty marker as ``to_text``. The only
# change: every string value is written as a JSON string literal (quoted, with ``"``, ``\``
# and control characters escaped, so a newline is the two characters ``\n``). A string
# therefore always occupies one line and always starts with ``"``, and it can no longer be
# read as a nested field or list item. The record can be read back without its shape,
# except that an empty object and an empty list both print as ``(empty)``.


def _quoted_emit(head: str, value: Any, depth: int, lines: list[str]) -> None:
    pad = INDENT * depth
    if isinstance(value, dict | list):
        if not value:
            lines.append(f"{pad}{head} {EMPTY}")
            return
        lines.append(f"{pad}{head}")
        items = value.items() if isinstance(value, dict) else (("-", v) for v in value)
        for key, item in items:
            _quoted_emit(f"{key}:" if isinstance(value, dict) else "-", item, depth + 1, lines)
    elif isinstance(value, str):
        lines.append(f"{pad}{head} {json.dumps(value, ensure_ascii=False)}")
    else:
        lines.append(f"{pad}{head} {_literal(value)}")


def to_quoted(record: Record) -> str:
    if not record:
        return EMPTY
    lines: list[str] = []
    for key, item in record.items():
        _quoted_emit(f"{key}:", item, 0, lines)
    return "\n".join(lines)


def _quoted_scalar(rest: str) -> Any:
    if rest.startswith('"'):
        return json.loads(rest)
    if rest == "none":
        return None
    if rest in ("true", "false"):
        return rest == "true"
    if rest == EMPTY:
        return {}
    value = json.loads(rest)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise PilotError(f"Not a scalar: {rest[:80]!r}")
    return value


def from_quoted(text: str) -> Record:
    """Read ``to_quoted`` output back with no shape given. ``(empty)`` reads as ``{}``."""
    if text == EMPTY:
        return {}
    lines = text.split("\n")
    at = 0

    def block(depth: int) -> Any:
        nonlocal at
        pad = INDENT * depth
        first = lines[at][len(pad) :]
        is_list = first == "-" or first.startswith("- ")
        out: Any = [] if is_list else {}
        while at < len(lines) and lines[at].startswith(pad) and not lines[at].startswith(pad + " "):
            line = lines[at][len(pad) :]
            if is_list:
                if not (line == "-" or line.startswith("- ")):
                    raise PilotError(f"Line {at + 1}: expected a list item.")
                key, rest = None, line[2:] if line != "-" else None
            else:
                key, sep, rest_ = line.partition(":")
                if not sep:
                    raise PilotError(f"Line {at + 1}: expected a label.")
                rest = rest_[1:] if rest_.startswith(" ") else (None if rest_ == "" else rest_)
            at += 1
            value = block(depth + 1) if rest is None else _quoted_scalar(rest)
            if is_list:
                out.append(value)
            else:
                out[key] = value
        return out

    record = block(0)
    if at != len(lines) or not isinstance(record, dict):
        raise PilotError(f"Unread text from line {at + 1}.")
    return record
