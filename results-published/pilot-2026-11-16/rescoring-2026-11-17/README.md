# Per-round rescoring of the archived pilot (2026-11-17), exploratory

`python scripts/pilot_rescore.py results-published/pilot-2026-11-16 --output <dir>`. No model call. Code: `src/prompt_injection_eval/pilot/rescore.py`; tests: `tests/test_stage1_analysis.py`.

**The archived final-state outcome stays the primary measure.** This adds, where the stored history supports it, *ever succeeded* and *first-success round*.

**How the states are obtained.**

- The recorded calls are re-executed through AgentDojo's runtime, as its `ToolsExecutor` would.
- A replay is *verified* only if its final state hash equals the one recorded at run time. No state is inferred from what the model wrote.
- Result: 4,062 of 4,062 archived attack episodes (selection and evaluation, both models) verify.

**What a round is.**

- Round 0 is the state after the replayed prefix.
- Round *k* is the model's *k*-th response together with the execution of all its tool calls.
- In a round-limited episode, the 16th response's calls were never executed: AgentDojo's loop ends first. They changed no state.
- `first_success_call` gives the same measure per individual tool execution.

**Findings, descriptive** (`per_round.csv`, first runs):

- **Archived disagreements.** Three archived outcomes disagree with the executed-calls check, all in one Granite Slack cell (C25).
- **Timing on Slack** (evaluation, first runs). Every success had happened by round 8, except one: Granite, `text_fake_turn` under JSON, between rounds 13 and 16.
  - Granite's baseline: 67 successes under text and 57 under JSON, all by round 8.
  - The extra rounds of text's round-limited episodes (23 against 10) added no success.
  - This describes timing. It does not show why text looped more, or that looping and success are causally related.
- **Ever against final.** One episode (Qwen selection) succeeded at some round but not at the end.

**Censoring.** An episode with no success either reached the round limit (`no_success_within_budget_round_limit`) or stopped first (`no_success_before_agent_stopped`). Neither shows that it *would never* succeed with more rounds or another run.
