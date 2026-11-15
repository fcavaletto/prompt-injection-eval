# Research audit and next step

First written on 2026-11-14, after Studies A and B. **The pilot's design in section 3.4 is superseded by [Pilot design](pilot-design.md), which is registered as Amendment 2 and has a working harness.** **Revised on 2026-11-15** after the closest papers were read in full and a [rendering census](rendering-census.md) was run. Sections 2.3 onward are new; the 2026-11-14 text of those sections is in the repository history (commit `31b63c5`). The revision changes the recommendation: see section 3.

This page audits the evidence so far, places it against the closest literature, and proposes the next experiment. Nothing here was run on a paid GPU. Every new analysis of existing results is **exploratory**: it was written after the outcomes were known. The original results and the [pre-registration](preregistration.md) are unchanged; this page and its [appendix](research-audit-2026-11.md) are dated additions.

## 1. Publication readiness

**Not ready for a main-conference submission.** The project has an honest record (two pre-registered studies, both reported against their own criteria) and one result that reproduces across ten models on synthetic data. It does not yet have a contribution a reviewer could not get from prior work, and this audit found defects that weaken parts of what is published.

What stands in the way, most serious first:

1. **Two of ten models were not validly measured as agents.** In Study B, Phi-4-mini's chat template rendered no tool definitions, so the model never knew any tool existed. Granite 3.3's template dropped the completed tool call, leaving an empty assistant turn. The write-up attributed their zeros to behavior. For the two gpt-oss models no rendered prompt was stored for any row, so what they saw cannot be checked.
2. **The headline causal claim outruns its controls.** "It is the role, not the position" compares conditions that differ in at least seven ways. On Qwen, the tool result is rendered inside a *user* turn, so the role token does not even change.
3. **Inference treats dependent cases as independent.** InjecAgent's 2,108 cases are 17 user contexts crossed with 62 attacker goals and 2 wordings. Design effects for the placement contrast run from 3 to 28.
4. **The outcome on the external benchmark is a tool name,** on single-turn cases, with no positive control showing the model can call a tool when it should.
5. **No capable agent has been tested.** The models are small or mid-sized, and nothing is scored by what happens in an environment.
6. **The serialization result is not novel.** ToolHazard (2026) reports that free-form tool output is attacked far more successfully than JSON or YAML on GPT-4.1 and Gemini-3.1-Pro, with numbers (52.6% against 5.9% in one cell). *Corrected 2026-11-15: the first version of this page said that paper gave no numbers. They are in a figure that had not been read.*
7. **Human validation has not happened.** No rater has been recruited and no row has been labelled by anyone but the author reading results. A [protocol and a blinded sample](annotation-protocol.md) are prepared.

What is worth building on: the project found, by accident and then by design, that the layer which turns a conversation into a prompt (chat template, serving stack, harness encoding) changes measured robustness and can silently invalidate a measurement. *Corrected 2026-11-15: the first version said no paper studies that layer. Several do, for capability and for benchmarks in general (section 2.3). What is open is narrower.*

## 2. Evidence audit and novelty

### 2.1 What the evidence supports

| Finding | Status | Support | Main threat |
| --- | --- | --- | --- |
| A tuned strategy defeats a generic security rule on held-out documents (46 to 58 of 59, ten models) | Replication of a known result (Nasr et al. 2025; Zhan et al. 2025) | Strong within scope | 24 hand-written strategies, canary-style goals |
| With the rule, the plain override succeeds more in a raw tool result than in the user message, on synthetic documents (ten of ten models; pooled +44 points, two-way interval 30 to 58) | Exploratory, then reproduced in one later session | Strong as a description of two prompt constructions | Not a role effect; two models had malformed tool turns; one author's 89 documents |
| JSON-encoding the same text lowers plain-override success | Pre-registered (Study A): verdict *mixed* | Pooled, exploratory: −25 points in the tool result, and −23 in the user message without the rule | Canary goals; not attacked adaptively; partly anticipated by ToolHazard |
| "JSON's effect is specific to the tool channel" | Pre-registered reading of A3 | **Not supported on re-analysis.** Relative reductions are similar in all four cells (27% to 40%); without the rule there is no interaction (−1 point, interval −14 to 12) | The with-rule difference is plausibly a floor effect |
| "Removing line breaks contributes nothing" | Exploratory reading in the write-up | **Too strong.** Pooled, flattening lowers success by 6 points (interval −11 to −1.5); nine of ten models go down, none up | Per-model tests could only detect differences of 11 or more seeds |
| On InjecAgent the placement effect appears only in Qwen3 | Pre-registered (Study B): *does not replicate* | The non-replication stands. Under clustering by user context, 3 of 4 Qwen3 models keep an interval above zero (2 after Holm adjustment) | One model family; task-state confound; tool-name outcome |
| A security rule can *raise* harmful tool calls (Qwen3-8B 82 to 357, Hermes 3 705 to 1,040, Qwen2.5-7B 419 to 531) | Exploratory, found in this audit | In the user message, survives clustering by user context (p ≤ 0.0007) | The rule ends with "complete the original task", which may simply prompt more tool calls |
| A serving stack changed a published conclusion (gpt-oss, 0.5.0 to 0.6.0) | Case study | One clean instance, documented with both rendered prompts | Laptop and server also differed in quantization and runtime |

Study B is the only replication attempt on external data, and it failed its criterion. Nothing has been replicated across runs except two models in one repeat, and nothing across serving stacks.

### 2.2 The review concerns

Each is examined in the [appendix](research-audit-2026-11.md) with the evidence. Summary:

| Concern | Judgment | Severity | Smallest effective remedy |
| --- | --- | --- | --- |
| Causal attribution to "role" | **Correct, and understated.** The conditions differ in wrapper, delimiters, labels, rule wording, rule distance, an added assistant turn and offered tools. On Qwen the role token is `user` in both. | High | Withdraw the word "role". Define the intervention as the rendered conversation, and vary one rendered feature at a time. |
| Significant here, not significant there | **Correct on method.** Tested directly, the JSON-by-placement interaction with the rule *is* large on the additive scale (−20 points, ten of ten models). The reviewer's deeper point still wins: it vanishes without the rule and on the ratio scale, so the "tool-specific" reading is wrong for a reason the reviewer did not give. | Medium | Pre-register interaction contrasts and the scale. Report equivalence only against a stated margin. |
| Absence claims | **Correct.** Only the gpt-oss "no effect" result fits inside ±5 points, and only because its base rate is 2%. Qwen2.5-7B's interval is −6.2 to 1.8. | Medium | Stated margin; relative as well as absolute effects when base rates are low. |
| Dependence in InjecAgent | **Verified exactly:** 17 user instructions, tools and argument sets; 62 attacker goals; 2 wordings; fully crossed. One correction: because the design is crossed, there are 62 clusters on the attacker side, and contrasts within a user context are well estimated. The limit is generalizing to new user tasks. | High | Two-way cluster bootstrap as the primary interval; sign-flip test over user contexts as a check; claims about new tasks only at that level. |
| Four Qwen3 sizes are one family | **Correct.** Of the three families with valid, checkable conversations, the effect appears in one. | High | Count families, not checkpoints. Choose models for contrast between families. |
| Measurement validity | **Correct, and worse than stated** (item 1 of section 1). The benign smoke test produced no parsed call on nine of ten models, so nothing showed the interface worked. One point in the measure's favor: when a direct-harm instruction names specifics, 77% to 98% of the attacker calls carry them, so the tool name is a fair proxy there. Data stealing is scored on a read, not on exfiltration. | High | Positive controls before any attack outcome; a rendered-prompt check on every row; outcome-level scoring; human validation of a stratified sample. |
| Reproducibility | **Correct on every point.** No model or tokenizer revision, no template hash, an image tag instead of a digest, no dependency lock, and resume keys that ignore the prompt and the serving flags. | Medium | Pin and record all of them; fingerprint every request. The InjecAgent runner now does the last part (section 4, WP0). |

### 2.3 Novelty, after reading the closest work directly

The appendix lists [what was read and how](research-audit-2026-11.md#d-literature-re-verified-on-2026-11-15). The table gives the experiment in each paper that comes closest to this project.

| Prior work | Closest result, with its location | What it leaves open |
| --- | --- | --- |
| Mou et al., *ToolHazard* (arXiv:2608.11878) | Sec. 7.2, Fig. 4: free-form tool output against JSON and YAML. GPT-4.1: 52.6% against 5.9% and 1.2% for one attack, 80.4% against 62.0% and 75.6% for another. Gemini-3.1-Pro: 4.7% against 2.4% and 3.5%, and 77.7% against 40.5% and 32.6%. | No intervals; 87 tasks; formats undefined in the paper and not reproducible from the released code; prompt mode only; fixed attacks; no test of the proposed reason |
| Tang and Zheng, *Measuring the Serving Stack Instead of the Model* (arXiv:2609.26693) | Sec. 4 and Table 2: four serving stacks handle the same tool request four ways; a refused request is recorded as a model at 0% (Sec. 5); a checklist (Sec. 7) | Covers emitting a call, not how a tool result is rendered in the history; capability, not security |
| Shaw, *Silent Failures* (arXiv:2609.32691) | Sec. IV and Table I: undelivered payloads, tool-name scoring (21.7% against 1.2%), incapacity scored as defense; Sec. VII-C: a model that cannot call tools is unmeasurable, not secure | Checks delivery in the environment, not in the prompt; no templates or stacks |
| Pape et al. (arXiv:2605.19537); Masoudian et al. (arXiv:2608.04714); Yao et al., *Harness-Bench* (arXiv:2605.27922) | Backend or harness alone moves benchmark results (abstracts; Masoudian Sec. 1) | Not security; not tool results |
| Ye et al., *Prompt Injection as Role Confusion* (arXiv:2603.12277) | Sec. 4.2, Table 1: user-sounding text stays 76% to 88% "user" inside tool tags. Sec. 5.2, Fig. 10 and App. J: the attacker's framing moves success from 2% to 70% on gpt-oss-20b; tool-like and JSON-like frames score lowest | Attacker-side framing, one model for behavior; nothing about the defender's or harness's serialization |
| Chang et al., *ChatInject* (arXiv:2509.22830) | Sec. 4.1, Table 1: payloads wrapped in the model's role tags; Sec. 5.1: transfer by template similarity | Serving stack unknown (hosted providers, App. D); whether tags arrive as control tokens is not reported |
| Yu et al. (arXiv:2601.04795) | Sec. 3.3: a model call extracts needed fields from tool results | A filter, not a serialization |

**What would a reader learn from the proposed paper that these papers do not already establish?** Three things, and today none of them is established by an experiment:

1. *What the tool-result path actually is* across the templates and stacks this literature uses. The census shows it for 18 templates and 11 Ollama entries. This is descriptive.
2. *Whether the format effect that ToolHazard reports holds under control*: in function-calling mode, with the rendered prompt verified for every row, on paired cases with intervals that respect the task structure.
3. *Whether it survives an attacker who writes for the format.* ToolHazard recommends structured output as protection. With fixed attacks that recommendation is untested.

Separating what this project has into the four kinds that were asked for:

| Kind | What belongs here | Is it a research contribution? |
| --- | --- | --- |
| **Defects in our own harness** | Phi-4-mini run without tool definitions; Granite 3.3 without completed calls; gpt-oss prompts not stored; no positive control; resume keys that ignored the prompt; success scored by tool name | No. They are corrections to our record. They are worth reporting because they were silent, but a reader of Tang and Zheng or of Shaw already knows this kind of failure exists. |
| **Known classes of defect** | A capable model measured at zero because of the serving layer (Tang and Zheng); incapacity mistaken for security and success scored by tool name (Shaw); format changes attack success (ToolHazard); backend changes scores (Pape et al.) | No. Citing them correctly is the contribution. |
| **Potentially new empirical findings** | (a) The census: the same family rendered differently by its Hugging Face and Ollama templates, down to the role token; four templates JSON-encoding tool output themselves; tool results carried in at least five different constructions. (b) InjecAgent's crossed structure and its design effects of 3 to 28. (c) A security rule raising attacker tool calls on three models. | (a) is new as far as the papers read go, and modest. (b) and (c) are exploratory and unverified as novel. None is a paper by itself. |
| **A general method** | A prompt-level delivery check: marked fixtures rendered through the real template, with string checks for definitions, calls, results and payload, run before a study and recorded on every row | A small extension of Shaw's environment-level checks to the last point before the model. It has found defects only in this project so far. Its value would be shown by running it against other public harnesses. |

**The strongest defensible novel contribution today: none is established.** The project has a corrected record, a descriptive census, and a check that others could use. That is a methods and replication contribution. A research contribution would have to come from item 2 or 3 above.

### 2.4 What the census adds to the decision

Full results: [rendering census](rendering-census.md). The parts that change the plan:

- **"Raw" and "JSON" are not things a harness controls.** On Llama and gpt-oss templates a string is JSON-encoded by the template. The intervention has to be defined, and verified, in the rendered prompt.
- **Two of the four models proposed on 2026-11-14 cannot be used as proposed.** Mistral Small 3.2 ships no template that could be observed. GLM-4-32B's template drops both the call and the result. gpt-oss cannot be verified on vLLM because that path returns no prompt.
- **Qwen3 and Granite 4.0 can.** Both render definitions, calls and results, pass tool output through verbatim, and for Qwen3 the server's prompt is known to equal the local rendering.
- **The check works as a gate.** It reproduced the two Study B defects from pinned template revisions, and found silent drops of the same kind in three other templates (Phi-3-mini, GLM-4-32B, Kimi K2).

## 3. Decision on Study R

### 3.1 Recommendation

**Narrow Study R to one question and run only its pilot. Treat what exists as a methods and replication contribution whatever the pilot shows. Do not plan a main-conference submission on this line until the pilot and a free audit of other harnesses (section 4, WP7) have reported.**

The 2026-11-14 design asked whether rendering changes attack success by as much as a defense, across four families. Two things make that the wrong study now. ToolHazard already shows the direction, with larger effects on stronger models, so a positive result would be a replication with better statistics. And the wide design spends most of its budget on breadth across families before it is known whether the effect survives an attacker, which is the only version of the question that bears on safety.

The narrowed question: **when tool output is serialized as JSON instead of free text, does an attacker who writes for that format succeed less often?**

This is not chosen because it is likely to produce a striking result. It is chosen because the comparison has not been made with attacks selected for each format. *Revised 2026-11-15:* an earlier version of this paragraph said what a "no" and a "yes" would mean in general. A pilot with two models, five attacker goals and a library of eight candidates supports neither reading. What it can support is stated in [Pilot design](pilot-design.md), section 5.

### 3.2 What needs adapted attacks and what fixed attacks can answer

| Claim | Attacks needed | Why |
| --- | --- | --- |
| Results from harnesses that serialize differently are not comparable | Fixed | It is a statement about existing static benchmarks, which use fixed strings |
| A published static number depends on serialization | Fixed | Same |
| JSON protects, or one format is safer than another | Adapted to each format | A fixed string may simply be worded for one format. Only an attacker who has seen the format tests the format. |
| A deployer should prefer one format | Adapted to each format, plus utility | It is a defense claim |
| Why the format matters | Neither alone | Needs the components varied separately. Not in the pilot. |

"Adapted to each format" means: the same budget of candidate attacks is tried against each format separately on development tasks, the best one per model and format is frozen, and each evaluation case gets one attempt with no feedback.

### 3.3 Thresholds and precision, for this question

- **Practical threshold: 5 points of attack success, absolute.** In Study B, with the document in the user message, the security rule moved attack success by 3 to 17 points in absolute size across the eight models that made calls, about 11 at the median. A format effect under 5 points is smaller than most of those and could rarely reorder a comparison of defenses. One above 10 is as large as a typical prompt defense. ToolHazard's reported gaps run from 2 to 47 points.
- **Required precision for a confirmatory claim: a 95% interval no wider than ±4 points** on the paired difference, so that an estimate near zero can exclude ±5 and an estimate near 10 can exclude 5.
- **Feasibility rule 1, base rate.** The contrast is only estimable on a model where the fixed attack succeeds between 10% and 90% of the time on free text. Outside that range a small difference is a floor or ceiling, not evidence.
- **Feasibility rule 2, projected precision.** The pilot estimates the variance between user tasks, between attacker goals and between repeated runs. If those imply the confirmatory interval would be wider than ±6 points with the cases available, the study needs more cases (a newer benchmark version, or a second benchmark) or its claim is restricted to effects of 10 points or more.

No ranking reversal, no minimum number of significant families, and no minimum effect size is required for the result to be worth reporting. A well-estimated zero is a result.

### 3.4 The pilot

**Primary estimand.** For one model, on the pilot evaluation cases: the paired difference in attack success between free-text and JSON tool output, when each format faces the attack adapted to it. Attack success is AgentDojo's check on the final state of the environment.

**Reported with it.** The same difference with the fixed attack (the comparison ToolHazard made); the user task's success under each format with and without attack; the two validity controls below.

**Intervention.** How every tool result is serialized in the prompt: free text, or the same record as one JSON object. The serialization is confirmed in the rendered prompt of every row. A row whose prompt does not contain the payload, the tool definitions and the completed calls is excluded and counted.

**Held fixed across the two formats.** The model and server; the system prompt; the tools; the user task; the attacker's goal; and the conversation up to and including the tool result that carries the injection. That prefix is built by replaying the benchmark's reference calls, so both formats start from the same state and differ only in serialization. From there the agent runs freely against the environment.

**Controls that must pass before any attack number is read, per model and format.**

- *Authorized behavior.* Each attacker goal is also given as an ordinary user request. If the model cannot or will not do it when the user asks, attack success on that goal says nothing; such goals are excluded and listed. At least two thirds of goals must pass.
- *Reading the format.* User-task success without attack must be at least 50%, and must not differ between formats by more than 10 points. Otherwise JSON may be lowering attack success by making the output unreadable.
- *Parser validity.* At most 5% of assistant turns contain call-like text that the server did not parse; zero rendering defects.
- *Sensitivity.* The fixed attack must succeed more often than no attack by a margin whose interval excludes zero. If the instrument cannot see an attack, it cannot see a format effect.

**Data.** AgentDojo, version to be pinned. Banking (144 task pairs) is development: harness debugging, attack selection, every threshold. Slack (105 pairs) is the pilot's evaluation set, read once after the harness and attacks are frozen in a commit, and not reused. Workspace and travel (380 pairs) stay untouched for a confirmatory study.

**Attacker budget.** Eight candidate wordings per format, written before the run, tried on half of the banking pairs. The best one per model and format is frozen. One attempt per evaluation case. No access to gradients or to evaluation outcomes. This is a weak attacker, and the write-up will say that "survives" means "survives this budget".

**Models.** Qwen3-32B and Granite 4.0 H Small. Both passed the census, they come from different developers, and both fit one rented GPU. Both carry tool results in a user turn, so the pilot says nothing about templates with a dedicated tool role. gpt-oss is left out until its prompt can be read from a server.

**Analysis.** Each case is run three times; outcomes are averaged within case first. Cases are user tasks crossed with attacker goals, so intervals come from a bootstrap that resamples both, with a sign-flip test over user tasks as a check. The share of cases whose outcome changes between repeated runs is reported. Models are reported separately; two models support no claim about models in general.

**First 20 minutes of the session.** Send the census fixtures to the server and compare the returned prompt with the local rendering. If they differ, stop and fix before spending more.

### 3.5 Reading the pilot

The pilot is too small to settle the question. Its jobs are to show the instrument works, to measure variance, and to say whether a confirmatory study can reach the precision above. The decision afterwards follows what the intervals allow, not which side of a line the estimate fell.

| What the pilot shows | What it means | Next |
| --- | --- | --- |
| A control fails | Nothing about the question | Fix the instrument or change the model. Not counted as a null. |
| Fixed attack outside 10% to 90% on free text | The contrast cannot be read on this model | Use a different fixed attack from the benchmark, or a different model |
| Controls pass; interval for the adapted-attack difference lies inside ±5 | On these cases, effects that would matter are ruled out for this attacker | Check whether one attacker goal hides a large effect. If not, report as a null with its interval and stop this line unless a stronger attacker is affordable. |
| Controls pass; interval excludes zero and is centered above 5 | The effect probably survives this budget | Run the confirmatory study; strengthen the attacker first |
| Controls pass; interval is wide enough to include both 0 and 10 | The pilot is uninformative about the effect | Use its variance estimates in feasibility rule 2. Proceed only if the confirmatory study can reach ±4 to ±6 within budget. |
| Fixed-attack difference is large and selected-attack difference is near zero | On these cases, the gap seen with the fixed attack was not reproduced with selected attacks | Worth confirming on the untouched suites. It is evidence about this attack and this library, not about formats in general. |

### 3.6 Cost

Throughput for multi-step agent runs has not been measured, so these are estimates from Study B (126,480 single calls in 2.6 hours for about $7, roughly $2.70 per hour).

| Stage | Work | Expected | Cap |
| --- | --- | ---: | ---: |
| Pilot | 2 models, about 2,700 episodes each (controls, attack selection, 105 pairs × 2 formats × 2 attacks × 3 runs) | 4 hours, about $11 | 6 hours, about $16 |
| Confirmatory, 2 models | 380 pairs × 2 formats × 2 attacks × 3 runs, plus controls | 8 hours, about $22 | 12 hours, about $32 |
| Each further family | Same | about $10 | about $15 |

If, after 30 minutes, the measured speed projects past the cap, the pilot drops to two runs per case, then to four candidate attacks, in that order. About $37 of the $50 limit remains. The pilot fits. The pilot plus a two-model confirmatory study fits at the expected cost and does not at the caps. Four families do not fit.

## 4. Work packages

| | Package | Cost | Status | Acceptance |
| --- | --- | --- | --- | --- |
| WP0 | Guards in the InjecAgent runner: request fingerprint, rendering check, refusal to resume across prompts or servers | Free | Done (commit `9838cbb`) | Tests replay the Study B prompts and flag both defects |
| WP-L | Closest literature read directly; metadata checked | Free | Done 2026-11-15 | Appendix section D |
| WP-C | Rendering census | Free | Done 2026-11-15 | Script, fixtures, rows, renders, summary; a test pins the counts |
| WP-A | Human validation of the Study B scorer | Free; needs people | **Prepared, not carried out** | Protocol and blinded sample exist; labels do not |
| WP1 | Reproducibility: dependency lock, model and template revisions in every row, image digest, the resume guard in the adaptive runner | Free | Proposed | A run refuses to start without them |
| WP2 | AgentDojo harness: fixed-prefix replay, two serializations, per-row rendering check, state-based scoring | Free to build | **Done 2026-11-15**, offline only | With a scripted model that follows the reference calls, at least 95% of banking tasks succeed in both formats and every row passes the rendering check |
| WP3 | Analysis module: averaging over runs, two-way bootstrap, sign-flip test | Free | **Done 2026-11-15** | Recovers a planted effect and its interval on simulated data |
| WP4 | Eight candidate attacks, tried against both formats | Free | **Done 2026-11-15** | Written and committed before any generation |
| WP5 | Pre-registration amendment for the pilot | Free | **Done 2026-11-15** (Amendment 2) | Dated and committed before the pilot's first generation |
| WP6 | The pilot | About $13, cap $20 | **Needs your go-ahead** | [Pilot design](pilot-design.md), section 9 |
| WP7 | Audit of other public harnesses: run the census fixtures through the message-building code of AgentDojo, InjecAgent and ToolHazard for their open-model settings | Free | Proposed | A table of what each harness delivers to each model it reports, or a statement that no defect was found |
| WP8 | Confirmatory study | About $22 for two models | Only after WP6 | Section 3.3 |

WP7 matters more than its size suggests. If the check finds that published numbers from other groups rest on prompts missing tools or payloads, the method has shown its value outside this project. If it finds nothing, the methods contribution is smaller than hoped and that is worth knowing before writing it up.

## 5. Decisions that are yours

1. **Whether to accept the current assessment.** No novel research contribution is established. The realistic near-term product is a methods and replication paper: a corrected record, the census, the check, and possibly a controlled answer to the format question. Whether that is the project you want is your call.
2. **Whether to run the pilot.** It costs about $11 and cannot by itself make the paper.
3. **The budget for a confirmatory study.** Two models fit the remaining $37 only at the expected cost.
4. **Raters.** Who labels the validation sample, or whether the paper says the author did.
5. **The ±5 point threshold.** It is argued in section 3.3 from this project's own defense effects. A different yardstick would change what counts as a null.
6. **Whether to release the corrections.** They are on a branch. Merging them to the default branch and tagging a version makes them the public record.

## What would make this a serious submission, and what would reframe it

Acceptance cannot be predicted. What would make a submission defensible:

- The census facts, re-observed on at least one running server per stack.
- A confirmatory estimate of the format effect under fixed and adapted attacks, at the precision in section 3.3, on untouched tasks, in at least two model families.
- Evidence from WP7 that the problem touches results other groups have published.
- Human validation carried out as the protocol describes, reported as it happened.

What would reframe it as a short methods note, or end it: the pilot's controls cannot be made to pass on two families; the confirmatory precision is out of reach; WP7 finds nothing in other harnesses and the format effect is absent. In that case the corrected record and the census are still worth publishing as a replication report, and a main-conference paper needs a different question. None has been identified with verified novelty; finding one is a separate piece of work.
