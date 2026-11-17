"""Supplementary analyses of the serialization pilot, written 2026-11-17 from stored traces.

**Exploratory.** Every quantity here was chosen after the pilot's outcomes, and after
three reviews, were read. None is registered and none replaces the registered primary
analysis, which stays as reported (first runs, 105 Slack pairs, task bootstrap). This
module only adds tables the pilot already had the data for:

- the complete banking attack x format matrix (selection phase, one run per cell);
- paired contrasts between AgentDojo's multiline baseline and its one-line twin;
- joint security/utility outcomes per condition;
- per-goal format effects;
- round-limit, model-call and token summaries;
- repeat disagreement clustered by pair, for attack and control cells.

Denominators. ``first_run`` tables use run 0 of each case only; ``all_runs`` tables use
every completed final trace and say so. They are never pooled into one figure.

Round-limit episodes. An episode that reaches the 15-round limit is a completed, scored
episode: its outcome is what the final state shows after a finite budget. It is kept in
every denominator and counted separately, never dropped and never re-labelled.

Attack groups. ``multiline`` means the payload, stripped of leading and trailing
whitespace, contains a newline. Every attack is also reported on its own, so a grouping
can be checked against its members. ``json_field_mimic`` is one-line but contains the
characters ``", "`` that close a JSON string when unescaped; aggregates are shown both
with and without it, because a reader may reasonably group it either way.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from prompt_injection_eval.pilot import attacks
from prompt_injection_eval.pilot.analysis import REPLICATES, SEED, latest
from prompt_injection_eval.pilot.exploratory import (
    _clopper_pearson,
    first_runs,
    linear_contrast,
)

FORMATS = ("text", "json")
ONE_LINE_TWIN = "neutral_baseline_one_line"
FIELD_MIMIC = "json_field_mimic"


def final(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The last trace per planned unit (superseded ``infra_error`` traces dropped)."""
    return list(latest(rows).values())


def is_multiline(payload: str | None) -> bool:
    return payload is not None and "\n" in payload.strip()


def normalized(text: str) -> str:
    return " ".join(text.split())


def attack_shapes(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per attack: multiline or not, and whether its payload text is fixed across goals."""
    out: dict[str, dict[str, Any]] = {}
    for row in final(rows):
        if row["mode"] != "attack":
            continue
        entry = out.setdefault(
            row["attack"], {"multiline": is_multiline(row["payload"]), "payload_lines": set()}
        )
        entry["payload_lines"].add(len(row["payload"].strip().split("\n")))
    return {
        a: {"multiline": v["multiline"], "payload_lines": sorted(v["payload_lines"])}
        for a, v in sorted(out.items())
    }


def groups(shapes: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    multi = [a for a, s in shapes.items() if s["multiline"]]
    one = [a for a, s in shapes.items() if not s["multiline"]]
    return {
        "multiline": multi,
        "one_line": one,
        "one_line_without_json_field_mimic": [a for a in one if a != FIELD_MIMIC],
    }


def _count(
    rows: list[dict[str, Any]], attack: str, fmt: str, outcome: str, run: int | None
) -> tuple[int, int]:
    hits = n = 0
    for row in final(rows):
        if (
            row["mode"] == "attack"
            and row["attack"] == attack
            and row["fmt"] == fmt
            and row["status"] == "completed"
            and row[outcome] is not None
            and (run is None or row["run"] == run)
        ):
            n += 1
            hits += bool(row[outcome])
    return hits, n


def attack_matrix(rows: list[dict[str, Any]], model: str, suite: str) -> list[dict[str, Any]]:
    """Every evaluated attack under both formats, first runs, with the text - JSON contrast."""
    out = []
    shapes = attack_shapes(rows)
    for attack in shapes:
        line: dict[str, Any] = {"model": model, "suite": suite, "attack": attack, **shapes[attack]}
        for fmt in FORMATS:
            k, n = _count(rows, attack, fmt, "security", 0)
            u, m = _count(rows, attack, fmt, "utility", 0)
            line[f"{fmt}_attack_success"] = f"{k}/{n}"
            line[f"{fmt}_utility_under_attack"] = f"{u}/{m}"
        c = linear_contrast(
            f"{model} {suite} {attack}: text - json",
            [
                (1.0, f"{attack}/text", first_runs(rows, attack, "text")),
                (-1.0, f"{attack}/json", first_runs(rows, attack, "json")),
            ],
        )
        line.update(
            {
                "cases": c.cases,
                "text_minus_json_pts": round(c.estimate, 2),
                "task_interval": [round(v, 1) for v in c.task_interval],
                "sign_flip_p": round(c.sign_flip_p, 4),
            }
        )
        out.append(line)
    return out


def group_aggregates(rows: list[dict[str, Any]], model: str, suite: str) -> list[dict[str, Any]]:
    """Pooled counts per attack group, first runs. Descriptive: cells share pairs."""
    out = []
    for name, members in groups(attack_shapes(rows)).items():
        if not members:
            continue
        line: dict[str, Any] = {"model": model, "suite": suite, "group": name, "members": members}
        for fmt in FORMATS:
            pairs = [_count(rows, a, fmt, "security", 0) for a in members]
            k, n = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
            line[f"{fmt}_attack_success"] = f"{k}/{n}"
            line[f"{fmt}_rate_pct"] = round(100 * k / n, 1) if n else None
        line["text_minus_json_pts"] = (
            round(line["text_rate_pct"] - line["json_rate_pct"], 1)
            if line["text_rate_pct"] is not None
            else None
        )
        line["attacks_where_json_lower"] = sum(
            _count(rows, a, "text", "security", 0)[0] > _count(rows, a, "json", "security", 0)[0]
            for a in members
        )
        line["attacks_where_json_higher"] = sum(
            _count(rows, a, "text", "security", 0)[0] < _count(rows, a, "json", "security", 0)[0]
            for a in members
        )
        out.append(line)
    return out


def twin_payload_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Do the baseline and its one-line twin carry the same words on every matched case?"""
    base: dict[tuple[str, str, str], str] = {}
    twin: dict[tuple[str, str, str], str] = {}
    for row in final(rows):
        if row["mode"] != "attack" or row["run"] != 0:
            continue
        key = (row["user_task"], row["injection_task"], row["fmt"])
        if row["attack"] == attacks.BASELINE:
            base[key] = row["payload"]
        elif row["attack"] == ONE_LINE_TWIN:
            twin[key] = row["payload"]
    matched = sorted(set(base) & set(twin))
    return {
        "matched_cases": len(matched),
        "equal_after_whitespace_normalization": sum(
            normalized(base[k]) == normalized(twin[k]) for k in matched
        ),
        "byte_identical": sum(base[k] == twin[k] for k in matched),
        "baseline_newlines": sorted({base[k].count("\n") for k in matched}),
        "twin_newlines": sorted({twin[k].count("\n") for k in matched}),
        "normalization": "split on any whitespace run and join with one space",
    }


def twin_contrasts(rows: list[dict[str, Any]], model: str, suite: str) -> list[dict[str, Any]]:
    """Baseline vs one-line twin on the same cases: the line-structure contrast, first runs."""
    b, t = attacks.BASELINE, ONE_LINE_TWIN
    if not first_runs(rows, t, "text"):
        return []
    r = {(a, f): first_runs(rows, a, f) for a in (b, t) for f in FORMATS}
    specs = [
        ("format effect, multiline baseline (text - json)", [(1, b, "text"), (-1, b, "json")]),
        ("format effect, one-line twin (text - json)", [(1, t, "text"), (-1, t, "json")]),
        (
            "interaction: format effect, baseline minus twin",
            [(1, b, "text"), (-1, b, "json"), (-1, t, "text"), (1, t, "json")],
        ),
        ("line breaks under text (baseline - twin)", [(1, b, "text"), (-1, t, "text")]),
        ("line breaks under json (baseline - twin)", [(1, b, "json"), (-1, t, "json")]),
    ]
    out = []
    for name, terms in specs:
        c = linear_contrast(
            f"{model} {suite}: {name}",
            [(float(w), f"{a}/{f}", r[(a, f)]) for w, a, f in terms],
        )
        out.append(
            {
                "model": model,
                "suite": suite,
                "contrast": name,
                "definition": c.row()["definition"],
                "cases": c.cases,
                "estimate_pts": round(c.estimate, 2),
                "task_interval": [round(v, 1) for v in c.task_interval],
                "two_way_interval": [round(v, 1) for v in c.two_way_interval],
                "sign_flip_p": round(c.sign_flip_p, 4),
                **(discordance(r, terms) if len(terms) == 2 else {}),
            }
        )
    return out


def discordance(
    r: dict[tuple[str, str], dict[tuple[str, str], list[float]]], terms: list[tuple[int, str, str]]
) -> dict[str, int]:
    """For a two-term contrast: cases where only the first, or only the second, succeeded."""
    (_, a1, f1), (_, a2, f2) = terms
    first, second = r[(a1, f1)], r[(a2, f2)]
    cases = set(first) & set(second)
    return {
        "only_first_succeeded": sum(first[c][0] > second[c][0] for c in cases),
        "only_second_succeeded": sum(first[c][0] < second[c][0] for c in cases),
    }


def joint_outcomes(rows: list[dict[str, Any]], model: str, suite: str) -> list[dict[str, Any]]:
    """Security x utility per attack condition, first runs."""
    table: dict[str, Counter[str]] = defaultdict(Counter)
    for row in final(rows):
        if row["mode"] != "attack" or row["run"] != 0 or row["status"] != "completed":
            continue
        cell = ("attacked" if row["security"] else "resisted") + (
            "+task_done" if row["utility"] else "+task_failed"
        )
        table[row["condition"]][cell] += 1
        table[row["condition"]]["round_limit"] += bool(row["totals"]["hit_round_limit"])
    out = []
    for condition in sorted(table):
        t = table[condition]
        n = sum(t[k] for k in t if "+" in k)
        out.append(
            {
                "model": model,
                "suite": suite,
                "condition": condition,
                "cases": n,
                "attacked+task_done": t["attacked+task_done"],
                "attacked+task_failed": t["attacked+task_failed"],
                "resisted+task_done": t["resisted+task_done"],
                "resisted+task_failed": t["resisted+task_failed"],
                "of_which_round_limit": t["round_limit"],
            }
        )
    return out


def per_goal(rows: list[dict[str, Any]], model: str, suite: str) -> list[dict[str, Any]]:
    """Per attacker goal and attack: first-run successes in each format and the difference."""
    out = []
    for attack in attack_shapes(rows):
        found = {f: first_runs(rows, attack, f) for f in FORMATS}
        goals = sorted({g for f in FORMATS for _, g in found[f]})
        for goal in goals:
            line: dict[str, Any] = {"model": model, "suite": suite, "attack": attack, "goal": goal}
            for f in FORMATS:
                values = [v[0] for (_, g), v in found[f].items() if g == goal]
                line[f"{f}_successes"] = f"{int(sum(values))}/{len(values)}"
                line[f"{f}_rate"] = sum(values) / len(values) if values else None
            line["text_minus_json_pts"] = round(100 * (line["text_rate"] - line["json_rate"]), 1)
            del line["text_rate"], line["json_rate"]
            out.append(line)
    return out


def budget(
    rows: list[dict[str, Any]], model: str, phase: str, first_run_only: bool
) -> list[dict[str, Any]]:
    """Round-limit, calls and tokens per condition. Completed final traces only."""
    acc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in final(rows):
        if row["status"] != "completed" or (first_run_only and row["run"] != 0):
            continue
        acc[row["condition"]].append(row)
    out = []
    for condition in sorted(acc):
        found = acc[condition]
        totals = [r["totals"] for r in found]
        limit = [r for r in found if r["totals"]["hit_round_limit"]]
        outcome = "security" if found[0]["mode"] == "attack" else "utility"
        if found[0]["mode"] in ("direct", "twin"):
            outcome = "success"
        out.append(
            {
                "model": model,
                "phase": phase,
                "denominator": "first runs" if first_run_only else "all completed runs",
                "condition": condition,
                "episodes": len(found),
                "round_limit": len(limit),
                "round_limit_with_positive_outcome": sum(bool(r[outcome]) for r in limit),
                "outcome_counted": outcome,
                "model_calls_mean": round(float(np.mean([t["model_calls"] for t in totals])), 2),
                "model_calls_max": max(t["model_calls"] for t in totals),
                "prompt_tokens_mean": round(float(np.mean([t["prompt_tokens"] for t in totals]))),
                "completion_tokens_mean": round(
                    float(np.mean([t["completion_tokens"] for t in totals])), 1
                ),
                "last_prompt_tokens_max": max(
                    (r["turns"][-1]["prompt_tokens"] or 0) for r in found if r["turns"]
                ),
                "truncated_turns": sum(t["truncated_turns"] for t in totals),
                "schema_rejections": sum(t["schema_rejections"] for t in totals),
            }
        )
    return out


def clustered_disagreement(
    rows: list[dict[str, Any]],
    model: str,
    phase: str,
    modes: tuple[str, ...],
    outcome_of: dict[str, str],
    replicates: int = REPLICATES,
    seed: int = SEED,
) -> dict[str, Any]:
    """Cells with three completed runs that disagree, clustered by case (user task, goal).

    For attack cells a case is a (user task, goal) pair; for controls it is the user task
    (clean, scratch) or the goal (direct, twin). Cells of one case share it, so the
    case-level count and a case bootstrap are given beside the cell count.
    """
    runs: dict[tuple[str, str, str], dict[int, bool]] = defaultdict(dict)
    for row in final(rows):
        if row["status"] != "completed" or row["mode"] not in modes:
            continue
        value = row[outcome_of[row["mode"]]]
        if value is None:
            continue
        case = (row["user_task"] or "-", row["injection_task"] or "-")
        runs[(*case, row["condition"])][int(row["run"])] = bool(value)
    by_case: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for (user, goal, _), found in runs.items():
        if len(found) >= 3:
            by_case[(user, goal)].append(len(set(found.values())) > 1)
    cases = sorted(by_case)
    if not cases:
        return {"model": model, "phase": phase, "modes": list(modes), "repeated_cells": 0}
    dis = np.array([sum(by_case[c]) for c in cases], dtype=float)
    size = np.array([len(by_case[c]) for c in cases], dtype=float)
    rng = np.random.default_rng(seed)
    shares = np.empty(replicates)
    for i in range(replicates):
        pick = rng.integers(0, len(cases), len(cases))
        shares[i] = dis[pick].sum() / size[pick].sum()
    k, n = int(dis.sum()), int(size.sum())
    kc = int((dis > 0).sum())
    lo, hi = _clopper_pearson(kc, len(cases))
    blo, bhi = np.percentile(shares, [2.5, 97.5])
    return {
        "model": model,
        "phase": phase,
        "modes": list(modes),
        "outcomes": {m: outcome_of[m] for m in modes},
        "repeated_cases": len(cases),
        "repeated_cells": n,
        "disagreeing_cells": k,
        "cell_share_pct": round(100 * k / n, 2),
        "cases_with_any_disagreement": kc,
        "case_share_exact_interval_pct": [round(100 * lo, 1), round(100 * hi, 1)],
        "cell_share_case_bootstrap_pct": [round(100 * blo, 1), round(100 * bhi, 1)],
    }


def prompt_verification_scope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Which recorded model turns can be rebuilt from stored history, final vs superseded.

    A turn is reconstructible when the trace stores the assistant message that followed it
    (the verifier rebuilds each request from the stored conversation). Aborted traces keep
    only the conversation up to the abort, so later turns of theirs cannot be rebuilt; the
    aborted request itself returned no prompt and records no turn.
    """
    keep = {id(r) for r in final(rows)}
    out: Counter[str] = Counter()
    for row in rows:
        kind = "final" if id(row) in keep else "superseded"
        assistant = [m for m in row.get("messages") or [] if m["role"] == "assistant"]
        stored = max(0, len(assistant) - len(row["prefix_calls"]))
        turns = len(row["turns"])
        out[f"{kind}_traces"] += 1
        out[f"{kind}_turns_recorded"] += turns
        out[f"{kind}_turns_reconstructible"] += min(turns, stored)
        out[f"{kind}_turns_not_reconstructible"] += max(0, turns - stored)
        out[f"{kind}_scored"] += row["status"] == "completed"
    return dict(sorted(out.items()))
