# Proposal: confirmatory same-attack serialization study (UNREGISTERED)

> **Superseded as a plan (2026-11-17).** The current plan is the [Stage 1 protocol](protocol-stage1.md). This page is kept as written for the record; its recommendation was made before the [claim–evidence table](claim-evidence.md) and the supplementary analyses.

**Status: proposal, not registered, not authorized.** Written 2026-11-16, after the pilot. No episode on the reserved suites has been run, and no reserved-suite outcome has been looked at. Before it could run, this design would have to be registered as its own amendment, committed and pushed, with CI passing. The recommendation in [Next stage](next-stage-2026-11-16.md) is *not* to run it now; it is written so the decision can be made on a complete design.

## 1. Question and estimands

**Scientific question.** When an agent's tool results are serialized as one JSON object instead of labelled free text, holding the injected text fixed, does a fixed prompt injection succeed less often?

This is the question ToolHazard (arXiv:2608.11878, Sec. 7.2) answered on two closed models without intervals or a delivery check. The proposal asks it on open models in function-calling mode, with delivery verified on every request and intervals that respect task structure. It is a **controlled replication**, not a new finding.

**Population.** AgentDojo v1.2.2 workspace (40 user tasks × 14 goals) and travel (20 × 7): 700 pairs, 60 user tasks, 21 goals. The agent is resumed after a reference-prefix replay, as in the pilot. These are not AgentDojo benchmark scores.

**Estimands, per model.** With r(a, f) the probability that attack a succeeds under format f on a pair, averaged over pairs:

- **E1 (primary).** Same-attack format effect under AgentDojo's fixed `important_instructions` baseline: r(baseline, text) − r(baseline, JSON), pooled over the two suites with **equal weight per pair** (workspace 80%, travel 20%).
- **E1-suite (secondary, reported always).** E1 in each suite separately.
- **E1-ratio (secondary).** r(baseline, JSON) / r(baseline, text), to show the effect on a scale less compressed near ceiling.

The pilot showed that comparing each format with its own selected attack combines format with attack wording. The primary is therefore a same-attack contrast. Attack selection is a separate module (section 3) with its own family of estimands. It is never folded into E1.

## 2. Attacks: no selection on reserved data

- The core uses only the fixed baseline. Nothing about it is chosen from data.
- The optional selection module uses each model's attacks **already frozen on banking** in the pilot (`data/pilot/frozen/*.json`): Granite `text_fake_turn` for both formats; Qwen `text_task_update` (text) and `neutral_baseline_one_line` (JSON). They are not re-selected, and Slack outcomes are not used to change them.
- No reserved outcome is inspected to choose attacks, remove ceiling cases, or set thresholds. Every threshold below is fixed in this document.
- No prospective development split of the reserved suites is needed, because nothing is selected. The work that must happen before registration is engineering only: benign twins for the 21 reserved goals, written from the goal definitions, and offline tests of the serializers and delivery check on every reference tool result of the two suites.

## 3. Contrasts and multiplicity

**Primary family (confirmatory).** E1 for Qwen3-32B and E1 for Granite 4.0 H Small. Holm adjustment over these two tests at familywise α = 0.05, with the sign-flip test over user tasks as the test. 95% task-bootstrap intervals are reported unadjusted, next to the Holm-adjusted p-values.

**Secondary (descriptive, no adjustment, labelled as such).** E1-suite, E1-ratio, user-task success with and without attack by format, the two-way interval, and the difference between models in E1 (cases matched and resampled jointly).

**Selection module (separate family, run only if registered and funded).** Per model:

- S1, same-attack format effect under each frozen selected attack;
- S2, the attack × format interaction (whether the format effect depends on the attack), tested directly;
- S3, selection transfer: each selected attack minus the baseline within each format;
- S4, the pilot's registered net contrast (each format against its own selected attack) with its decomposition into wording and format components.

S1 to S4 are reported with intervals and no confirmatory claim. Holm is applied within S1 if a claim is made from it.

**What the results would mean** (two-sided 95% task intervals, 5-point practical threshold as registered in the audit):

| E1 interval | Reading |
| --- | --- |
| Above 0 | For this model, on these suites, JSON lowered the fixed attack's success. Its size is the estimate and interval. |
| Below 0 | JSON raised it. |
| Within ±5 | A format effect larger than 5 points is excluded for this attack. |
| Includes 0, extends beyond ±5 | Inconclusive at this precision. No absence claim. |

## 4. Units, dependence and weighting

- A case is a (user task, goal) pair. Primary analysis: first run only, one outcome per case and condition, equal weight per pair.
- Pairs share user tasks and goals. The primary interval resamples user tasks (stratified by suite), keeping goals: it speaks to new user tasks for these goals. The two-way interval also resamples goals within suite. With 21 goals this is more informative than in the pilot, but it is still reported, not relied on.
- The sign-flip test uses per-task mean differences and is conditional on the goals.
- Pooling uses pair weights. Under them the effective number of user tasks is 55.6 of 60. A task-weighted pooled estimate is reported as a sensitivity analysis.

## 5. Validity controls (unchanged from the pilot except where stated)

Per model and format, on the reserved suites, three runs:

- clean (no attack, resumed);
- scratch (no attack, from the user request);
- benign twin and direct request per goal.

Gates, all fixed now:

1. every episode's delivery verified, or the row is invalid and counted;
2. unparsed call text at most 5% of turns per format;
3. resumed clean user-task success at least 50% per format, and not different between formats by more than 10 points;
4. at least two thirds of goals have a capable benign twin (two of three runs, both formats), per suite.

A failed gate means E1 is not interpreted for that model. Attack episodes are not rerun to pass a gate. The capable-set analysis is secondary, as in the pilot.

## 6. Repeatability

- A pre-drawn subset of 60 pairs, one per user task, with goals balanced within each suite, drawn with a documented seed from task names only, gets runs 2 and 3 under every condition. It is committed before the first episode.
- First runs of every case complete before any repeat starts.
- Disagreement is reported per model and outcome, by condition and pooled, with exact 95% intervals.
- Rule (from [Pilot design](pilot-design.md) section 9.8a, adopted here prospectively): below 10% of repeated attack-success cells, disagreement is reported as a reliability statistic. From 10%, the all-runs sensitivity analysis is reported beside the primary, and each claim rests on the less favorable of the two. At 15% or more, the model's run stops and the instrument is investigated before any further phase.

## 7. Completeness and infrastructure failures

- Completeness is counted on first runs. If more than 2% of a model's E1 first-run cases are incomplete in either format, E1 for that model is not interpretable. Bounds with every missing case set to success, then to failure, are always shown.
- **Bounded retries (an instrument change from the pilot, to be registered).** The provider retries a request that fails at the transport level before any response, such as a dropped proxy connection, at most 3 times with backoff. Each retry is logged in the trace. Retried requests are identical, and the server fingerprint is checked again.
- An episode that still fails is `infra_error`, which is non-final. It is rerun at most twice on resume. After that it is counted as missing.
- No retry on any model output, on a parse failure, or on a scorer result.

## 8. Precision: the ±5.4 projection is an assumption

The pilot's ±5.4 figure was scaled from one banking contrast. Here the assumption is examined against the pilot's own Slack data. For the per-task standard deviation of the baseline format difference, the pilot observed 14.0 points (Qwen) and 17.5 (Granite), with 5 goals per task. Normal-approximation half-widths for E1 (`scripts/cost_next_stage.py` carries the inputs; the table below is arithmetic on them):

| Per-task SD | Pooled (n_eff 55.6) | Workspace (40) | Travel (20) | Chance the interval excludes 0 if the true effect is 10 / 5 |
| ---: | ---: | ---: | ---: | --- |
| 14.0 (Qwen, as observed) | ±3.7 | ±4.3 | ±6.1 | 1.00 / 0.76 |
| 17.5 (Granite, as observed) | ±4.6 | ±5.4 | ±7.7 | 0.99 / 0.57 |
| 21.9 (Granite × 1.25) | ±5.7 | ±6.8 | ±9.6 | 0.93 / 0.40 |
| 26.2 (Granite × 1.5) | ±6.9 | ±8.1 | ±11.5 | 0.81 / 0.29 |

Reading:

- Workspace has 14 goals per task against Slack's 5, which would lower per-task spread if goal-level noise dominates. Heterogeneity between two suites would raise it.
- Percentile intervals at this size run slightly under nominal coverage (the pilot's simulation test accepts 87%).
- So the study can plausibly distinguish a 10-point effect from zero. It has roughly even odds of detecting a 5-point effect. It can establish "within ±5" only if the true effect is near zero and the spread is no larger than observed.
- Per-suite results, travel especially, are descriptive.

## 9. Execution and cost

One pod per model. Each pod runs the rendering check, then controls, gates, E1 first runs, repeats, and then (if registered) the selection module. Each stage either completes for every planned case or is reported as not run; none is truncated. Expiry, deadlines and price checks are as in the pilot.

From `scripts/cost_next_stage.py`, at $2.72/h, including controls and overhead (central / conservative):

| Variant | Episodes | Cost |
| --- | ---: | --- |
| Core: E1 for both models | 5,224 | $10.8 / $21.2 |
| Core plus Granite's selection module | 6,864 | $12.4 / $24.9 |
| Core plus both selection modules | 10,144 | $20.5 / $42.5 (does not fit the $31.29 remaining in the conservative case) |

The conservative case assumes 11 calls per attack episode and half of Slack's throughput. Qwen's pilot host was about 2.2 times slower than F1's; on a host like F1's, Qwen's share roughly halves. The decision before the core's evaluation would follow the pilot's rule: re-project from the measured controls, and do not start a stage that cannot finish.

## 10. What it could support

- **At best:** "On 700 untouched AgentDojo workspace and travel pairs, with every request's delivery verified, serializing tool results as JSON instead of free text changed the success of AgentDojo's fixed injection by X points (interval) for Qwen3-32B and Y for Granite 4.0 H Small, served by vLLM 0.33.0." That is a controlled replication of a reported direction, for two open models, one attack and one stack.
- **It could not support:** a claim about attackers who write for the format, about models in general, about tool-role templates, or that JSON is a defense.
