#!/usr/bin/env python
"""Draw the blinded sample for human validation of the Study B scorer.

Reads the published Study B rows, draws a stratified sample, and writes:

- ``items.jsonl``: what a rater sees. No model, condition or automated label.
- ``annotation_sheet.csv``: one row per item with empty label columns.
- ``manifest.json``: strata sizes, the seed and the SHA-256 of the key.
- ``key.jsonl``: the link from item id to model, condition and automated labels.
  It is listed in .gitignore and must not be opened by a rater before labelling ends.

The draw is deterministic, so the key can be rebuilt from the seed. Blinding therefore
rests on raters not running this script or opening the key. docs/annotation-protocol.md
says so.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt_injection_eval import injecagent  # noqa: E402

SEED = 20261115
OUT = ROOT / "data" / "annotation" / "study-b-v1"
STUDY_B = ROOT / "results-published" / "v08"
# Phi-4-mini and Granite 3.3 are left out: the audit found they were not validly run as
# agents, and they produced 0 and 13 parsed calls.
MODELS = [
    "qwen3-4b",
    "qwen3-8b",
    "qwen3-14b",
    "qwen3-32b",
    "qwen2.5-7b",
    "hermes-3-8b",
    "gpt-oss-20b",
    "gpt-oss-120b",
]
PER_MODEL = {
    "scored_success": 12,
    "named_in_text_no_call": 8,
    "other_tool_called": 5,
    "no_call_no_mention": 5,
}


def stratum(row: dict) -> str:
    if row["attack_score"] == "success":
        return "scored_success"
    if row.get("target_in_text_unparsed"):
        return "named_in_text_no_call"
    if row.get("tool_call_names"):
        return "other_tool_called"
    return "no_call_no_mention"


def main() -> None:
    rng = random.Random(SEED)
    cases = {c.id: c for c in injecagent.load_cases(ROOT / injecagent.DATA_DIR)}
    instructions = {}
    for name in ("dh_base", "dh_enhanced", "ds_base", "ds_enhanced"):
        raw = json.loads((ROOT / injecagent.DATA_DIR / f"test_cases_{name}.json").read_text())
        attack, setting = name.split("_")
        for index, case in enumerate(raw):
            instructions[f"{attack}-{setting}-{index:04d}"] = case["Attacker Instruction"]
    picked, population = [], {}
    for model in MODELS:
        rows = []
        with gzip.open(STUDY_B / model / "raw_results.jsonl.gz", "rt") as handle:
            for line in handle:
                row = json.loads(line)
                if not row.get("error_type"):
                    rows.append(row)
        by_stratum: dict[str, list[dict]] = {}
        for row in sorted(rows, key=lambda r: (r["case_id"], r["condition"])):
            by_stratum.setdefault(stratum(row), []).append(row)
        for name, quota in PER_MODEL.items():
            pool = by_stratum.get(name, [])
            population[f"{model}/{name}"] = len(pool)
            for row in rng.sample(pool, min(quota, len(pool))):
                picked.append((model, name, row))
    rng.shuffle(picked)
    missing = [row["case_id"] for _, _, row in picked if row["case_id"] not in instructions]
    if missing:
        raise SystemExit(f"case ids without an attacker instruction: {missing[:5]}")

    OUT.mkdir(parents=True, exist_ok=True)
    items, key = [], []
    for number, (model, name, row) in enumerate(picked, start=1):
        case = cases[row["case_id"]]
        item_id = f"B{number:03d}"
        items.append(
            {
                "item": item_id,
                "user_request": case.user_instruction,
                "attacker_instruction": instructions[row["case_id"]],
                "user_tool": case.user_tool,
                "attacker_tools": list(case.attacker_tools),
                "model_reply_text": row.get("response_text") or "",
                "model_tool_calls": row.get("tool_calls") or [],
            }
        )
        key.append(
            {
                "item": item_id,
                "model": model,
                "condition": row["condition"],
                "case_id": row["case_id"],
                "stratum": name,
                "attack_score": row["attack_score"],
                "injecagent_eval": row.get("injecagent_eval"),
                "unit_key": row["unit_key"],
            }
        )
    with (OUT / "items.jsonl").open("w") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    key_text = "".join(json.dumps(k, sort_keys=True) + "\n" for k in key)
    (OUT / "key.jsonl").write_text(key_text)
    with (OUT / "annotation_sheet.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["item", "rater", "q1_attempt", "q2_arguments", "q3_disclosed", "note"])
        for item in items:
            writer.writerow([item["item"], "", "", "", "", ""])
    manifest = {
        "seed": SEED,
        "source": "results-published/v08 (Study B), rows without a backend error",
        "models": MODELS,
        "quota_per_model": PER_MODEL,
        "items": len(items),
        "population_by_model_and_stratum": population,
        "key_sha256": hashlib.sha256(key_text.encode()).hexdigest(),
        "status": "Sample drawn. No rater has been recruited and no item has been labelled.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(items)} items written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
