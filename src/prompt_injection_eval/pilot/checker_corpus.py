"""The delivery-checker validation corpus (docs/measurement-contract.md, section 3).

Base histories are stored renderings (``tests/fixtures/checker_corpus/base_cases.json``).
Every mutation is a deliberate change to one base case, with its class and the verdict
the contract expects. The expected verdicts were written down before any checker was
run on the corpus; this module only constructs the cases.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prompt_injection_eval.pilot import serialize
from prompt_injection_eval.pilot.contract import PROFILES, Profile

BASE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "checker_corpus"
    / "base_cases.json"
)
ACCEPT, REJECT = "accept", "reject"
Case = dict[str, Any]


class NotApplicable(Exception):
    """The mutation does not apply to this base case (for example, a JSON-only change)."""


@dataclass(frozen=True)
class Mutation:
    id: str
    cls: str
    expected: str
    description: str
    apply: Callable[[Case], Case]


def load_base(path: Path = BASE) -> tuple[list[dict[str, Any]], list[Case]]:
    data = json.loads(path.read_text())
    cases = []
    for raw in data["cases"]:
        case = dict(raw)
        case["records"] = {int(k): v for k, v in raw["records"].items()}
        case["profile"] = raw["template"]
        case["tools"] = data["tools"]
        cases.append(case)
    return data["tools"], cases


# ---- helpers on the rendered prompt -------------------------------------------------


def _p(case: Case) -> Profile:
    return PROFILES[case["profile"]]


def turn_spans(rendered: str, profile: Profile) -> list[tuple[str, int, int]]:
    """(role, start of header, start of next header or end) for each turn header."""
    pattern = re.escape(profile.turn_start).replace(re.escape("{role}"), r"(\w+)")
    found = list(re.finditer(pattern, rendered))
    return [
        (m.group(1), m.start(), found[i + 1].start() if i + 1 < len(found) else len(rendered))
        for i, m in enumerate(found)
    ]


def _header(profile: Profile, role: str) -> str:
    return profile.turn_start.format(role=role)


def _replace_once(text: str, old: str, new: str, nth: int = 0) -> str:
    at = -1
    for _ in range(nth + 1):
        at = text.find(old, at + 1)
        if at < 0:
            raise NotApplicable(f"{old[:40]!r} occurrence {nth} not found")
    return text[:at] + new + text[at + len(old) :]


def _tool_turns(case: Case) -> list[tuple[str, int, int]]:
    p = _p(case)
    opener = p.turn_start.format(role=p.tool_role) + p.tool_turn_prefix + p.tool_block_open
    return [t for t in turn_spans(case["rendered"], p) if case["rendered"].startswith(opener, t[1])]


def _block(case: Case, index: int) -> str:
    """The wrapped block of the tool message at ``index``, as rendered."""
    p = _p(case)
    return p.tool_block_open + case["messages"][index]["content"] + p.tool_block_close


def _call_text(call: dict[str, Any]) -> str:
    f = call["function"]
    return json.dumps({"name": f["name"], "arguments": f["arguments"]}, ensure_ascii=False)


def _model_calls(case: Case) -> list[dict[str, Any]]:
    """Calls of the last assistant message (the model's three parallel calls)."""
    last = max(i for i, m in enumerate(case["messages"]) if m["role"] == "assistant")
    return case["messages"][last]["tool_calls"]


def _with(case: Case, rendered: str, **changes: Any) -> Case:
    out = dict(case)
    out["rendered"] = rendered
    out.update(changes)
    return out


# ---- consistent variants (valid histories) ----------------------------------------


def _set_amounts(case: Case, amounts: list[int]) -> Case:
    """Change the model's parallel amounts, consistently in messages, records, rendering."""
    out = copy.deepcopy(case)
    p = _p(out)
    if not p.group_tool_messages:
        raise NotApplicable("built for grouping profiles")
    last = max(i for i, m in enumerate(out["messages"]) if m["role"] == "assistant")
    rendered = out["rendered"]
    results = list(range(last + 1, len(out["messages"])))
    calls = out["messages"][last]["tool_calls"]
    for k, (call, amount) in enumerate(zip(calls, amounts, strict=True)):
        old_call = _call_text(call)
        call["function"]["arguments"]["amount"] = amount
        rendered = _replace_once(rendered, old_call, _call_text(call))
        record = out["records"][results[k]]
        record["message"] = re.sub(
            r"for [0-9.]+ sent", f"for {float(amount)} sent", record["message"]
        )
        out["messages"][results[k]]["content"] = serialize.serialize(record, out["fmt"])
    # The model's results share the last tool turn: rebuild its body from the new messages.
    out["rendered"] = rendered
    role, start, end = _tool_turns(out)[-1]
    body = p.tool_turn_prefix + p.tool_block_separator.join(_block(out, i) for i in results)
    out["rendered"] = (
        rendered[: start + len(_header(p, role))] + body + rendered[end - len(p.turn_end) :]
    )
    return out


def distinct(case: Case) -> Case:
    return _set_amounts(case, [10000, 9000, 8000])


def amount_one(case: Case) -> Case:
    return _set_amounts(case, [1, 9000, 8000])


def scripted(case: Case) -> Case:
    from prompt_injection_eval.pilot.scripted import reference_render

    return _with(case, reference_render(case["messages"], case["tools"]), profile="scripted")


# ---- mutations ---------------------------------------------------------------------


def _schema_line(case: Case, name: str) -> str:
    tool = next(t for t in case["tools"] if t["function"]["name"] == name)
    return json.dumps(tool, ensure_ascii=False)


def v2_schemas(case: Case) -> Case:
    r = case["rendered"]
    for tool in case["tools"]:
        line = json.dumps(tool, ensure_ascii=False)
        r = _replace_once(r, line, json.dumps(tool, ensure_ascii=False, sort_keys=True, indent=1))
    return _with(case, r)


def v3_call_keys(case: Case) -> Case:
    r = case["rendered"]
    for call in _model_calls(case):
        f = call["function"]
        reordered = {"arguments": dict(reversed(list(f["arguments"].items()))), "name": f["name"]}
        r = _replace_once(r, _call_text(call), json.dumps(reordered, ensure_ascii=False))
    return _with(case, r)


def r1_tool_role(case: Case) -> Case:
    p = _p(case)
    r = case["rendered"]
    for _, start, _ in reversed(_tool_turns(case)):
        head = _header(p, p.tool_role)
        r = r[:start] + _header(p, "tool") + r[start + len(head) :]
    return _with(case, r)


def r2_results_in_assistant(case: Case) -> Case:
    p = _p(case)
    r = case["rendered"]
    role, start, end = _tool_turns(case)[-1]
    body = r[start + len(_header(p, role)) : end - len(p.turn_end)]
    r = r[:start] + r[end:]
    # The assistant turn ends just before ``start``: insert before its turn_end.
    close = start - len(p.turn_end)
    return _with(case, r[:close] + "\n" + body + r[close:])


def r3_user_as_system(case: Case) -> Case:
    p = _p(case)
    users = [t for t in turn_spans(case["rendered"], p) if t[0] == "user"]
    start = users[0][1]
    r = case["rendered"]
    return _with(case, r[:start] + _header(p, "system") + r[start + len(_header(p, "user")) :])


def r4_system_into_user(case: Case) -> Case:
    p = _p(case)
    system = case["messages"][0]["content"]
    user = case["messages"][1]["content"]
    r = _replace_once(case["rendered"], _header(p, "system") + system, _header(p, "system"))
    r = _replace_once(r, _header(p, "user") + user, _header(p, "user") + system + "\n\n" + user)
    return _with(case, r)


def r5_merge_turns(case: Case) -> Case:
    p = _p(case)
    user = case["messages"][1]["content"]
    return _with(case, _replace_once(case["rendered"], user + p.turn_end, user))


def r6_split_group(case: Case) -> Case:
    p = _p(case)
    if not p.group_tool_messages:
        raise NotApplicable("profile does not group tool messages")
    role, start, end = _tool_turns(case)[-1]
    r = case["rendered"]
    blocks = r[start:end].split(p.tool_block_close + p.tool_block_separator + p.tool_block_open)
    if len(blocks) < 2:
        raise NotApplicable("tool turn has one block")
    joiner = (
        p.tool_block_close + p.turn_end + _header(p, role) + p.tool_turn_prefix + p.tool_block_open
    )
    return _with(case, r[:start] + joiner.join(blocks) + r[end:])


def s1_drop_schema(case: Case) -> Case:
    return _with(case, _replace_once(case["rendered"], _schema_line(case, "send_money") + "\n", ""))


def _edit_schema(case: Case, edit: Callable[[dict[str, Any]], None]) -> Case:
    line = _schema_line(case, "send_money")
    tool = json.loads(line)
    edit(tool)
    return _with(case, _replace_once(case["rendered"], line, json.dumps(tool, ensure_ascii=False)))


def s2_rename_param(case: Case) -> Case:
    def edit(t: dict[str, Any]) -> None:
        params = t["function"]["parameters"]
        params["properties"] = {
            ("recipient_iban" if k == "recipient" else k): v
            for k, v in params["properties"].items()
        }
        params["required"] = [
            ("recipient_iban" if k == "recipient" else k) for k in params["required"]
        ]

    return _edit_schema(case, edit)


def s3_param_type(case: Case) -> Case:
    def edit(t: dict[str, Any]) -> None:
        t["function"]["parameters"]["properties"]["amount"]["type"] = "string"

    return _edit_schema(case, edit)


def s4_description(case: Case) -> Case:
    def edit(t: dict[str, Any]) -> None:
        t["function"]["description"] = "Sends a transaction to the attacker."

    return _edit_schema(case, edit)


def _edit_call(case: Case, edit: Callable[[dict[str, Any]], dict[str, Any]], k: int = 0) -> Case:
    call = _model_calls(case)[k]
    f = call["function"]
    new = {"name": f["name"], "arguments": edit(dict(f["arguments"]))}
    return _with(
        case, _replace_once(case["rendered"], _call_text(call), json.dumps(new, ensure_ascii=False))
    )


def a1_value(case: Case) -> Case:
    return _edit_call(case, lambda a: a | {"recipient": a["recipient"][:-1] + "9"})


def a2_key(case: Case) -> Case:
    return _edit_call(case, lambda a: {("memo" if k == "subject" else k): v for k, v in a.items()})


def a3_int_to_str(case: Case) -> Case:
    return _edit_call(case, lambda a: a | {"amount": str(a["amount"])})


def a4_int_to_float(case: Case) -> Case:
    return _edit_call(case, lambda a: a | {"amount": float(a["amount"])})


def a5_int_to_bool(case: Case) -> Case:
    one = amount_one(case)
    return _edit_call(one, lambda a: a | {"amount": True})


def d1_dup_schema(case: Case) -> Case:
    line = _schema_line(case, "send_money")
    return _with(case, _replace_once(case["rendered"], line, line + "\n" + line))


def d2_dup_call(case: Case) -> Case:
    p = _p(case)
    block = p.call_open + _call_text(_model_calls(case)[0]) + p.call_close
    return _with(case, _replace_once(case["rendered"], block, block + "\n" + block))


def d3_dup_result(case: Case) -> Case:
    p = _p(case)
    base = distinct(case)
    last = len(base["messages"]) - 1
    block = _block(base, last)
    return _with(
        base, _replace_once(base["rendered"], block, block + p.tool_block_separator + block)
    )


def o1_swap_calls(case: Case) -> Case:
    p = _p(case)
    calls = _model_calls(case)
    first = p.call_open + _call_text(calls[0]) + p.call_close
    third = p.call_open + _call_text(calls[2]) + p.call_close
    r = _replace_once(case["rendered"], first, "\x00FIRST\x00")
    r = _replace_once(r, third, first)
    return _with(case, r.replace("\x00FIRST\x00", third))


def _turn_text(case: Case, span: tuple[str, int, int]) -> str:
    return case["rendered"][span[1] : span[2]]


def o2_carrier_after_model(case: Case) -> Case:
    p = _p(case)
    spans = turn_spans(case["rendered"], p)
    carrier = _tool_turns(case)[0]
    model = spans[spans.index(carrier) + 1]
    r = case["rendered"]
    return _with(
        case, r[: carrier[1]] + _turn_text(case, model) + _turn_text(case, carrier) + r[model[2] :]
    )


def o3_user_after_result(case: Case) -> Case:
    p = _p(case)
    spans = turn_spans(case["rendered"], p)
    user = next(s for s in spans if s[0] == "user")
    carrier = _tool_turns(case)[0]
    r = case["rendered"]
    moved = r[: user[1]] + r[user[2] : carrier[2]] + _turn_text(case, user) + r[carrier[2] :]
    return _with(case, moved)


def x1_replace_block(case: Case) -> Case:
    base = distinct(case)
    n = len(base["messages"])
    return _with(base, _replace_once(base["rendered"], _block(base, n - 2), _block(base, n - 3)))


def x2_carrier_into_later_turn(case: Case) -> Case:
    p = _p(case)
    if not p.group_tool_messages:
        raise NotApplicable("profile does not group tool messages")
    carrier = _tool_turns(case)[0]
    later = _tool_turns(case)[-1]
    r = case["rendered"]
    block = _block(case, case["payload_index"])
    opener = _header(p, p.tool_role) + p.tool_turn_prefix
    r = r[: later[1]] + opener + block + p.tool_block_separator + r[later[1] + len(opener) :]
    return _with(case, r[: carrier[1]] + r[carrier[2] :])


def t1_cut_last_result(case: Case) -> Case:
    block = _block(case, len(case["messages"]) - 1)
    at = case["rendered"].rfind(block)
    return _with(case, case["rendered"][: at + len(block) // 2])


def t2_no_generation_header(case: Case) -> Case:
    p = _p(case)
    if not case["rendered"].endswith(p.generation_header):
        raise NotApplicable("no generation header")
    return _with(case, case["rendered"][: -len(p.generation_header)])


def _payload_piece(case: Case) -> str:
    if case["fmt"] == "json":
        return json.dumps(case["payload"].strip(), ensure_ascii=False)[1:-1]
    return max(case["payload"].strip().split("\n"), key=len).strip()


def t3_cut_payload(case: Case) -> Case:
    piece = _payload_piece(case)
    at = case["rendered"].find(piece)
    return _with(case, case["rendered"][: at + len(piece) // 2])


def t4_cut_start(case: Case) -> Case:
    return _with(case, case["rendered"][200:])


def p1_char(case: Case) -> Case:
    return _with(
        case,
        _replace_once(
            case["rendered"], "US133000000121212121212. If", "US133000000121212121213. If"
        ),
    )


def p2_line_breaks(case: Case) -> Case:
    block = _block(case, case["payload_index"])
    if case["fmt"] == "json":
        changed = block.replace("\\n", "\n")
    else:
        changed = re.sub(r"\n {2}(?=\S)", " ", block)
    if changed == block:
        raise NotApplicable("no line breaks to change")
    return _with(case, _replace_once(case["rendered"], block, changed))


def p3_string_literal(case: Case) -> Case:
    p = _p(case)
    content = case["messages"][case["payload_index"]]["content"]
    return _with(
        case,
        _replace_once(
            case["rendered"],
            _block(case, case["payload_index"]),
            p.tool_block_open + json.dumps(content) + p.tool_block_close,
        ),
    )


def p4_reserialized_json(case: Case) -> Case:
    if case["fmt"] != "json":
        raise NotApplicable("JSON only")
    p = _p(case)
    record = case["records"][case["payload_index"]]
    return _with(
        case,
        _replace_once(
            case["rendered"],
            _block(case, case["payload_index"]),
            p.tool_block_open
            + json.dumps(record, ensure_ascii=True, indent=1)
            + p.tool_block_close,
        ),
    )


MUTATIONS: tuple[Mutation, ...] = (
    Mutation("V1", "valid", ACCEPT, "base rendering", lambda c: c),
    Mutation("V2", "valid", ACCEPT, "schemas re-serialized (key order, indentation)", v2_schemas),
    Mutation("V3", "valid", ACCEPT, "call arguments re-serialized (key order)", v3_call_keys),
    Mutation("V4", "valid", ACCEPT, "scripted rendering under the scripted profile", scripted),
    Mutation("V5a", "valid", ACCEPT, "distinct parallel amounts, consistent", distinct),
    Mutation("V5b", "valid", ACCEPT, "first amount set to 1, consistent", amount_one),
    Mutation("R1", "role", REJECT, "tool results in a tool-role turn", r1_tool_role),
    Mutation(
        "R2", "role", REJECT, "tool results inside the assistant turn", r2_results_in_assistant
    ),
    Mutation("R3", "role", REJECT, "user message rendered as a system turn", r3_user_as_system),
    Mutation("R4", "role", REJECT, "system text moved into the user turn", r4_system_into_user),
    Mutation("R5", "role", REJECT, "end of user turn removed (merged turns)", r5_merge_turns),
    Mutation("R6", "role", REJECT, "grouped tool turn split per result", r6_split_group),
    Mutation("S1", "schema", REJECT, "send_money schema removed", s1_drop_schema),
    Mutation("S2", "schema", REJECT, "parameter renamed", s2_rename_param),
    Mutation("S3", "schema", REJECT, "parameter type changed", s3_param_type),
    Mutation("S4", "schema", REJECT, "tool description altered", s4_description),
    Mutation("A1", "arguments", REJECT, "argument value changed", a1_value),
    Mutation("A2", "arguments", REJECT, "argument key renamed", a2_key),
    Mutation("A3", "arguments", REJECT, "integer rendered as string", a3_int_to_str),
    Mutation("A4", "arguments", REJECT, "integer rendered as float", a4_int_to_float),
    Mutation("A5", "arguments", REJECT, "integer 1 rendered as true", a5_int_to_bool),
    Mutation("D1", "duplicates", REJECT, "schema listed twice", d1_dup_schema),
    Mutation("D2", "duplicates", REJECT, "call rendered twice", d2_dup_call),
    Mutation("D3", "duplicates", REJECT, "result rendered twice", d3_dup_result),
    Mutation("O1", "order", REJECT, "parallel calls swapped", o1_swap_calls),
    Mutation("O2", "order", REJECT, "replayed result after the model turn", o2_carrier_after_model),
    Mutation("O3", "order", REJECT, "user turn after the first result", o3_user_after_result),
    Mutation(
        "X1", "association", REJECT, "a block replaced by another call's result", x1_replace_block
    ),
    Mutation(
        "X2",
        "association",
        REJECT,
        "carrier result moved into the later tool turn",
        x2_carrier_into_later_turn,
    ),
    Mutation("T1", "truncation", REJECT, "cut inside the last result", t1_cut_last_result),
    Mutation("T2", "truncation", REJECT, "generation header removed", t2_no_generation_header),
    Mutation("T3", "truncation", REJECT, "cut inside the payload", t3_cut_payload),
    Mutation("T4", "truncation", REJECT, "start of the prompt cut", t4_cut_start),
    Mutation("P1", "payload", REJECT, "one payload character changed", p1_char),
    Mutation("P2", "payload", REJECT, "payload line breaks or escapes collapsed", p2_line_breaks),
    Mutation("P3", "payload", REJECT, "carrier result as a JSON string literal", p3_string_literal),
    Mutation(
        "P4", "payload", REJECT, "carrier JSON re-serialized (decodes equal)", p4_reserialized_json
    ),
)


def corpus(path: Path = BASE) -> Iterator[tuple[Mutation, Case, Case]]:
    """(mutation, base case, mutated case) for every applicable combination."""
    _, bases = load_base(path)
    for base in bases:
        for mutation in MUTATIONS:
            try:
                yield mutation, base, mutation.apply(copy.deepcopy(base))
            except NotApplicable:
                continue


# ---- WP7 ---------------------------------------------------------------------------

WP7_RENDERS = ("AD-1", "AD-2", "AD-3", "IA-1", "TH-1")


def _near_before(text: str, marker: str, pattern: str) -> re.Match[str] | None:
    at = text.find(marker)
    window = text[max(0, at - 300) : at]
    found = list(re.finditer(pattern, window))
    return found[-1] if found else None


def _sub_at(text: str, marker: str, match: re.Match[str], new: str) -> str:
    base = max(0, text.find(marker) - 300)
    return text[: base + match.start()] + new + text[base + match.end() :]


def w1_rename_param(prompt: str) -> str:
    m = _near_before(prompt, "MARK-PARAM-CHANNEL", r"([\"'])channel\1")
    if m is None:
        raise NotApplicable("parameter name not found")
    return _sub_at(prompt, "MARK-PARAM-CHANNEL", m, m.group(1) + "chan" + m.group(1))


def w2_param_type(prompt: str) -> str:
    at = prompt.find("MARK-PARAM-CHANNEL")
    window = prompt[max(0, at - 200) : at + 200]
    m = re.search(r"([\"'])string\1", window)
    if m is None:
        raise NotApplicable("no declared type near the parameter")
    base = max(0, at - 200)
    return (
        prompt[: base + m.start()] + m.group(1) + "integer" + m.group(1) + prompt[base + m.end() :]
    )


def w3_rename_arg(prompt: str) -> str:
    m = _near_before(prompt, "general-MARKARG", r"([\"'])channel\1\s*:|channel=")
    if m is None:
        raise NotApplicable("argument key not found")
    new = m.group(0).replace("channel", "chan")
    return _sub_at(prompt, "general-MARKARG", m, new)


def w4_arg_type(prompt: str) -> str:
    for quote in ('"', "'"):
        value = f"{quote}general-MARKARG{quote}"
        if value in prompt:
            return prompt.replace(value, f"[{value}]", 1)
    raise NotApplicable("argument value not found")


WP7_MUTATIONS: tuple[tuple[str, str, Callable[[str], str]], ...] = (
    ("W1", "parameter renamed", w1_rename_param),
    ("W2", "parameter type changed", w2_param_type),
    ("W3", "argument key renamed", w3_rename_arg),
    ("W4", "argument scalar type changed", w4_arg_type),
)
