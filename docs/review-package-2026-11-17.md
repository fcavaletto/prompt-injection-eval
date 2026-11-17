# Review package, 2026-11-17 (offline)

**What this covers.** The work on branch `offline-package-2026-11`, started from `b33750d`.

- **Authorized:** offline analysis, code repairs, tests, documentation and experiment preparation.
- **Nothing paid.** No model was called, nothing was rented, nothing was published, released or merged, and no external message was sent.
- **Price and pod reads.** The GPU price list and the pod list were *read* from RunPod. Both are free reads; no pods exist.
- **Preserved.** Raw evidence and the original pre-registrations are unchanged.

## 1. Correction and response matrix

Full table: [claim–evidence table](claim-evidence.md), section 2; new corrections C18 to C24 in [Corrections](corrections.md).

| Review point | Verdict | Action | Archived outcomes |
| --- | --- | --- | --- |
| WP7 accepts parameter-name and scalar-type mutations | confirmed (20/20 accepted) | `wp7.check(strict=True)`; C18 | unchanged: all five stored renderings pass strict |
| Pilot checker does not verify role delimiters | confirmed, plus duplicates, int/float/bool, generation header | `check_contract`; C19 | unchanged: all 21,321 scored turns hash-match the pinned template |
| Free text is ambiguous; its decoder gets the shape | confirmed | contract §4; `quoted` representation for Stage 1; C20 | unchanged; affects interpretation |
| Context-overflow causation unproven | confirmed as unproven (already a hypothesis) | kept as a limitation | n/a |
| SecAlign bounds overlap on workspace/`direct` | confirmed; README and report did not qualify | C22 | n/a |
| Prompt verification: scored vs aborted | confirmed | precise counts; C21 | unchanged |
| Component reconstructions ≠ end-to-end certification | confirmed | C23 | n/a |
| Review 3: "only multiline attacks benefit from JSON" | unsupported for Qwen (one-line `json_field_mimic` +19.4, `json_single_line_authority` +15.3); its aggregate omitted `json_field_mimic` | all attacks and both groupings reported | n/a |

## 2. Regenerated analysis tables

Everything comes from one entry point, `scripts/pilot_supplementary.py`, and everything is exploratory. Outputs and definitions: [supplementary-2026-11-17](https://github.com/fcavaletto/prompt-injection-eval/tree/main/results-published/pilot-2026-11-16/supplementary-2026-11-17).

**Reproduction checks (all match):**

- Qwen primary, wording and format: 8.5714, 7.1429 and 1.4286.
- Granite Slack baseline: 67/105 against 57/105.
- Granite banking baseline: 47/72 against 35/72.
- Granite banking twin: 20/72 against 28/72.
- Baseline and twin payloads: equal after whitespace normalization on all 144 matched banking cases per model and all 210 Qwen Slack cases. None is byte-identical.

**Banking, text minus JSON** (points, task interval):

| Attack | Multiline | Qwen | Granite |
| --- | :---: | ---: | ---: |
| baseline | yes | +16.7 (+6.8, +28.0) | +16.7 (+2.7, +31.9) |
| text_task_update | yes | +31.9 (+14.5, +48.7) | +19.4 (+4.1, +35.5) |
| text_fake_turn | yes | +31.9 (+18.9, +45.1) | +9.7 (−2.7, +22.4) |
| text_end_of_output | yes | +16.7 (+4.2, +29.7) | +4.2 (−4.2, +13.4) |
| json_field_mimic | no | +19.4 (+8.5, +31.0) | +2.8 (−8.3, +14.9) |
| json_single_line_authority | no | +15.3 (+2.8, +27.4) | −5.6 (−14.1, +2.7) |
| json_key_value_prose | no | −4.2 (−11.3, +2.8) | +2.8 (−2.7, +8.2) |
| neutral_pass_on | no | +2.8 (−5.6, +9.9) | −4.2 (−11.4, +2.7) |
| neutral_baseline_one_line | no | +1.4 (−7.9, +12.7) | −11.1 (−18.9, −4.2) |

**Twin interaction**, the baseline's format effect minus the twin's:

- Qwen banking: +15.3 (+1.3 to +28.8).
- Granite banking: +27.8 (+12.3 to +44.0).
- Qwen Slack: +0.9 (at ceiling).

**Round limit.** Granite's Slack baseline reached the 15-round limit in 23 of 105 text episodes and 10 of 105 JSON episodes. 7 of the 10-success gap lies in those episodes. They are kept as finite-budget outcomes.

**Joint outcomes.** Under JSON, Granite's Slack episodes moved from "attacked" to "resisted with the task done", not to "resisted with the task failed".

**Repeatability.**

- Granite also disagrees in its controls: 6/104 and 4/100 cells.
- Qwen never disagrees.
- First-run and all-run denominators are in separate tables.

**Prompt verification, precisely.**

- All 21,321 turns of scored episodes match the pinned template's rendering.
- The published 21,327 includes 6 turns of superseded traces.
- 11 turns of superseded traces cannot be rebuilt.

## 3. Checker validation

[Measurement contract](measurement-contract.md); [results](https://github.com/fcavaletto/prompt-injection-eval/tree/main/results-published/checker-validation-2026-11-17).

**Order of work.** The expected verdicts and the unchanged checkers' results were committed in `15a2279`, before any checker changed (`aadf5da`).

| Class | Should reject | Archived pilot check | Contract check |
| --- | ---: | ---: | ---: |
| valid (false alarms) | 0 of 24 | 0 | 0 |
| role | 24 | 0 | 24 |
| schema | 16 | 16 | 16 |
| arguments | 20 | 12 | 20 |
| duplicates | 12 | 0 | 12 |
| order | 12 | 12 | 12 |
| association | 8 | 8 | 8 |
| truncation | 16 | 12 | 16 |
| payload | 14 | 14 | 14 |
| WP7 W1 to W4 / valid W0 | 20 / 0 of 5 | 0 / 0 | 20 / 0 |

**Further checks:**

- **Real prompts.** All 787 real kept prompts pass the contract check. In the 404 text prompts, the record items were skipped and counted.
- **Valid variants.** The 12 valid variants are byte-identical to the pinned tokenizers' output.
- **Regression tests.** `tests/test_checker_contract.py` covers every corpus case, every demonstrated counterexample (including the archived checks' gaps) and the free-text collisions.

**Scope of the claim.** Coverage is narrowed to the tested classes and two templates.

## 4. Repository navigation

- **README** rewritten as question, method, findings, limitations, reproduction, then entry points.
- **[Historical overview](history.md)** keeps the previous README and home page verbatim, with links rewritten and dated notes.
- **New entry points:** [claim–evidence table](claim-evidence.md) and [evidence index](evidence-index.md).
- **One current plan:** [Stage 1 protocol](protocol-stage1.md). Three earlier plans carry a "superseded" banner.
- **Docs navigation** grouped into Current, Plans, Methods, History and Background.
- **Not changed:** no raw results moved, and no package-wide refactor.

## 5. Next-study protocol

[Stage 1 protocol](protocol-stage1.md). In short:

- **Model:** Granite only.
- **Pairs:** 24 development pairs from an outcome-blind seeded draw. The 12 banking pairs come from the half no model has run; the 12 Slack pairs are pairs where the twin was never run on Granite.
- **Conditions:** instruction twins × six (carrier, context) conditions over text, quoted and JSON × two independently scheduled batches = 576 episodes.
- **Forged data:** 120 feasibility episodes on five pathways, each verified against AgentDojo's own checks.
- **Controls:** 162 clean controls.
- **Total:** 858 of 960 allowed.
- **Explanations it separates:** escaping, container syntax, global reading, family-specific suppression, and instrument noise. Each reading is decided by effect thresholds and validity checks, not a p-value.

The [adaptive follow-up](protocol-adaptive.md) keeps same-payload crossover (S) apart from budget-matched, independently selected attacks (A), and states how a failed search is told apart from an inadequate attack.

## 6. Cost and launch proposal (not authorized)

**Price:** $2.69/h, RTX PRO 6000 Blackwell Server Edition, Secure cloud. Read from RunPod `list-gpu-types` on 2026-11-17, availability HIGH. `list-pods` showed no pods.

**Measured inputs** (pilot):

- Granite throughput: 7.09 to 8.21 calls/s.
- Calls per episode: 2.1 to 7.4.
- Startup: 6.0 minutes.

| | Central | High | Proposed cap |
| --- | ---: | ---: | ---: |
| Stage 1 (858 episodes; two sessions; startup, idle, shutdown margin, reruns, disk included) | $1.74 (39 min) | $5.56 (123 min) | **$8** |
| Adaptive follow-up (3,024 victim episodes; co-hosted attacker) | $4.25 (94 min) | $15.85 (351 min) | **$18**, only after Stage 1's progression rule is met |

- **Budget.** Both caps together come to $26 of the $31.29 that remains.
- **Against the provisional estimate.** That was $5–10 with a $15 cap. The measured central case is lower, because Granite ran at about 7 calls/s in the pilot.
- **Launch order** (protocol §9):
  1. finish L4 to L6, offline (about one day);
  2. register Amendment 4;
  3. human review (L8);
  4. re-read the price, then approval.

## 7. Human-review checklist

[Reviewer checklist](review-checklist.md), new sections:

- **G. Attack realism, scoring and design:** whether each forged field reads as data, equal control, twins, goal scoring, the outcome-blind draw, the description of the representations, and the progression rule.
- **H. Checkers and recomputed tables:** the order of verdicts and checker changes, re-running validation, re-deriving the banking counts.

## 8. Acceptance, and the endpoint of this offline stage

| Criterion | Where |
| --- | --- |
| Every current headline maps to evidence | claim–evidence table, section 1 (H1 to H18); README findings |
| Registered and exploratory analyses distinguishable | status column; "exploratory" header and status in every new output |
| Known checker counterexamples covered | `tests/test_checker_contract.py` |
| The next experiment discriminates between explicit explanations | Stage 1 §1 and §6 |
| No paid work started | ledger unchanged; no pods (`list-pods`, 2026-11-17) |
| A finite endpoint | this page. Remaining before any launch: L4 to L6 (offline, about one day), then the author's decisions. Nonblocking historical uncertainty (context-limit causation, WP7 provenance, mirrored templates) stays a limitation, with no new audit |

**Decisions for the author:**

1. Accept or revise the Stage 1 protocol, and register it.
2. Authorize Stage 1 spending, up to the proposed $8, after L4 to L8.
3. Arrange the independent human review.
4. Merge this branch, which was not done.

## 9. Addendum: launch package (later on 2026-11-17)

Still offline: nothing run, nothing paid. The configuration (`src/`, `data/`) is frozen at `3e3e3dd`; later commits do not touch it.

**Stage 1, ready to run.**

- `pie stage1 plan/run/report`, with analysis and progression rules.
- Registered as [Amendment 4](preregistration.md). Its manifest is `data/stage1/manifest.jsonl`: 858 lines, SHA-256 `596f848d…e261`.
- Primary contrasts P1 to P3, secondary S1 to S8 with U, B and F, exploratory per-round measures.
- Batches stay inside their pair.
- Data roles: Stage 1's pairs become development data, and `held-out-evaluation-v1` (workspace and travel) is untouched.

**Per-round rescoring.**

- Rounds are defined as a response plus its tool-call batch, with a per-call variant.
- States come only from replaying recorded calls, never from narration. All 4,062 archived attack episodes verify by final-state hash.
- "Not successful within the observed budget" is kept apart from "would never succeed".

**Two scoring findings.**

- **C25:** three Granite episodes were scored with unexecuted calls. New runs score executed calls only.
- **H19:** goal predicates can miss real unauthorized actions. One episode paid the attacker $1,100 and was scored "not attacked".

**Reporting.**

- Prompt-verification populations are reconciled ([contract](measurement-contract.md) §6): 21,321 rest on reconstruction, and 787 on retained prompts.
- Mutation results are stated as evidence against the tested fault classes only.
- Forged-data pathways have a threat-model table with reachability and validity judged separately ([Stage 1](protocol-stage1.md) §4).

**OpenRouter screen.**

- [Protocol](protocol-openrouter.md). Identifiers, endpoints, parameters and prices come from current metadata.
- 5 eligible cases, not 24, so 60 episodes plus 4 calibration.
- The adapter pins routing, guards spending, records everything except credentials, and verifies delivery at request level. It is tested offline with mocks.

**Spending.** One [proposal](spending-proposal-2026-11-17.md) with three gates: $8 (Stage 1), $5 (screen) and $18 (adaptive, conditional).

**Review.** A [human-review packet](human-review-packet.md) with concealed expected verdicts; answers SHA-256 `36ba20b5…f0ed`. No one has been contacted.
