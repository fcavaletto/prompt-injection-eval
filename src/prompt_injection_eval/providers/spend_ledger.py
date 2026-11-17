"""A durable spending ledger for paid API calls (OpenRouter screen).

Rules, each covered by an offline test (tests/test_openrouter.py):

- **Reserve before sending, durably.** A reservation is appended and fsynced before the
  request leaves this process. If the process dies, the reservation survives.
- **Charged until reconciled.** A reservation becomes a charge at its reserved amount unless
  it is *settled* with the cost the API reported for it, or *released* with evidence that the
  request never left (a refused connection). A timeout, a disconnect after sending, an HTTP
  error or a response without usable cost stays charged at the reserved amount: OpenRouter
  documents that non-streaming requests continue and are billed even if the client goes away.
- **Restart restores everything.** Opening the ledger replays it: settled costs, unresolved
  reservations (including those left pending by a crash) and the cumulative call count.
- **One spender at a time.** The ledger holds an exclusive, non-blocking ``flock`` for its
  whole life; a second process (or a second open in the same process) cannot open it.
- **Overrun halts.** If a reported cost exceeds its reservation, the bound behind the
  reservation was wrong: the overrun is recorded and no further reservation is granted.

The reservation bound is conservative but not provable (docs/protocol-openrouter.md §6):
input tokens <= UTF-8 bytes of the request body plus a fixed allowance for provider-added
framing; output tokens <= ``max_tokens``. The service-side key limit is the backstop.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class LedgerBusy(RuntimeError):
    """Another process (or handle) already holds this ledger."""


class SpendLedger:
    def __init__(self, path: Path, cap_usd: float, max_calls: int) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cap_usd = cap_usd
        self.max_calls = max_calls
        self._lock = threading.Lock()
        self._lockfile = open(self.path.with_suffix(".lock"), "a")  # noqa: SIM115 - held open
        try:
            fcntl.flock(self._lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._lockfile.close()
            raise LedgerBusy(f"{self.path} is in use by another process.") from exc
        self.spent = 0.0  # settled with reported cost
        self.open: dict[str, dict[str, Any]] = {}  # pending: reserved, not yet resolved
        self.unresolved: dict[str, dict[str, Any]] = {}  # charged at the reserved amount
        self.calls = 0
        self.halted: str | None = None
        self.baseline: dict[str, Any] | None = None
        self._replay()

    # -- persistence ---------------------------------------------------------------------

    def _append(self, entry: dict[str, Any]) -> None:
        entry = {"t": time.time(), **entry}
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _replay(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            op = e["op"]
            if op == "reserve":
                self.open[e["id"]] = e
                self.calls += 1
            elif op == "settle":
                self.open.pop(e["id"], None)
                self.unresolved.pop(e["id"], None)
                self.spent += e["cost_usd"]
            elif op == "release":
                self.open.pop(e["id"], None)
            elif op == "unresolved":
                r = self.open.pop(e["id"], None) or {"worst_usd": e["worst_usd"]}
                self.unresolved[e["id"]] = {**r, "reason": e["reason"]}
            elif op == "halt":
                self.halted = e["reason"]
            elif op == "baseline":
                self.baseline = e
        # Anything still pending was in flight when the process stopped: it may be billed.
        for rid, r in list(self.open.items()):
            self.unresolved[rid] = {**r, "reason": "pending at restart (process stopped in flight)"}
            self._append(
                {
                    "op": "unresolved",
                    "id": rid,
                    "worst_usd": r["worst_usd"],
                    "reason": "pending at restart",
                }
            )
        self.open.clear()

    # -- accounting ----------------------------------------------------------------------

    def committed(self) -> float:
        return (
            self.spent
            + sum(r["worst_usd"] for r in self.open.values())
            + sum(r["worst_usd"] for r in self.unresolved.values())
        )

    def reserve(self, worst_usd: float, note: str = "") -> str | None:
        with self._lock:
            if (
                self.halted
                or self.calls >= self.max_calls
                or self.committed() + worst_usd > self.cap_usd
            ):
                return None
            rid = uuid.uuid4().hex
            entry = {"op": "reserve", "id": rid, "worst_usd": worst_usd, "note": note}
            self._append(entry)
            self.open[rid] = entry
            self.calls += 1
            return rid

    def settle(self, rid: str, cost_usd: float, evidence: str) -> None:
        with self._lock:
            r = self.open.pop(rid)
            self._append({"op": "settle", "id": rid, "cost_usd": cost_usd, "evidence": evidence})
            self.spent += cost_usd
            if cost_usd > r["worst_usd"] + 1e-12:
                self.halted = f"reported cost {cost_usd} exceeded its reservation {r['worst_usd']}"
                self._append({"op": "halt", "reason": self.halted})

    def release(self, rid: str, evidence: str) -> None:
        """Only with evidence that the request never left this process."""
        with self._lock:
            self.open.pop(rid)
            self._append({"op": "release", "id": rid, "evidence": evidence})

    def mark_unresolved(self, rid: str, reason: str) -> None:
        with self._lock:
            r = self.open.pop(rid)
            self.unresolved[rid] = {**r, "reason": reason}
            self._append(
                {"op": "unresolved", "id": rid, "worst_usd": r["worst_usd"], "reason": reason}
            )

    def halt(self, reason: str) -> None:
        with self._lock:
            self.halted = reason
            self._append({"op": "halt", "reason": reason})

    def record_baseline(self, key_info: dict[str, Any]) -> None:
        with self._lock:
            if self.baseline is None:
                self.baseline = {"op": "baseline", **key_info}
                self._append(self.baseline)

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "spent_usd": round(self.spent, 6),
                "unresolved_usd": round(sum(r["worst_usd"] for r in self.unresolved.values()), 6),
                "in_flight_usd": round(sum(r["worst_usd"] for r in self.open.values()), 6),
                "committed_usd": round(self.committed(), 6),
                "cap_usd": self.cap_usd,
                "calls": self.calls,
                "halted": self.halted,
            }

    def close(self) -> None:
        if not self._lockfile.closed:
            fcntl.flock(self._lockfile, fcntl.LOCK_UN)
            self._lockfile.close()

    def __enter__(self) -> SpendLedger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
