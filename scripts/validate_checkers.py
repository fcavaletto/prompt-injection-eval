#!/usr/bin/env python
"""Run the delivery checkers on the validation corpus and count detections. No inference.

    python scripts/validate_checkers.py --label v1 \
        --output results-published/checker-validation-2026-11-17
    HF_HUB_OFFLINE=1 python scripts/validate_checkers.py --label v2 --verify-templates --output ...

Checkers: the pilot's ``delivery.check`` (as used by the archived pilot), the contract
checker ``delivery.check_contract`` when it exists, and ``wp7.check`` with and without
its strict items. Expected verdicts come from ``checker_corpus`` and were fixed before
any checker ran on it. ``--verify-templates`` re-renders every valid variant's messages
with the pinned tokenizer and requires an identical prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval import wp7  # noqa: E402
from prompt_injection_eval.pilot import checker_corpus as cc  # noqa: E402
from prompt_injection_eval.pilot import delivery  # noqa: E402

WP7_DIR = ROOT / "results-published" / "wp7-audit-2026-11-16"


def pilot_checkers() -> dict[str, Any]:
    found: dict[str, Any] = {
        "pilot_v1": lambda c: delivery.check(
            c["rendered"],
            c["messages"],
            c["tools"],
            c["records"],
            c["fmt"],
            c["payload"],
            c["payload_index"],
        )
    }
    if hasattr(delivery, "check_contract"):
        found["pilot_contract"] = lambda c: delivery.check_contract(
            c["rendered"],
            c["messages"],
            c["tools"],
            c["records"],
            c["fmt"],
            c["payload"],
            c["payload_index"],
            profile=c["profile"],
        )
    return found


def wp7_checkers() -> dict[str, Any]:
    found: dict[str, Any] = {
        "wp7_v1": lambda p: wp7.check(p, strict=False) if _has_strict() else wp7.check(p)
    }
    if _has_strict():
        found["wp7_strict"] = lambda p: wp7.check(p, strict=True)
    return found


def _has_strict() -> bool:
    import inspect

    return "strict" in inspect.signature(wp7.check).parameters


def verify_templates(cases: list[tuple[Any, dict, dict]]) -> dict[str, Any]:
    import transformers

    tokenizers: dict[str, Any] = {}
    checked, identical, failures = 0, 0, []
    for mutation, base, case in cases:
        if mutation.expected != cc.ACCEPT or case["profile"] == "scripted":
            continue
        repo, revision = base["tokenizer"].split("@")
        if repo not in tokenizers:
            tokenizers[repo] = transformers.AutoTokenizer.from_pretrained(
                repo, revision=revision, token=False
            )
        if mutation.id in ("V2", "V3"):
            continue  # re-serializations a template would not produce; accepted by the spec
        rendered = tokenizers[repo].apply_chat_template(
            case["messages"],
            tools=case["tools"],
            add_generation_prompt=True,
            tokenize=False,
            **base["template_kwargs"],
        )
        checked += 1
        if rendered == case["rendered"]:
            identical += 1
        else:
            failures.append(f"{base['id']}:{mutation.id}")
    return {"checked": checked, "identical_to_pinned_template": identical, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-templates", action="store_true")
    args = parser.parse_args()

    cases = list(cc.corpus())
    rows: list[dict[str, Any]] = []
    for name, check in pilot_checkers().items():
        for mutation, base, case in cases:
            defects = check(case)
            rows.append(
                {
                    "checker": name,
                    "case": f"{base['id']}:{mutation.id}",
                    "class": mutation.cls,
                    "mutation": mutation.id,
                    "expected": mutation.expected,
                    "verdict": cc.REJECT if defects else cc.ACCEPT,
                    "defects": defects[:6],
                }
            )

    fixture = wp7.load_fixture()
    for name, check in wp7_checkers().items():
        for render in cc.WP7_RENDERS:
            prompt = (WP7_DIR / "renders" / f"{render}.txt").read_text()
            rows.append(_wp7_row(name, f"{render}:W0", "W0", cc.ACCEPT, check(prompt)))
            for mid, _, mutate in cc.WP7_MUTATIONS:
                try:
                    mutated = mutate(prompt)
                except cc.NotApplicable:
                    continue
                rows.append(_wp7_row(name, f"{render}:{mid}", mid, cc.REJECT, check(mutated)))
    del fixture

    summary: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for r in rows:
        s = summary[r["checker"]][r["class"]]
        s["cases"] += 1
        if r["expected"] == cc.REJECT:
            s["should_reject"] += 1
            s["detected"] += r["verdict"] == cc.REJECT
        else:
            s["should_accept"] += 1
            s["false_alarms"] += r["verdict"] == cc.REJECT
    out = {
        "label": args.label,
        "checkers": sorted(summary),
        "summary": {k: {c: dict(v) for c, v in d.items()} for k, d in summary.items()},
        "misses": [r for r in rows if r["verdict"] != r["expected"]],
        "rows": rows,
    }
    if args.verify_templates:
        out["template_verification"] = verify_templates(cases)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f"results_{args.label}.json").write_text(json.dumps(out, indent=1) + "\n")
    lines = [
        f"## Checker validation, {args.label}\n",
        "| Checker | Class | Should reject | Detected | Should accept | False alarms |",
        "|---|---|---:|---:|---:|---:|",
    ]
    order = [
        "valid",
        "role",
        "schema",
        "arguments",
        "duplicates",
        "order",
        "association",
        "truncation",
        "payload",
        "wp7-valid",
        "wp7",
    ]
    for checker in sorted(summary):
        for cls in order:
            if cls in summary[checker]:
                s = summary[checker][cls]
                lines.append(
                    f"| {checker} | {cls} | {s['should_reject']} | {s['detected']} "
                    f"| {s['should_accept']} | {s['false_alarms']} |"
                )
    lines.append("\n### Disagreements with the expected verdict\n")
    lines += [
        f"- `{r['checker']}` {r['case']} ({r['class']}): expected {r['expected']}, "
        f"got {r['verdict']} {r['defects']}"
        for r in out["misses"]
    ]
    (args.output / f"summary_{args.label}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    if args.verify_templates:
        print(json.dumps(out["template_verification"]))


def _wp7_row(checker: str, case: str, mid: str, expected: str, result: Any) -> dict[str, Any]:
    return {
        "checker": checker,
        "case": case,
        "class": "wp7-valid" if expected == cc.ACCEPT else "wp7",
        "mutation": mid,
        "expected": expected,
        "verdict": cc.ACCEPT if result.passed else cc.REJECT,
        "defects": result.missing[:6],
    }


if __name__ == "__main__":
    main()
