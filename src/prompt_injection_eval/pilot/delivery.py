"""Was the conversation delivered to the model as intended?

The check reads the prompt the server returned and compares it with what the harness
sent. It decodes JSON objects out of the prompt and compares them for equality with the
tool schemas, the earlier calls and (in the JSON condition) the tool results, so it tests
that these are usable and not only that some marker survived.

A defect makes the row an invalid measurement. It is never read as a failed attack.
"""

from __future__ import annotations

import json
from typing import Any

from prompt_injection_eval.pilot import serialize

PROMPT_NOT_RETURNED = "prompt_not_returned"
_DECODER = json.JSONDecoder()


def json_objects(text: str) -> list[tuple[int, dict[str, Any]]]:
    """Every JSON object that can be decoded starting at a ``{`` in ``text``."""
    found = []
    at = text.find("{")
    while at >= 0:
        try:
            value, _end = _DECODER.raw_decode(text, at)
        except ValueError:
            value = None
        if isinstance(value, dict):
            found.append((at, value))
        at = text.find("{", at + 1)
    return found


def payload_in_format(payload: str, fmt: str) -> list[str]:
    """The pieces of ``payload`` that must appear, in order, in a prompt of this format."""
    stripped = payload.strip()
    if fmt == "json":
        return [json.dumps(stripped, ensure_ascii=False)[1:-1]]
    return [line.strip() for line in stripped.split("\n") if line.strip()]


def _in_order(pieces: list[str], text: str, start: int = 0) -> bool:
    at = start
    for piece in pieces:
        at = text.find(piece, at)
        if at < 0:
            return False
        at += len(piece)
    return True


def _record_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [s for item in value.values() for s in _record_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _record_strings(item)]
    return [value] if isinstance(value, str) else []


def check(
    rendered: str | None,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    records: dict[int, serialize.Record],
    fmt: str,
    payload: str | None = None,
    payload_index: int | None = None,
) -> list[str]:
    """Defects in one rendered prompt. An empty list means delivery was verified.

    ``messages`` is the wire conversation that was sent, ``records`` maps the index of
    each tool message to its canonical record, and ``payload_index`` is the index of the
    tool message that must carry ``payload``.
    """
    if rendered is None:
        return [PROMPT_NOT_RETURNED]
    defects: list[str] = []
    objects = json_objects(rendered)
    decoded = [value for _, value in objects]

    for tool in tools:
        name = tool["function"]["name"]
        if any(value == tool or value == tool["function"] for value in decoded):
            continue
        # A schema-shaped object with this name that is not equal to what was sent.
        named = any(
            (value.get("name") == name and "description" in value)
            or (isinstance(value.get("function"), dict) and value["function"].get("name") == name)
            for value in decoded
        )
        defects.append(f"tool_schema_altered:{name}" if named else f"tool_schema_missing:{name}")

    cursor = 0
    for index, message in enumerate(messages):
        role = message["role"]
        if role in ("system", "user"):
            text = message["content"].strip()
            at = rendered.find(text, cursor) if text else cursor
            if at < 0:
                kind = "out_of_order" if text in rendered else "missing"
                defects.append(f"{role}_message_{kind}:{index}")
            else:
                cursor = at + len(text)
        elif role == "assistant":
            for call in message.get("tool_calls") or []:
                name = call["function"]["name"]
                arguments = call["function"]["arguments"]
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                hit = next(
                    (
                        position
                        for position, value in objects
                        if position >= cursor
                        and value.get("name") == name
                        and arguments in (value.get("arguments"), value.get("parameters"))
                    ),
                    None,
                )
                if hit is None:
                    anywhere = any(
                        value.get("name") == name
                        and ("arguments" in value or "parameters" in value)
                        and "description" not in value
                        for value in decoded
                    )
                    defects.append(
                        f"call_altered_or_out_of_order:{index}:{name}"
                        if anywhere
                        else f"call_missing:{index}:{name}"
                    )
                else:
                    cursor = hit + 1
        elif role == "tool":
            content = message["content"]
            record = records.get(index)
            if not isinstance(content, str) or record is None:
                defects.append(f"result_not_a_serialized_record:{index}")
                continue
            if serialize.serialize(record, fmt) != content:
                defects.append(f"result_is_not_the_record:{index}")
            body = content.strip()
            at = rendered.find(body, cursor)
            if at < 0:
                escaped = json.dumps(body, ensure_ascii=False)[1:-1]
                ascii_escaped = json.dumps(body)[1:-1]
                if body in rendered:
                    defects.append(f"result_out_of_order:{index}")
                elif escaped != body and (escaped in rendered or ascii_escaped in rendered):
                    defects.append(f"result_reencoded:{index}")
                else:
                    defects.append(f"result_missing:{index}")
                continue
            if fmt == "json" and not any(p == at and value == record for p, value in objects):
                defects.append(f"result_not_decodable:{index}")
            if index == payload_index and payload is not None:
                pieces = payload_in_format(payload, fmt)
                if not any(payload.strip() in s for s in _record_strings(record)):
                    defects.append("payload_not_in_record")
                elif not _in_order(pieces, rendered, at):
                    defects.append("payload_not_in_prompt")
            cursor = at + len(body)
    if payload is not None and payload_index is None:
        defects.append("payload_has_no_carrier")
    return defects


def call_like_text(text: str | None, tool_names: list[str]) -> bool:
    """Whether a reply holds something shaped like a tool call that the server left as text."""
    if not text:
        return False
    if "<tool_call>" in text or "<|tool_call|>" in text:
        return True
    return any(
        value.get("name") in tool_names and ("arguments" in value or "parameters" in value)
        for _, value in json_objects(text)
    )
