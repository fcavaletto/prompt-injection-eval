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


# ---- The measurement contract (docs/measurement-contract.md), added 2026-11-17 ----------
#
# ``check`` above is the check the archived pilot ran, kept unchanged so that its recorded
# defects can be reproduced. ``check_contract`` adds what validation showed ``check``
# misses: the turn structure and roles of the pinned template, exact multiplicity of
# schemas, calls and results, type-strict equality, and the generation header.


def strict_equal(a: Any, b: Any) -> bool:
    """Equality that also requires equal JSON types: ``True != 1 != 1.0``."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(strict_equal(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def _turns(rendered: str, profile: Any) -> list[tuple[str, int, int]]:
    import re

    pattern = re.escape(profile.turn_start).replace(re.escape("{role}"), r"(\w+)")
    found = list(re.finditer(pattern, rendered))
    return [
        (m.group(1), m.end(), found[i + 1].start() if i + 1 < len(found) else len(rendered))
        for i, m in enumerate(found)
    ]


def _expected_turns(messages: list[dict[str, Any]], profile: Any) -> list[tuple[str, list[int]]]:
    """(role, message indices) per turn, as the profile lays the messages out."""
    out: list[tuple[str, list[int]]] = []
    for index, message in enumerate(messages):
        role = message["role"]
        if role == "tool":
            if profile.group_tool_messages and out and messages[out[-1][1][-1]]["role"] == "tool":
                out[-1][1].append(index)
                continue
            out.append((profile.tool_role, [index]))
        else:
            out.append((role, [index]))
    return out


def _calls_in(body: str, profile: Any) -> tuple[list[Any], str]:
    """Decoded call objects in an assistant body, and the body with the call blocks removed."""
    calls, rest, at = [], [], 0
    while True:
        start = body.find(profile.call_open, at)
        if start < 0:
            rest.append(body[at:])
            break
        end = body.find(profile.call_close, start + len(profile.call_open))
        if end < 0:
            rest.append(body[at:])
            break
        rest.append(body[at:start])
        inner = body[start + len(profile.call_open) : end]
        try:
            calls.append(json.loads(inner))
        except ValueError:
            calls.append({"__undecodable__": inner[:200]})
        at = end + len(profile.call_close)
    return calls, "".join(rest)


def _schema_defects(body: str, tools: list[dict[str, Any]]) -> list[str]:
    decoded = [value for _, value in json_objects(body)]
    defects = []
    functions = [tool["function"] for tool in tools]
    for tool in tools:
        name = tool["function"]["name"]
        full = sum(strict_equal(v, tool) for v in decoded)
        bare = sum(strict_equal(v, tool["function"]) for v in decoded) - full
        count = full or bare
        if count == 0:
            named = any(
                v.get("name") == name
                or (isinstance(v.get("function"), dict) and v["function"].get("name") == name)
                for v in decoded
            )
            defects.append(
                f"tool_schema_altered:{name}" if named else f"tool_schema_missing:{name}"
            )
        elif count > 1:
            defects.append(f"tool_schema_duplicated:{name}:{count}")
    for value in decoded:
        schema_like = "name" in value and ("description" in value or "parameters" in value)
        if schema_like and not any(strict_equal(value, f) for f in functions):
            defects.append(f"tool_schema_extra:{value.get('name')}")
    return sorted(set(defects))


def check_contract(
    rendered: str | None,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    records: dict[int, serialize.Record] | None,
    fmt: str | dict[int, str],
    payload: str | None = None,
    payload_index: int | None = None,
    profile: str = "qwen3",
) -> list[str]:
    """Defects against the measurement contract for one rendered prompt; [] if none.

    ``fmt`` is one format for every tool message, or a format per tool-message index (for
    a carrier-only intervention). ``records=None`` skips the record items (K5's record
    equality and K7) for stored prompts whose records cannot be recovered; the skip must be
    reported. ``profile`` names the pinned template's layout
    (``contract.PROFILES``): tool results in a user turn are legitimate where the template
    puts them there.
    """
    from prompt_injection_eval.pilot.contract import PROFILES

    if rendered is None:
        return [PROMPT_NOT_RETURNED]
    p = PROFILES[profile]
    formats = (
        fmt
        if isinstance(fmt, dict)
        else {i: fmt for i, m in enumerate(messages) if m["role"] == "tool"}
    )
    defects: list[str] = []

    turns = _turns(rendered, p)
    header = p.turn_start.format(role=turns[0][0]) if turns else ""
    if not turns or not rendered.startswith(header):
        defects.append("text_before_first_turn")
    # The last header must be the assistant's, followed by exactly the rest of the
    # generation header (for Qwen3, the empty think block) and nothing else.
    tail = p.generation_header[len(p.turn_start.format(role="assistant")) :]
    if not (turns and turns[-1][0] == "assistant" and rendered[turns[-1][1] :] == tail):
        defects.append("generation_header_missing")
    body_turns = turns[:-1] if "generation_header_missing" not in defects else turns
    bodies = []
    for position, (role, start, end) in enumerate(body_turns):
        text = rendered[start:end]
        if not text.endswith(p.turn_end):
            defects.append(f"turn_not_closed:{position}:{role}")
            bodies.append((role, text))
        else:
            bodies.append((role, text[: -len(p.turn_end)]))

    expected = _expected_turns(messages, p)
    if [r for r, _ in expected] != [r for r, _ in bodies]:
        defects.append(
            "role_sequence:"
            + ",".join(r for r, _ in expected)
            + "!="
            + ",".join(r for r, _ in bodies)
        )
        return sorted(set(defects))

    for (_, indices), (_, body) in zip(expected, bodies, strict=True):
        first = messages[indices[0]]
        if first["role"] == "system":
            if not body.lstrip().startswith(first["content"].strip()):
                defects.append("system_text_altered")
            defects += _schema_defects(body, tools)
        elif first["role"] == "user":
            if body.strip() != first["content"].strip():
                defects.append(f"user_message_altered:{indices[0]}")
        elif first["role"] == "assistant":
            found, rest = _calls_in(body, p)
            sent = []
            for call in first.get("tool_calls") or []:
                arguments = call["function"]["arguments"]
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                sent.append({"name": call["function"]["name"], "arguments": arguments})
            got = [{"name": c.get("name"), "arguments": c.get("arguments")} for c in found]
            if len(got) != len(sent):
                defects.append(f"call_count:{indices[0]}:{len(got)}!={len(sent)}")
            elif not all(strict_equal(g, s) for g, s in zip(got, sent, strict=True)):
                same_set = sorted(map(json.dumps, got)) == sorted(map(json.dumps, sent))
                kind = "call_order" if same_set else "call_altered"
                defects.append(f"{kind}:{indices[0]}")
            if rest.strip() != (first.get("content") or "").strip():
                defects.append(f"assistant_text_altered:{indices[0]}")
        else:  # a tool turn
            blocks = [
                p.tool_block_open + messages[i]["content"] + p.tool_block_close for i in indices
            ]
            want = p.tool_turn_prefix + p.tool_block_separator.join(blocks)
            for i in indices:
                content = messages[i]["content"]
                if records is None:  # caller cannot supply records: item skipped, not passed
                    continue
                record = records.get(i)
                if record is None or serialize.serialize(record, formats[i]) != content:
                    defects.append(f"result_is_not_the_record:{i}")
                elif formats[i] == "json":
                    try:
                        if not strict_equal(json.loads(content), record):
                            defects.append(f"result_not_decodable:{i}")
                    except ValueError:
                        defects.append(f"result_not_decodable:{i}")
            if body != want:
                count = body.count(p.tool_block_open)
                if count != len(indices):
                    defects.append(f"result_count:{indices[0]}:{count}!={len(indices)}")
                missing = [i for i, b in zip(indices, blocks, strict=True) if b not in body]
                defects += [f"result_missing_or_altered:{i}" for i in missing]
                if not missing and count == len(indices):
                    defects.append(f"result_order_or_layout:{indices[0]}")
            if payload is not None and payload_index in indices and records is not None:
                record = records.get(payload_index) or {}
                if not any(payload.strip() in s for s in _record_strings(record)):
                    defects.append("payload_not_in_record")
                else:
                    block = blocks[indices.index(payload_index)]
                    where = body.find(block)
                    span = block if where >= 0 else ""
                    if not _in_order(payload_in_format(payload, formats[payload_index]), span):
                        defects.append("payload_not_in_prompt")
    if payload is not None and payload_index is None:
        defects.append("payload_has_no_carrier")
    return sorted(set(defects))
