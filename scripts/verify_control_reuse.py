#!/usr/bin/env python
"""Check that a finished development-controls phase can stand in for a new one. No inference.

Amendment 3 lets Qwen3-32B's F1 development controls count as its registered development
controls instead of being rerun. That holds only if they are what the registered phase
would produce now. This script checks, and writes what it checked:

1. The phase is ``dev-controls`` for the same study, AgentDojo release, benchmark version,
   suite hash and attack library as the current code.
2. Its stored plan equals the current ``runner.plan("dev-controls")``, unit by unit.
3. Every planned unit has exactly one final trace, and it is ``completed``.
4. Every trace's request fingerprint equals the one the current code computes for that
   unit and the phase's settings, so the current harness would send the same requests.
5. No file that builds requests, checks delivery, executes tools or scores has changed
   between the phase's commit and HEAD (``git diff``).
6. With ``--against MANIFEST`` (a phase run for the same model in this pilot): identical
   settings and an identical server description (runtime, version, served model, context
   length and launch arguments, which include the image digest and GPU type).

    python scripts/verify_control_reuse.py \\
        results-published/pilot-f1-2026-11-16/qwen3-32b/dev-controls \\
        [--against results/pilot/qwen3-32b/select/manifest.json] --output reuse.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Paths whose change could alter requests, delivery checks, tool execution or scoring.
REQUEST_PATHS = (
    "src/prompt_injection_eval/pilot/__init__.py",
    "src/prompt_injection_eval/pilot/adapter.py",
    "src/prompt_injection_eval/pilot/attacks.py",
    "src/prompt_injection_eval/pilot/delivery.py",
    "src/prompt_injection_eval/pilot/episode.py",
    "src/prompt_injection_eval/pilot/serialize.py",
    "src/prompt_injection_eval/providers",
    "pyproject.toml",
)
SERVER_FIELDS = ("runtime", "runtime_version", "served_model", "max_model_len", "launch_args")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("phase_dir", type=Path)
    parser.add_argument("--against", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from prompt_injection_eval.pilot import (
        AGENTDOJO_VERSION,
        BENCHMARK_VERSION,
        DEV_SUITE,
        STUDY,
        adapter,
        attacks,
        episode,
        runner,
    )
    from prompt_injection_eval.pilot.episode import Settings, Spec

    manifest = json.loads((args.phase_dir / "manifest.json").read_text())
    stored_plan = json.loads((args.phase_dir / "plan.json").read_text())
    rows = runner.read_traces(args.phase_dir / "traces.jsonl")
    settings = Settings(**manifest["settings"])
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: object) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    expected = {
        "study": STUDY,
        "phase": "dev-controls",
        "agentdojo": AGENTDOJO_VERSION,
        "benchmark": BENCHMARK_VERSION,
        "suite_sha256": {DEV_SUITE: adapter.suite_sha256(DEV_SUITE)},
        "attack_library_sha256": attacks.library_sha256(),
    }
    differing = {k: [manifest.get(k), v] for k, v in expected.items() if manifest.get(k) != v}
    check("study, phase, releases, suite and attack library", not differing, differing or "equal")

    current = [asdict(u) for u in runner.plan("dev-controls")]
    check(
        "stored plan equals the current registered plan, in order",
        stored_plan == current,
        f"{len(stored_plan)} stored units, {len(current)} planned now",
    )

    latest = {row["unit_key"]: row for row in rows}
    keys = [Spec(**u).key() for u in current]
    statuses = {}
    for key in keys:
        status = latest.get(key, {}).get("status", "missing")
        statuses[status] = statuses.get(status, 0) + 1
    check(
        "every planned unit has a completed trace",
        statuses == {"completed": len(keys)} and len(rows) == len(keys),
        {"statuses": statuses, "trace_lines": len(rows)},
    )

    mismatched = [
        key
        for key in keys
        if key in latest
        and latest[key].get("request_sha256")
        != episode.fingerprint(Spec(**json.loads(key)), settings)
    ]
    check(
        "every trace's request fingerprint equals the current code's",
        not mismatched and all(k in latest for k in keys),
        f"{len(keys) - len(mismatched)} of {len(keys)} equal",
    )

    old = manifest["git_commit"]
    diff = subprocess.run(  # noqa: S603 - fixed arguments
        ["git", "diff", "--stat", old, "HEAD", "--", *REQUEST_PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    head = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    check(
        "no request, delivery, execution or scoring code changed since the phase ran",
        diff.returncode == 0 and not diff.stdout.strip() and not manifest["git_dirty"],
        {
            "from": old,
            "to": head,
            "paths": list(REQUEST_PATHS),
            "diff": diff.stdout.strip() or None,
        },
    )

    against = None
    if args.against:
        other = json.loads(args.against.read_text())
        against = str(args.against)
        check(
            "settings equal those of the new phase",
            other["settings"] == manifest["settings"],
            {"reused": manifest["settings"], "new": other["settings"]},
        )
        server_old = {k: (manifest.get("server") or {}).get(k) for k in SERVER_FIELDS}
        server_new = {k: (other.get("server") or {}).get(k) for k in SERVER_FIELDS}
        check(
            "server configuration equals that of the new phase",
            server_old == server_new and None not in server_old.values(),
            {"reused": server_old, "new": server_new},
        )

    result = {
        "reused_phase": str(args.phase_dir),
        "reused_phase_git_commit": old,
        "reused_phase_created": manifest.get("created"),
        "reused_phase_plan_sha256": manifest["plan_sha256"],
        "label": manifest["settings"]["label"],
        "checked_at_commit": head,
        "against": against,
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1) + "\n")
    for c in checks:
        print(f"[{'pass' if c['passed'] else 'FAIL'}] {c['check']}")
    print("PASSED" if result["passed"] else "FAILED")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
