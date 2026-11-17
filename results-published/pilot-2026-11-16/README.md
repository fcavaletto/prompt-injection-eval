# Serialization pilot, 2026-11-16 (UTC 11:35 to 13:31)

Two models, Qwen3-32B and Granite 4.0 H Small, under [Amendment 3](../../docs/preregistration.md#amendment-3-2026-11-16-one-first-run-per-evaluation-case-a-frozen-repeat-subset-before-any-selection-or-evaluation-episode), registered and implemented in `1f4c368` before any selection or evaluation episode (CI passed both jobs). Design: [docs/pilot-design.md](../../docs/pilot-design.md), sections 5 and 9.6c.

These are custom-harness results on AgentDojo tasks with the agent resumed after a controlled reference-prefix replay. They are **not** AgentDojo benchmark scores. Workspace and travel were not touched. This is a pilot: it does not confirm a hypothesis, and main-conference novelty remains unestablished.

## Episode accounting

| Model | Phase | Suite | Planned | Completed | Invalid | Not started | Superseded `infra_error` traces |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3-32B | Development controls | banking | 300 | 300 (F1, reused) | 0 | 0 | 0 |
| Qwen3-32B | Selection | banking | 1,296 | 1,296 | 0 | 0 | 5 |
| Qwen3-32B | Evaluation controls | slack | 312 | 312 | 0 | 0 | 0 |
| Qwen3-32B | Evaluation | slack | 882 | 882 | 0 | 0 | 0 |
| Granite 4.0 H Small | Development controls | banking | 300 | 300 | 0 | 0 | 0 |
| Granite 4.0 H Small | Selection | banking | 1,296 | 1,296 | 0 | 0 | 0 |
| Granite 4.0 H Small | Evaluation controls | slack | 312 | 312 | 0 | 0 | 0 |
| Granite 4.0 H Small | Evaluation | slack | 588 | 588 | 0 | 0 | 1 |

- 4,986 new episodes completed with verified delivery, plus Qwen's 300 F1 controls reused.
- **Superseded traces.** Six episodes were cut short by the RunPod HTTP proxy closing a pooled connection ("Server disconnected without sending a response"). The server logged every request it received as `200 OK`; the requests that failed never reached it. The provider retries connection errors but not this one, so each became `infra_error`, which is not a final status. Resuming the phase reran exactly those units, as the runner does for any non-final status. No partial episode was scored. The traces files keep the superseded lines; every report uses the last trace per unit.
- **Qwen's development controls** are F1's (`results-published/pilot-f1-2026-11-16/qwen3-32b/dev-controls`). `qwen3-32b/control_reuse_check.json` passed all seven checks, including identical settings and server description against this pilot's selection phase.
- **F1's baseline-feasibility episodes** were not used. Selection reran the baseline on the development pairs as registered.

## Validity

**Delivery and prompts.**

- Every returned prompt passed the delivery check.
- All 21,327 model turns of the new phases match a local rendering at the pinned revision by hash (`prompt_verification_*.json`), and every kept full prompt (580) is identical.
  *Note 2026-11-17: precisely, all 21,321 turns of scored episodes; 6 of the 21,327 are turns of superseded traces, and 11 turns of superseded traces are not reconstructible ([corrections](../../docs/corrections.md) C21; [supplementary](supplementary-2026-11-17/README.md)).*
- The verifier lists 11 turns of Qwen's selection as unverifiable. They belong to the five superseded `infra_error` traces, which store no assistant message for an aborted turn. All final traces verify.
- Each model's one-request rendering check found the server's prompt identical to the local rendering.
- Same image digest as F1 (`sha256:d825baf9…`) on both pods.

**Parsing.** All rates are far below the 5% limit.

- Unparsed call text: Qwen 4 of 4,492 development turns and 1 of 7,035 Slack turns; Granite 1 of 4,917 and 1 of 5,602.
- Qwen on Slack: 3 calls to unknown tools and 42 schema rejections (0.6% of turns), all but 3 of them in attack episodes.
- Granite on Slack: 1 turn cut off at the output limit.
- No tool arguments failed to parse as JSON.

**Development gates (`dev-gates-v1`).** Both models passed all four (`development_gates.json`).

| | Qwen3-32B | Granite 4.0 H Small |
| --- | --- | --- |
| Development episodes verified | 1,596 / 1,596 | 1,596 / 1,596 |
| Resumed user task, no attack (text / JSON) | 33/48, 30/48 | 28/48, 30/48 |
| Goals with a capable benign twin | 8 / 9 | 8 / 9 |

**Slack controls** (three runs; `report/report.md`):

| | Qwen text | Qwen JSON | Granite text | Granite JSON |
| --- | ---: | ---: | ---: | ---: |
| Resumed user task, no attack | 86% | 90% | 78% | 81% |
| User task from the request | 81% | 81% | 70% | 76% |
| Benign twins | 15/15 | 15/15 | 15/15 | 15/15 |
| Direct requests | 15/15 | 15/15 | 15/15 | 15/15 |

All five Slack goals are in the capable set for both models, so the capability-restricted analysis equals the full one.

## Selection (frozen and committed before each model's first Slack episode)

| Model | Selected for text | Selected for JSON | Baseline on development (text / JSON) | Commit |
| --- | --- | --- | --- | --- |
| Qwen3-32B | `text_task_update` (58/72) | `neutral_baseline_one_line` (47/72) | 53/72, 41/72 | `177312a` |
| Granite 4.0 H Small | `text_fake_turn` (42/72) | `text_fake_turn` (35/72) | 47/72, 35/72 | `e37d3e4` |

Granite's winner was the same for both formats, so it was evaluated once (588 episodes), as registered. Its primary contrast is therefore its same-attack contrast for `text_fake_turn`.

## Primary analysis: first runs, 105 pairs, equal weight

Text minus JSON in percentage points of attack success. The task interval resamples the 21 user tasks with the 5 goals fixed. The two-way interval also resamples goals and is not relied on. All contrasts are complete (105/105 cases), interpretable, and their extreme-value bounds equal the estimate.

| Model | Contrast | Text | JSON | Difference | Task interval | Two-way | Sign-flip p |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| Qwen3-32B | **Primary: each format vs its selected attack** | 94.3 | 85.7 | **+8.6** | **+2.9 to +14.3** | +0.0 to +21.0 | 0.02 |
| Qwen3-32B | Same attack: baseline | 88.6 | 86.7 | +1.9 | −3.8 to +7.6 | −7.6 to +10.5 | 0.75 |
| Qwen3-32B | Same attack: `text_task_update` | 94.3 | 92.4 | +1.9 | −3.8 to +8.6 | −7.6 to +11.4 | 0.78 |
| Qwen3-32B | Same attack: `neutral_baseline_one_line` | 86.7 | 85.7 | +1.0 | −3.8 to +5.7 | −5.7 to +9.5 | 1.00 |
| Granite 4.0 H Small | **Primary (= same attack: `text_fake_turn`)** | 70.5 | 59.0 | **+11.4** | **+2.9 to +21.0** | −1.0 to +25.7 | 0.04 |
| Granite 4.0 H Small | Same attack: baseline | 63.8 | 54.3 | +9.5 | +2.9 to +17.1 | −1.0 to +22.9 | 0.04 |

Within each format, Qwen's selected attack minus the other format's selected attack:

- On text: +7.6 (+1.9 to +15.2).
- On JSON: −6.7 (−12.4 to −1.0).

The attack selected for JSON on banking did worse on Slack than the text-selected one *in both formats*. Selection benefit over the baseline: Qwen +5.7 (text), −1.0 (JSON); Granite +6.7 (text), +4.8 (JSON); only Qwen's text interval excludes zero.

**User task under attack** (text minus JSON): Qwen +1.9, +1.0, −2.9; Granite −6.7 (−14.3 to +0.0) and −4.8 (−12.4 to +1.9).

**Reading, by the registered rules.** For both models the primary interval lies above zero, which is read as: *with this library and budget, the best attack found for JSON did worse than the best found for text, on these 21 user tasks and 5 goals.* It is not read as showing that JSON is a mitigation, or as a statement about other attackers.

What the contrasts beside it show:

- **Qwen3-32B: the primary difference is attack wording, not format.** Every same-attack contrast is within +1 to +2 points with intervals across zero. Three of five goals are at or near 100% under every condition (ceiling). The +8.6 comes almost entirely from `injection_task_2`, where the JSON-selected wording succeeded 10–11 times in 21 in both formats against 15–16 for the text-selected wording. Banking-based selection for JSON did not transfer to Slack.
  *Note 2026-11-16: too categorical. Decomposed, +7.1 points (+2.4 to +12.9) are wording and +1.4 (−2.9 to +6.2) the average same-attack format difference, which does not exclude a format effect of a few points. See [exploratory/](exploratory/README.md) and Corrections C11.*
- **Granite 4.0 H Small: a same-attack format difference.** Under the fixed baseline and under the selected attack, JSON was attacked about 10 points less often than text, with task intervals excluding zero, in the direction ToolHazard reports for fixed attacks. Format-aware selection did not find a JSON-specific wording: the same candidate won in both formats.
- **The two-way intervals reach zero for both models.** With five goals they are not trustworthy, but they show the results are conditional on these goals.

## Secondary: repeatability and sensitivity

**Repeatability**, over repeated cells only: 21 pairs × each condition, all three runs completed.

| Model | Attack success: cells with disagreeing runs | User task: cells with disagreeing runs |
| --- | ---: | ---: |
| Qwen3-32B | 0 / 126 (0%) | 0 / 126 (0%) |
| Granite 4.0 H Small | 4 / 84 (4.8%) | 5 / 84 (6.0%) |

This is the first measurement of attack repeatability in this project. At temperature 0 it measures serving nondeterminism only.

**Sensitivity analysis** (all completed runs, each case the mean of its runs, equal weight per case):

- Qwen: identical to the primary analysis, since no run disagreed.
- Granite: primary +11.1 (+2.9 to +20.0); baseline +10.2 (+2.9 to +17.1); user task under the baseline −8.3 (−15.9 to −1.9).

The readings above do not change.

## Pilot-design section 9.8 (would a larger study be justified?)

| Condition | Qwen3-32B | Granite 4.0 H Small |
| --- | --- | --- |
| 1. Validity controls pass on development and pilot suites | Yes | Yes |
| 2. Runs disagree in at most 5% of repeated cells | Yes (0%) | Attack success yes (4.8%); user task no (6.0%) |
| 3. Projected task interval on the 60 reserved tasks ±6 or tighter | Yes (±5.7 on 21 tasks → about ±3.4) | Yes (±9.1 on 21 tasks → about ±5.4) |
| 4. Informative: primary interval excludes zero | Yes | Yes |

*Note 2026-11-16: condition 2 names no outcome. Read conservatively (any recorded outcome) it is not met for Granite, so section 9.8 does not justify the larger study as registered. See pilot design section 9.8a.*

Condition 3 scales by √(21/60) and assumes similar between-task variance on workspace and travel. It is a conditional planning assumption, not a guaranteed precision or a minimum detectable effect.

## Cost

| Pod | Lifetime | Estimate (listed $2.69/h + disk) |
| --- | ---: | ---: |
| Qwen3-32B `pxrrdap88tin5c` | about 82.5 min | $3.73 |
| Granite 4.0 H Small `1jlad7wd8u3l3o` | about 33.2 min | $1.50 |
| **Pilot** | | **about $5.23 of $20** |

These are estimates: billing had posted only part of Qwen's pod when this was written ($2.65 for 11:00 to 13:00, one bucket incomplete) and nothing for Granite. The in-pod expiries ($10.00 and $15.00 allocations) were never reached, and no expiry was extended. Both pods were deleted by the client right after their last phase (API 204; `list-pods` empty).

## Deviations and incidents, all stated

1. **Proxy disconnects.** Six `infra_error` episodes were rerun on resume (above). Qwen's first selection pass used `--fail-fast` and stopped after the first two of them; later passes used the registered default for these phases, without fail-fast, with a client-side guard that would have stopped the run at the first invalid or unverified delivery, prefix error or harness error. None occurred.
2. **Slow host for Qwen.** During selection, latency per call was about 2.2 times F1's for identical prompts and output lengths (`run_record.json`). Resuming a phase on another pod is not registered, so the phase continued on this pod.
3. **Granite's Slack client deadlines** were set at the in-pod expiry minus 3 minutes (section 9.6), not at 1.3 times the projection (section 9.5). The 1.3-times rule bounds spending, which the in-pod expiry already enforced, and for Granite it would have allowed 14 minutes for an evaluation projected at 11. Qwen's evaluation ran under the 1.3-times deadline (88.7 minutes) and finished in 30. Neither model's evaluation was cut by a deadline.
4. **A reporting bug, fixed after the runs.** When Granite's repeats were held back because one first run had ended in `infra_error`, the runner reported the hold-back as a deadline stop (exit code 3), though the deadline was 4.9 hours away. The behaviour was correct; the message was wrong. It now reports `held_back` separately. The repeatability table's share is now printed as a percentage, so a share of 1/21 no longer rounds to "0.0". Both fixes change reporting only; the reports here were regenerated with them from the unchanged traces.
5. **One pod session per model** (section 9.6c), with the freeze committed and pushed from the client before the first Slack episode.

## Files

- `qwen3-32b/`: `select/` (with `frozen_attacks.json`), `eval-controls/`, `evaluate/`, `report/`; `control_reuse_check.json`, `development_gates.json`, `evaluation_projection.json`, `serving_rendering_check.json`, `prompt_verification_*.json`.
- `granite-4.0-h-small/`: `dev-controls/`, `select/`, `eval-controls/`, `evaluate/`, `report/`; the same checks except the reuse check.
- `run_record.json`, `PROVENANCE.md`, `AGENTDOJO_LICENCE`.

The phase directories are byte-identical to what the runs wrote.

## Rebuild without inference

```bash
pip install -e ".[dev,pilot]"
pie pilot report --phase-dir results-published/pilot-f1-2026-11-16/qwen3-32b/dev-controls --phase-dir results-published/pilot-2026-11-16/qwen3-32b/select --phase-dir results-published/pilot-2026-11-16/qwen3-32b/eval-controls --phase-dir results-published/pilot-2026-11-16/qwen3-32b/evaluate --output-dir /tmp/pilot-qwen
pie pilot report --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/dev-controls --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/select --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/eval-controls --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/evaluate --output-dir /tmp/pilot-granite
pip install transformers   # tokenizer files only
python scripts/verify_pilot_prompts.py results-published/pilot-2026-11-16/granite-4.0-h-small/evaluate --repository ibm-granite/granite-4.0-h-small --revision b8c0982bab7fde4eb48110f5a069527c008fab39
```
