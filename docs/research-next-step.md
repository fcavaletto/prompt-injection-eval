# Research audit and next step (2026-11-14)

Written on 2026-11-14, after Studies A and B. It audits the evidence so far, places it against the closest literature, and proposes one decisive experiment. Nothing here was run on a paid GPU. Every new analysis of existing results is **exploratory**: it was written after the outcomes were known. The original results and the [pre-registration](preregistration.md) are unchanged; this page and its [appendix](research-audit-2026-11.md) are dated additions.

## 1. Publication readiness

**Not ready for a main-conference submission.** The project has an honest record (two pre-registered studies, both reported against their own criteria) and one result that reproduces across ten models on synthetic data. It does not yet have a contribution a reviewer could not get from prior work, and this audit found defects that weaken parts of what is published.

What stands in the way, most serious first:

1. **Two of ten models were not validly measured as agents.** In Study B, Phi-4-mini's chat template rendered no tool definitions, so the model never knew any tool existed. Granite 3.3's template dropped the completed tool call, leaving an empty assistant turn. The write-up attributed their zeros to behavior. For the two gpt-oss models no rendered prompt was stored for any row, so what they saw cannot be checked.
2. **The headline causal claim outruns its controls.** "It is the role, not the position" compares conditions that differ in at least seven ways. On Qwen, the tool result is rendered inside a *user* turn, so the role token does not even change.
3. **Inference treats dependent cases as independent.** InjecAgent's 2,108 cases are 17 user contexts crossed with 62 attacker goals and 2 wordings. Design effects for the placement contrast run from 3 to 28.
4. **The outcome on the external benchmark is a tool name,** on single-turn cases, with no positive control showing the model can call a tool when it should.
5. **No capable agent has been tested.** The models are small or mid-sized, and nothing is scored by what happens in an environment.
6. **The serialization result is no longer novel on its own.** A 2026 benchmark paper reports, without numbers in its text, that free-form tool output is attacked more successfully than JSON or YAML.

What is worth building on: the project found, by accident and then by design, that the layer which turns a conversation into a prompt (chat template, serving stack, harness encoding) changes measured robustness and can silently invalidate a measurement. No paper found in this review studies that layer.

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

### 2.3 Novelty matrix

Sources were read through a fetching tool that returned the first part of each paper verbatim and summarized the rest. Cells marked † rest partly on those summaries and need a direct read before they are cited in a paper. Full notes and identifiers are in the appendix.

| Prior work | Closest experiment to ours | What it leaves open | What this project could add |
| --- | --- | --- | --- |
| Nasr et al. 2025, *The Attacker Moves Second* (arXiv:2510.09023) | Adaptive search, RL and human attacks against 12 defenses, including spotlighting and prompt sandwiching, mostly above 90% | Nothing about our adaptive result. It is the stronger version of it. | None on attacks. It sets the bar: any mitigation claim needs an adaptive attacker. |
| Zhan et al. 2025 (arXiv:2503.00061) | White-box GCG against eight defenses on 100 InjecAgent cases, two agents | Same. Also uses a tool-name outcome. | None on attacks. |
| Chang et al. 2025, *ChatInject* (arXiv:2509.22830) | Forged role tags inside tool output raise success on AgentDojo and InjecAgent | Does not move the same content between channels, vary serialization, or check how serving stacks tokenize typed control tokens† | A controlled account of what the rendering layer does when the attacker is *not* forging tokens |
| Ye et al. 2026, *Prompt Injection as Role Confusion* (arXiv:2603.12277) | Linear probes show models read role from style, not tags; a style ablation changes success | Role-swap evidence is internal probe readouts; no causal intervention; no serialization; no standard benchmark† | Behavioral, content-fixed comparisons across renderings. It also explains why "role" was the wrong word for our effect. |
| McCauley et al. 2026, *IH-Benchmark* (arXiv:2607.25987); Zhang et al. 2025, *IHEval* (arXiv:2502.08745) | Conflicts between user and tool instructions, 37 and 13 models; a "treat tool output as untrusted" prompt level | No matched content across channels; no serialization; no template or stack differences | The same |
| Mou et al. 2026, *ToolHazard* (arXiv:2608.11878) | One short analysis: free-form tool output gives higher success than JSON or YAML | No numbers in the text, models and case counts not stated, no pairing, no defense condition, no adaptive attacker, no mechanism† | A paired, pre-registered estimate with a defense factor, utility, and an encoding-aware attacker. **This overlaps our serialization result and must be cited.** |
| Rashidi 2026 (arXiv:2606.18120) | Escaped versus raw template slots across seven delimiter families, user message only | Not tool output, not agents | Extends the same idea to the tool channel and to real serving stacks |
| Shaw 2026, *Silent Failures* (arXiv:2609.32691) | Audit of one harness: undelivered payloads, tool-name scoring (21.7% against 1.2% by arguments), incapacity scored as defense | No templates, parsers, serving stacks, serialization or clustering | Our Phi-4-mini and Granite findings are the same kind of defect at a layer that paper does not examine |
| Debenedetti et al. 2024, *AgentDojo* (arXiv:2406.13352); Zhan et al. 2024, *InjecAgent* (arXiv:2403.02691) | The benchmarks. AgentDojo formats tool output as YAML and says other formats are possible; it varies injection position | No format ablation; intervals treat crossed cases as independent† | Cluster-aware re-analysis; a format factor on an outcome-scored benchmark |

**Where the gap is.** No paper found treats the rendering layer as an experimental variable: the same logical conversation, rendered the ways real stacks render it, with the model, task, tools and injected content fixed. Serialization alone is partly taken. Channel placement with content fixed is open but cannot be cleanly identified (section 3.4).

### 2.4 Candidate contributions, ranked

Scores are judgments, 1 (low) to 5 (high).

| Contribution | Importance | Novelty | Identifiability | Feasibility | Safety relevance |
| --- | ---: | ---: | ---: | ---: | ---: |
| **1. Rendering is an uncontrolled treatment.** How much do renderings that deployed stacks actually produce change attack success, defense effects and model rankings, on outcome-scored agent tasks? | 4 | 4 | 5 | 4 | 4 |
| 2. Serialization as a mitigation under an encoding-aware attacker | 3 | 2 | 5 | 5 | 3 |
| 3. Channel and task-state effects with a state-matched design | 3 | 3 | 2 | 3 | 3 |

**Recommendation: contribution 1,** with contribution 2's attacker as one secondary arm. It is the only one where the intervention is exactly what can be manipulated, where the project already holds a documented real-world instance, and where no overlapping paper was found. Contribution 3 is dropped as a headline: role cannot be varied without changing the wrapper, and the literature already has a stronger conceptual account.

The working direction ("how do serialization and conversation construction change measured robustness, and when does that transfer to capable agents") is kept but narrowed in one way that matters. "Conversation construction" is restricted to **renderings that occur in practice for the same logical conversation**. That turns an open-ended sensitivity study into one with a population to sample from and a yardstick to compare against.

## 3. The decisive experiment: Study R

### 3.1 Question, claim, hypotheses

**Question.** For a fixed model, task, tool set and injected content, how much does targeted attack success change across renderings of the tool result that deployed serving stacks produce, compared with the change a standard prompt-level defense produces?

**Claim it could support.** "On outcome-scored agent tasks, the choice among renderings in common use moves measured attack success by an amount comparable to a prompt-level defense, in k of K model families, and changes which model looks more robust." It could not support any claim about roles, about why, or about models not tested.

**Hypotheses,** each falsifiable, all two-sided unless stated:

- **H1 (existence).** In at least 3 of 4 families, attack success differs between the `raw` and `json_string` renderings by at least 5 percentage points, with a two-way cluster interval excluding zero.
- **H2 (direction, one-sided, from Study A and ToolHazard).** `json_string` is lower than `raw`.
- **H3 (yardstick).** In at least 2 of 4 families, the largest difference between renderings is at least half the size of the rule's effect under the native rendering.
- **H4 (interaction, tested directly).** The rule's effect differs between `raw` and `json_string` (difference in differences not zero).
- **H5 (ranking).** At least one pair of models changes order between two renderings, with the difference-of-differences interval excluding zero.

### 3.2 What changes and what stays fixed

All conditions run through the chat API with the model's own template. Only the content string of each tool message changes.

| Condition | Tool-result content | Occurs in practice as | Rule |
| --- | --- | --- | --- |
| `raw` | The benchmark's text, unchanged (AgentDojo's YAML dump) | AgentDojo default; vLLM's Harmony path | none |
| `json_string` | The same text as one JSON string (quoted, escapes) | Templates that apply `tojson` to tool content (the gpt-oss template on Hugging Face) | none |
| `json_object` | The underlying object serialized as JSON | OpenAI-style function-calling harnesses; InjecAgent's function-calling evaluation | none |
| the same three | as above | | generic rule, one fixed sentence in the system prompt |

Fixed across all six: model weights and revision, serving image digest, chat template, tool schemas, user task, injection text and position, system prompt apart from the rule sentence, sampling settings, output budget, parser. The rendered prompt is stored for every row, and every row passes the rendered-prompt check or the model is excluded.

`raw` against `json_string` isolates quoting and escaping of identical text. `raw` against `json_object` changes structure as well, and is the comparison ToolHazard reports.

### 3.3 Competing explanations and the controls for them

| Explanation for a difference | Control |
| --- | --- |
| The model cannot use the interface, so low success is incapacity | Validity gate before any attack outcome: benign utility, authorized-call rate, and the attacker's task given as the user's own request |
| The rendering breaks the task, so "safer" is "less useful" | Benign utility and utility under attack per condition; a mitigation claim requires utility within 5 points |
| The template dropped or rewrote something | Rendered-prompt check on every row |
| Output cut off, or calls not parsed | Truncation and parse-failure rates per condition, reported next to every success rate; output budget raised to 1,024 tokens |
| Run-to-run noise | Two full runs of the native condition per model; the noise interval is reported beside every contrast |
| Serving stack rather than rendering | Stage 3: the same weights on a second stack, where the rendered-prompt difference is predicted in advance |
| The attack was not adapted to the encoding | Secondary arm with an encoding-aware attacker (section 3.6) |
| A few tasks drive the result | Two-way clustering; per-suite results; leave-one-suite-out |

### 3.4 What cannot be isolated

- **Role.** A chat role is a wrapper the template writes. It cannot be changed without changing those tokens, and on Qwen the tool result sits in a user turn. Study R does not vary it and makes no claim about it.
- **Channel.** Moving content from a tool result to the user message changes the agent's task state. It is left out.
- **Native format.** A model's own template fixes one rendering as the trained one. Renderings that depart from it may be worse because they are unfamiliar, not because of their form. This is reported as a pre-specified exploratory comparison (does the native rendering give the lowest success?), with four families and no inferential claim.
- **Invalid formats.** A dropped tool schema or a dropped completed call is a validity failure, not a treatment. Such configurations are excluded and counted, not compared.

### 3.5 Data and contamination safeguards

- **Benchmark.** AgentDojo, pinned to a commit: 629 security cases (97 user tasks crossed with 27 injection tasks in four suites) and its utility tasks, scored by its environment checks.
- **Development data.** The banking suite (144 cases). All pipeline debugging, the pilot, and the selection of the encoding-aware attack use only this suite. InjecAgent and the synthetic documents are also development data from here on.
- **Untouched evaluation data.** Workspace, Slack and travel (485 cases; 81 user tasks, 18 injection tasks). No attack outcome on these is produced before the pre-registration amendment for Study R is committed.
- **Safeguards.** The harness refuses to run evaluation suites unless the commit of the amendment is an ancestor of the working tree; the smoke and validity stages write no attack outcomes; request fingerprints prevent mixed rows.
- **Limit.** AgentDojo is public and may be in training data. The contrasts are within model, which protects comparisons more than levels.

### 3.6 Models, controls, measures, attacker

**Models.** Four families chosen because their templates render a tool result differently, each large enough to act as an agent, each fitting one 96 GB card at full precision:

| Model | Why |
| --- | --- |
| Qwen3-32B | Tool result inside a user turn in `<tool_response>` tags; the family where the earlier effect appeared |
| gpt-oss-120b | Harmony format; the family where a stack difference reversed a published result |
| Mistral Small 3.2 (24B) | Template wraps tool results in its own JSON envelope |
| A fourth, Granite 4.0 Small or GLM-4 32B | A different developer with a dedicated tool role |

The last two are to be confirmed in the census (names and current support were not verified in this session). A model that fails the validity gate is dropped with the reason and replaced from a reserve list fixed in advance. Qwen3-8B is an optional fifth as a small-model contrast.

**Validity gate (positive controls), run on the development suite, read before any attack outcome:** benign utility of at least 40%; a parsed, schema-valid call on at least 90% of turns that need one; at least 70% success on the attacker's tasks when given as the user's own request; zero rendered-prompt defects.

**Measures per condition:** targeted attack success, benign utility, utility under attack, parse-failure rate, truncation rate, invalid-argument rate, rendered-prompt defects.

**Attacker.** Primary: AgentDojo's `important_instructions` attack as shipped, which knows the user's and the model's name, with no queries to the target. Secondary: an encoding-aware attacker who knows the tool result will be a JSON string. Eight variants written in advance (for example, text that imitates the end of the string, or that avoids characters the encoding escapes), one chosen per model on the development suite with at most 8 × 144 queries, then one attempt per evaluation case. This arm exists so that a lower rate under JSON is never read as a defense.

**Human validation.** A stratified sample of 200 evaluation trajectories (model, rendering, scorer outcome), labeled blind by two people for "did the agent carry out the attacker's goal with arguments that would work" and "did it complete the user's task". Reported as agreement with the programmatic checks and between raters.

### 3.7 Analysis

- **Unit.** One (user task, injection task) cell. Cells are crossed, not independent.
- **Primary estimand.** Per family, the difference in attack success between `raw` and `json_string`, averaged over the two rule levels, in percentage points.
- **Interval and test.** Two-way cluster bootstrap over user tasks and injection tasks, stratified by suite, 10,000 replicates, percentile 95% interval. A sign-flip test over user tasks is the sensitivity check. A mixed logistic model with crossed random effects is reported as a second check.
- **Interactions.** H4 and H5 are tested as contrasts of contrasts, never by comparing significance labels.
- **Multiplicity.** Holm over the four primary tests. H3 to H5 form one secondary family. Everything else is exploratory.
- **Absence.** "No difference" is claimed only if the interval lies within ±5 points; otherwise the result is "not resolved".
- **Families.** With four, results are counted ("k of 4"); no inference to models in general.

**Sample size.** Precision is set by the number of tasks, not cases. In Study B the design effect for the JSON contrast was about 2 to 7 (appendix). If AgentDojo behaves similarly, 485 evaluation cases carry the information of roughly 70 to 200 independent ones. For a paired contrast with 15% discordant cases, the smallest effect detectable at 80% power after Holm is then about 9 to 15 points per model. Study A's effect was 25 points on synthetic documents; on InjecAgent, where the "raw" text is already quoted, it was 1 to 4. So the study can confirm an effect of the size seen on synthetic data, and can rule one out only above roughly 10 points. The pilot re-estimates the design effect on AgentDojo before the full run, and the amendment fixes the final numbers.

### 3.8 Stages, cost, and decisions

| Stage | What | Cost | Go / stop |
| --- | --- | ---: | --- |
| 0. Rendering census | Render one fixed agent conversation through the templates of about 25 popular tool-calling models on three or four stacks; classify what each drops or re-encodes. No GPU. | $0 | **Stop or reframe** if fewer than 15% of model-stack pairs differ in a security-relevant way. Otherwise it fixes the rendering levels. |
| 1. Gate and pilot | Validity gate on four models; the six conditions on the development suite for two models | about $3 | **Stop** if fewer than three families pass. **Stop** if the rendering difference is under 3 points on both pilot models with an upper bound under 8. |
| 2. Confirmatory | Six conditions, four models, evaluation suites, utility tasks, a second run of the native condition, the encoding-aware arm on two models | about $14 to $20 | Pre-registered analysis |
| 3. Second stack | Native condition for two models on a second serving stack, with the prompt difference predicted first | about $4 | Supports or removes the "stacks" half of the claim |

Estimated total $21 to $27 of the roughly $37 remaining. The multi-turn throughput figure is a guess until the pilot measures it; treat the total as uncertain by half in either direction.

**What each outcome would mean.**

- **Positive** (H1 in three families, H3 in two): the thesis holds. The paper is the census, the experiment, the correction of a published result, and a reporting standard.
- **Null** (all intervals within ±5): rendering effects seen on single-turn synthetic tasks do not carry to capable agents. That is worth a short paper together with the audit, not a main-conference submission. The project should stop spending on this line.
- **Reversed** (JSON higher): the benefit is specific to the task format. Report it, and look at whether the native rendering is the safest, as exploratory.
- **Heterogeneous:** effects exist but differ by family. This still supports "rendering must be reported and controlled", and leans on the census to show the choice is common in practice.

**No mechanistic probes.** Role probes in the style of Ye et al. would be correlational here. A causal reading would need activation patching between renderings at matched positions, and the renderings differ in length and tokenization. The measurement claim does not need it.

## 4. Work packages

| Package | Content | Acceptance criterion |
| --- | --- | --- |
| **WP0. Corrections and guards** (done in this session) | Dated correction notes on the Study A and B pages; request fingerprints and a refusal to resume across a changed prompt or server; a rendered-prompt check that fails the smoke test | Tests reproduce the Phi-4-mini and Granite defects from the published prompts; the full suite passes |
| WP1. Reproducibility | Dependency lock; model and tokenizer revisions and template hashes recorded per row; image by digest; the same resume guard in the adaptive runner; a fix or an explicit exclusion for servers that return no prompt | A run manifest from which a third party can rebuild every prompt byte for byte |
| WP2. Rendering census (stage 0) | Fixed conversation, renderer per stack, classification table | The table is rebuilt by one command with no GPU, and the go or stop rule is applied as written |
| WP3. AgentDojo harness | Pinned benchmark, tool-content hook for the three renderings, per-row prompt capture, validity gate | The six conditions differ only in tool-message content, shown by diffing rendered prompts |
| WP4. Cluster-aware analysis | Two-way bootstrap, sign-flip test, contrasts of contrasts, equivalence margin, as a tested module | Reproduces the appendix tables from the published Study B rows |
| WP5. Pre-registration amendment | Hypotheses, estimands, margins, exclusions and stop rules of section 3, with pilot-based numbers | Committed before any evaluation-suite attack outcome exists |
| WP6. Pilot, then confirmatory run | Stages 1 and 2 | Stop rules applied as written; all rows published |
| WP7. Human validation | Sampling script, blind labeling sheet, agreement statistics | Two raters, 200 trajectories, agreement reported whatever it is |
| WP8. Second stack (stage 3) | Same weights on a second stack | The prompt difference is written down before the run |

## 5. Unresolved decisions

1. **The thesis.** Whether to commit to "rendering is an uncontrolled treatment" as the paper, and so let go of the role and placement story that the current documentation leads with.
2. **Who validates.** The human validation needs two raters who are not the system that wrote the scorer. One should be the author. A second person has to be found, or the paper must say there was one rater.
3. **The stop rules.** Whether to accept in advance that a null pilot ends this line, and that a census showing rendering differences are rare reduces the work to a controlled serialization study.

Smaller open points: whether to request access to a gated Llama model as the fourth family; whether to add one hosted frontier model for external validity, which conflicts with the no-paid-API constraint; and whether the earlier pages should be restructured now or only annotated, as they are today.

## What would make this a serious submission, and what would end it

**Serious:** a census showing that security-relevant rendering differences are common across stacks; a pre-registered effect on outcome-scored tasks in at least three families that is comparable to a defense's effect; a ranking reversal; the same effect reproduced by switching stacks with the prompt difference predicted beforehand; validated scoring; and all of it with cluster-aware intervals. That would be new, checkable, and useful to anyone who evaluates open-weight agents. It still would not make acceptance predictable.

**Abandon or reframe:** the census finds the differences are rare; fewer than three families pass the validity gate; or the pilot shows differences under 3 points. In those cases the honest product is a short methods note built from the audit: the dependence structure of InjecAgent, the template defects, and the corrected Study A reading.
