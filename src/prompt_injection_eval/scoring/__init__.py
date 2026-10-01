"""Attack and task scoring entry points."""

from prompt_injection_eval.scoring.attack import score_attack
from prompt_injection_eval.scoring.task import score_task

__all__ = ["score_attack", "score_task"]
