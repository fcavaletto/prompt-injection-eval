"""Separate visible reasoning from the final answer.

Reasoning-tuned models such as DeepSeek-R1 distills and Qwen3 emit their
chain-of-thought in the completion, either as a separate ``thinking`` field
from the runtime or inline inside ``<think>...</think>`` tags. The harness
scores only the final answer. The reasoning is stored because it is visible
model output, not a hidden channel, and it is useful for understanding why a
model complied with an injected instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_THINK_BLOCK = re.compile(r"^\s*<think>(.*?)</think>\s*", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"^\s*<think>", re.IGNORECASE)


@dataclass(frozen=True)
class SplitResponse:
    answer: str
    reasoning: str | None
    truncated: bool


def split_reasoning(content: str) -> SplitResponse:
    """Split a leading inline think block from the answer.

    A ``<think>`` that is never closed means generation stopped inside the
    reasoning. The answer is then empty and ``truncated`` is True.
    """
    match = _THINK_BLOCK.match(content)
    if match:
        return SplitResponse(
            answer=content[match.end() :],
            reasoning=match.group(1).strip() or None,
            truncated=False,
        )
    if _THINK_OPEN.match(content):
        body = _THINK_OPEN.sub("", content, count=1).strip()
        return SplitResponse(answer="", reasoning=body or None, truncated=True)
    return SplitResponse(answer=content, reasoning=None, truncated=False)


def strip_reasoning(text: str) -> str:
    """Return only the final answer. Used defensively by the scorers."""
    return split_reasoning(text).answer


def estimate_tokens(text: str | None) -> int | None:
    """Rough token estimate. Four characters per token is a documented heuristic."""
    if text is None:
        return None
    return max(1, len(text) // 4) if text else 0
