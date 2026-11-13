"""Turn a dev grid into an ordered list of strategies to try on held-out seeds.

The order is a greedy set cover. The first strategy is the one that succeeded on the
most dev seeds. Each later strategy is the one that adds the most dev seeds not already
covered. Ties go to the strategy with more dev successes overall, then to the name, so
the order is deterministic.

A second order, `conditions_plain`, ranks only the strategies with ordinary spacing. It
answers a narrower question: how much of the attack survives without the blank-character
trick, which exploits how this harness implements datamarking rather than the idea.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from prompt_injection_eval.adaptive.hardening import ADAPTIVE_CONDITIONS
from prompt_injection_eval.adaptive.strategies import LIBRARY_VERSION, all_strategies


class RankError(ValueError):
    """The grid rows cannot be ranked."""


def grid_rows(rows: list[dict[str, Any]], *, split: str = "dev") -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("adaptive_phase") == "grid"
        and row.get("seed_split") == split
        and not row.get("error_type")
    ]


def successes_by_strategy(rows: list[dict[str, Any]], condition: str) -> dict[str, set[str]]:
    """Seed ids on which each strategy got attack score `success` under one condition."""
    table: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["condition"] != condition:
            continue
        table.setdefault(row["strategy"], set())
        if row["attack_score"] == "success":
            table[row["strategy"]].add(row["case_id"])
    return dict(table)


def greedy_order(table: dict[str, set[str]], top: int) -> list[dict[str, Any]]:
    covered: set[str] = set()
    remaining = dict(table)
    order: list[dict[str, Any]] = []
    while remaining and len(order) < top:
        name = min(
            remaining,
            key=lambda item: (-len(remaining[item] - covered), -len(remaining[item]), item),
        )
        gained = remaining.pop(name) - covered
        covered |= table[name]
        order.append(
            {
                "strategy": name,
                "dev_successes": len(table[name]),
                "dev_new_seeds": len(gained),
                "dev_cumulative": len(covered),
            }
        )
    return order


def build_ranking(rows: list[dict[str, Any]], *, top: int) -> dict[str, Any]:
    dev = grid_rows(rows)
    if not dev:
        raise RankError("No dev grid rows found.")
    models = {row["model"] for row in dev}
    hashes = {row["dataset_sha256"] for row in dev}
    if len(models) != 1 or len(hashes) != 1:
        raise RankError("A ranking is built from one model and one seed file.")
    expected = {strategy.name for strategy in all_strategies()}
    seed_ids = {row["case_id"] for row in dev}
    conditions: dict[str, list[dict[str, Any]]] = {}
    plain: dict[str, list[dict[str, Any]]] = {}
    plain_names = {strategy.name for strategy in all_strategies() if strategy.spacing == "plain"}
    for condition in ADAPTIVE_CONDITIONS:
        table = successes_by_strategy(dev, condition)
        if not table:
            continue
        missing = expected - set(table)
        if missing:
            raise RankError(f"{condition}: grid is missing strategies {sorted(missing)}")
        conditions[condition] = greedy_order(table, top)
        plain[condition] = greedy_order(
            {name: seeds for name, seeds in table.items() if name in plain_names}, top
        )
    return {
        "library_version": LIBRARY_VERSION,
        "model": models.pop(),
        "seeds_sha256": hashes.pop(),
        "dev_seed_count": len(seed_ids),
        "conditions": conditions,
        "conditions_plain": plain,
    }
