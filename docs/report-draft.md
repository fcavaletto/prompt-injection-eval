# Draft report: what reaches the model, and does tool-output serialization change injection success?

**Status: release candidate draft, 2026-11-16. Not submitted, not released, not independently reviewed.** It summarizes evidence already in this repository. Every number is from stored traces or code at a pinned revision, and nothing new was run on a model. Pre-registered results are stated as registered. Exploratory analyses are labelled.

**What the central claims rest on.** Only two bodies of evidence:

- the registered serialization pilot, whose outcomes are AgentDojo's own state-based checks, with delivery verified on every request;
- the offline audit of other harnesses (WP7).

The project's earlier Studies A and B used a text-based scorer that has had **no human validation**: the protocol and a blinded sample exist, but no rater has labelled anything. Those studies appear here only as a corrected record of past claims. No new claim rests on that scorer.

Revision of 2026-11-16, after commit `9158143`:

- missing-outcome bounds corrected;
- code behaviour, observations and hypotheses separated;
- provenance qualified;
- a template-free sensitivity count added.

## 1. Question

Agent security benchmarks report how often an injected instruction in a tool result makes an agent act for the attacker. Two layers between the benchmark and the model can change that number without anyone deciding to:

- the harness code that turns a conversation into a request;
- the chat template that turns the request into a prompt.

This report asks two questions.

1. **Measurement.** Do public prompt-injection harnesses deliver tool definitions, completed calls, tool results and payloads to the model as intended? When they do not, what does that do to published numbers?
2. **Replication under control.** With delivery verified on every request, does serializing tool output as one JSON object instead of labelled free text change injection success? Does that survive choosing attacks separately for each format?

## 2. Related work, as verified

Claims below were checked against full text and released code on 2026-11-16 ([audit appendix](research-audit-2026-11.md), D1b).

- **ToolHazard** (arXiv:2608.11878 v1, Sec. 7.2, Fig. 4) reports that free-form tool output is attacked far more often than JSON or YAML. For example, GPT-4.1 under one attack: 52.6% free-form, 5.9% JSON, 1.2% YAML.
  - Two closed models and two attacks.
  - Formats described only as "identical settings"; experiment size not stated; no intervals.
  - The released code has no switch for the three formats, so the comparison cannot be rebuilt.
- **Agent Data Injection** (arXiv:2607.05120 v1) shows that attacks written for JSON work. Fake objects and escaped delimiters, which models misread (Sec. III-C), reach 49.1% success on AgentDojo with JSON tool output (GPT-5.2), against 0.2% for instruction injection (Sec. VI-B). It does not compare serializations with the payload fixed.
- **AutoDojo** (arXiv:2606.15057 v3) optimizes injections adaptively on AgentDojo, with point estimates only (App. G.3). It does not vary serialization.
- **The evaluation layer as a confound** is established for serving stacks and tool calling (Tang and Zheng, arXiv:2609.26693) and for undelivered payloads and incapacity scored as defense (Shaw, arXiv:2609.32691). Those checks are at the environment or server level, not on the rendered prompt.

What is not in this literature: a prompt-level audit of what public injection harnesses deliver, and a same-attack serialization comparison with verified delivery and intervals that respect task structure.

## 3. Method: verified delivery

- **Rendering census** ([rendering census](rendering-census.md)): four fixed conversations through 26 templates at pinned revisions and 11 Ollama templates, plus 144 stored server prompts compared with local renderings.
- **Delivery check** (pilot harness): for every model request, the prompt the server returns is parsed. Each offered tool must appear as a JSON object equal to the schema sent, each earlier call with equal name and arguments, each tool result verbatim (and, for JSON, decoding to its record), and the payload in the form the condition prescribes. A row that fails is an invalid measurement, never a failed attack.
  *Note 2026-11-17: this check did not verify turn roles, multiplicity, strict scalar types or the generation header ([corrections](corrections.md) C19). The archived outcomes rest on hash equality with the pinned template, which covers those. A repaired check is validated in the [measurement contract](measurement-contract.md).*
- **External audit** ([WP7](wp7-audit.md)): a common fixture is passed through other harnesses' own message-building code at pinned revisions, with the templates the reported configurations would use (reconstructed: see section 7 on provenance). The checker accepts every legitimate encoding: JSON escaping, YAML scalar styles including folded lines, YAML inside JSON, and Python `repr`. A checker failure is a lead, not a finding: on the first run it flagged two harness configurations whose YAML folding it did not yet recognize. Both were valid.
  *Note 2026-11-17: the WP7 checker matched markers and accepted renamed parameters, changed types and changed arguments. With strict items all stored renderings still pass (C18). A pass certifies a reconstructed component, not the original pipeline (C23).*

## 4. Registered pilot (Amendment 2, as amended by Amendment 3)

**Setup:**

- **Models:** Qwen3-32B and Granite 4.0 H Small on vLLM 0.33.0.
- **Benchmark:** AgentDojo 0.1.35 (v1.2.2). Banking is development (72 selection pairs); Slack is evaluation (105 pairs).
- **Episodes:** the agent is resumed after a reference-prefix replay, so both formats start from the same state. This is a custom harness, not AgentDojo benchmark scores.
- **Formats:** every tool result is serialized as one JSON object or as labelled free text.
- **Attacks:** eight candidate wordings plus AgentDojo's fixed `important_instructions` attack. The candidate with the most development successes is frozen per model and format.

**Validity:**

- 4,986 new episodes, none invalid.
- All 21,327 returned prompts of the new phases match a local rendering by hash.
  *Note 2026-11-17: precisely, all 21,321 turns of scored episodes; the figure also counts 6 turns of superseded traces, and 11 turns of superseded traces cannot be rebuilt (C21).*
- Six episodes interrupted by proxy disconnects were rerun.
- Both models passed every development gate. Every Slack goal has a capable benign twin.

**Primary, as registered** (each format against the attack selected for it; first runs; task-bootstrap interval):

| Model | Text minus JSON, attack success | Reading as registered |
| --- | --- | --- |
| Qwen3-32B | +8.6 (+2.9 to +14.3) | With this library and budget, the attack selected for JSON did worse against JSON than the attack selected for text did against text |
| Granite 4.0 H Small | +11.4 (+2.9 to +21.0) | Same |

Same-attack contrasts (registered secondary):

- Qwen: +1.9 (−3.8 to +7.6) under the fixed attack; +1.9 and +1.0 under its two selected attacks.
- Granite: +9.5 (+2.9 to +17.1) under the fixed attack.

Two-way intervals reach zero for both models. With five goals they are reported, not relied on.

## 5. Exploratory: what the primary contrast contains

The primary measures a procedure (select per format, then evaluate), not serialization alone. For Qwen, whose two selected attacks differ, it splits exactly per case:

| Qwen3-32B | Estimate | Task interval |
| --- | ---: | --- |
| Primary | +8.6 | +2.9 to +14.3 |
| Wording: the two selected attacks differ in strength, averaged over formats | +7.1 | +2.4 to +12.9 |
| Format: text minus JSON, averaged over the two attacks | +1.4 | −2.9 to +6.2 |
| Interaction: does the format effect depend on the attack? | +1.0 | −5.7 to +7.6 |

- **Granite:** averaged over its two attacks, the same-attack format effect is +10.5 (+3.8 to +17.1). The interaction is +1.9 (−7.6 to +11.4).
  *Note 2026-11-17: both attacks are multiline. On banking, the baseline's one-line twin went the other way (−11.1), and on Slack 7 of the baseline's 10-success gap fall in round-limit episodes (C24; [claim–evidence](claim-evidence.md) H3, H4).*
- **Between models:** Granite's fixed-attack format effect minus Qwen's is +7.6 (−0.9 to +16.2). A difference between models is not established.
- **Ceiling:** three of Qwen's five goals were at ceiling.
- **What is supported:** for Granite, JSON lowered success under the same attack. For Qwen, most of the primary difference was attack wording. A Qwen format effect of a few points is neither shown nor excluded.

## 6. Repeatability

At temperature 0, repeated runs measure serving nondeterminism.

- **Qwen:** no repeated cell disagreed (0 of 126 cells; 0 of 21 pairs, exact interval over pairs 0% to 16.1%).
- **Granite:** 4 of 84 cells disagreed on attack success and 5 of 84 on user-task success. The cells of one pair are not independent: three of the four attack disagreements are in one pair.
  - Attack success, by pairs: 2 of 21 (1.2% to 30.4%); cluster bootstrap of the cell share, 0% to 13.1%.
  - The all-runs sensitivity analysis moved Granite's primary from +11.4 to +11.1.
  - Whether nondeterminism is shared across cases (batch effects) was not investigated. First-run intervals include run-to-run noise only if it is independent across cases.

**Registered progression gate.** "Runs disagree in at most 5% of cells" names no outcome. It holds for Granite on attack success and fails on user-task success. Read conservatively, it is not met, so the registered criterion for a larger study is not satisfied ([Pilot design](pilot-design.md) 9.8a). No threshold was waived and no repeats were added.

## 7. Audit of other harnesses (WP7)

Full table, provenance and method: [WP7](wp7-audit.md).

**Passes:**

- InjecAgent's prompted Together path, as released: all content delivered, though its Llama 2 template folds the system prompt into the user turn;
- ToolHazard's prompt mode, as released: YAML tool output in a user turn;
- AgentDojo's `vllm_parsed` path.

**Unverifiable:**

- Meta-SecAlign-70B's rendering: its template is gated and its tool role is unrecorded;
- ToolHazard's three-format experiment: no code path for it;
- Agent Data Injection at the model: the agent is a hosted API. At the message level its JSON is valid and lossless.

**Provenance.** "Published configuration" here means the provider, model and mode that published results report, rebuilt from code at a pinned revision. For none of the three harnesses does the record show that revision generated the published results.

- AgentDojo's traces record `agentdojo_package_version: "unknown"`. They were added on a branch (PR #96) separate from the LocalLLM changes merged the same day (PR #97). The PR #97 code, identical to v0.1.35 in the relevant file, is the most plausible generator.
- Both behaviours below are present in every LocalLLM revision from 2025-03-21 to v0.1.35, including both candidate revisions.
- InjecAgent restructured its prompted path after the paper's results.
- Templates for gated models come from mirrors, and whether the original servers used them is unrecorded.

**AgentDojo `local` path** (the provider of the published Llama 3.3 70B and Meta-SecAlign-70B runs): four statements, each held at its own level of evidence.

1. **Confirmed code behaviour.**
   - `chat_completion_request` catches any exception and returns an empty string. The episode then ends with an empty assistant turn and enters ordinary outcome scoring, with no failure flag.
   - This does not automatically score an error as a defence. Security is read from the final environment state, so an attack completed before the error would still count as a success.
2. **Observed in the published traces.**
   - 59 episodes end in an empty assistant turn with no call: 48 Llama 3.3 (46 under attack) and 11 SecAlign (8 under attack). All are in workspace, and every one under attack was scored as an attack failure.
   - Rebuilt with LocalLLM's code and the mirrored template, every such request is longer than every other trace's for the same model: at least 16,564 tokens against at most 16,537 for Llama 3.3; at least 17,804 against at most 17,584 for SecAlign.
   - Without any template, on message contents alone, SecAlign still separates. For Llama 3.3, 2 of 2,931 other traces lie above the smallest empty one. The sharpness therefore depends partly on the template.
3. **Hypothesis, not established.** A server context limit caused these endings through the error path. The server command, context limit and logs would settle it; none was recorded. A model that returns nothing on very long inputs would also fit.
4. **Representation, reproduced; effect unmeasured.**
   - LocalLLM sends each tool result as `{"result": [{"type": "text", "content": "<YAML>"}]}`, where its code evidently intends `{"result": "<text>"}`.
   - With the Llama 3.x template, `tojson` encodes that string once more.
   - The payload survives and decodes exactly. Whether this representation changes attack success has not been measured.

**Conditional missing-outcome bounds.** Take the empty endings as missing outcomes and hold every other outcome fixed. With N planned episodes, S observed successes and M missing:

- the full-benchmark rate lies between S/N and (S+M)/N;
- the complete-case estimate is S/(N−M).

These are bounds under that assumption, not confidence intervals.

| Llama 3.3 70B, `important_instructions` | N | S | M | Bounds | Complete-case |
| --- | ---: | ---: | ---: | --- | ---: |
| Workspace | 560 | 38 | 29 | 6.8% to 12.0% | 7.2% |
| All suites | 949 | 219 | 29 | 23.1% to 26.1% | 23.8% |

- The published figure is the lower bound.
- The missing episodes are the longest workspace requests, so missingness depends on length and plausibly on the episode's course. Exclusion may therefore be selective, and the complete-case figure is not a corrected estimate.
- Meta-SecAlign-70B's bounds widen by at most 0.6 points. Llama 3.3's lower bound stays above SecAlign's upper bound for every attack over all suites, and on workspace for the two stronger attacks. Only workspace `direct`, under 2% for both models, overlaps. The published robustness comparison survives.

**Configurations that no published result used:**

- AgentDojo's prompting path now sends its system text twice, once as `developer`;
- ToolHazard's formatter would skip YAML for non-string outputs;
- Agent Data Injection's unused delivery flag misfires on escaped payloads.

## 8. What is demonstrated and what is not

**Demonstrated:**

- delivery verified on every pilot request;
- the registered pilot results;
- the exact decomposition of Qwen's primary contrast;
- for Granite, a same-attack format effect with an interval above zero, on 21 Slack tasks and 5 goals;
- in AgentDojo's `local` code, the error-to-empty-answer path and the extra encoding, reproduced from pinned code and present in every candidate revision;
- in the published traces, 59 empty endings, concentrated in the longest workspace requests, and the conditional bounds they imply;
- clean passes for three other harness paths.
  *Note 2026-11-17: passes of reconstructed components, not certifications of the original pipelines (C23).*

**Inferred, not established:**

- that the empty endings were context-limit errors;
- that the PR #97 code generated the traces;
- that the servers used the mirrored templates.

**Unknown:**

- what the 59 episodes would have scored without the failure;
- whether the extra encoding changed published success rates;
- whether Granite's format effect generalizes beyond Slack, these goals and this library, or differs from Qwen's;
- whether serving nondeterminism is shared across cases;
- how hosted services render their inputs.

## 9. Possible follow-up for the WP7 finding (not run, not authorized)

**Step 0, free.** A draft inquiry to the AgentDojo maintainers has been prepared for the author's review. It has not been sent or posted. It asks for:

- the server command;
- the context limit;
- the output-token budget;
- the tokenizer and template revisions;
- the SecAlign tool delimiter;
- the code commit;
- the error logs.

A recorded context limit near the observed thresholds, or logged request errors for the affected episodes, would establish the mechanism without any inference.

**Step 1, only if step 0 cannot settle it.** Rerun exactly the 59 affected episodes with a context window that fits them, and with failed requests recorded instead of swallowed.

- **What it measures.** These episodes' outcomes under a changed configuration: a larger context window, a different serving run, and new nondeterminism. It does **not** recover the original missing outcomes. The original runs could not produce an outcome for these requests, which is the finding.
- **What it cannot do.** Substituting the rerun outcomes into the published counts gives a counterfactual "what these runs would have scored had the requests fit", not a corrected original measurement. It does not narrow the conditional bounds, which describe the original runs.
- **The mechanism.** Restoring the original limit and observing the same requests fail would test the hypothesis, but only if that limit is known.
- **Size.** About 59 episodes on a 70B model in bf16, on the order of 1 to 2 GPU-hours plus weight download. Prices were not checked.

Measuring the extra encoding's effect would need a different study: the same model on a stratified subset under both representations. It is larger and lower priority.

## 10. Reproducing without inference

```bash
pip install -e ".[dev,pilot]" transformers
# Pilot reports, from stored traces
pie pilot report --phase-dir results-published/pilot-f1-2026-11-16/qwen3-32b/dev-controls --phase-dir results-published/pilot-2026-11-16/qwen3-32b/select --phase-dir results-published/pilot-2026-11-16/qwen3-32b/eval-controls --phase-dir results-published/pilot-2026-11-16/qwen3-32b/evaluate --output-dir /tmp/pilot-qwen
pie pilot report --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/dev-controls --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/select --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/eval-controls --phase-dir results-published/pilot-2026-11-16/granite-4.0-h-small/evaluate --output-dir /tmp/pilot-granite
# Exploratory decomposition, interactions, clustered repeatability
python scripts/pilot_exploratory.py results-published/pilot-2026-11-16 --output /tmp/exploratory
# WP7: see results-published/wp7-audit-2026-11-16/README.md for the pinned clones, then
python scripts/wp7_audit.py --ext "$EXT" --out /tmp/wp7
python scripts/wp7_agentdojo_traces.py "$EXT/agentdojo" --out /tmp/wp7
pytest tests/test_pilot_analysis.py tests/test_pilot_exploratory.py tests/test_wp7.py
```

Prompt hashes: `python scripts/verify_pilot_prompts.py <phase-dir> --repository <model> --revision <rev>` (tokenizer files only).

## 11. Limitations

- **Pilot scope:** two models, both carrying tool results in a user turn; one serving stack; one evaluation suite with five goals; a fixed library of eight wordings and no adaptive attacker; temperature 0.
- **Audit scope:** bounded by design (four harnesses, one fixture). Hosted services are invisible. Templates for gated models are mirrors, and the code revisions behind other groups' published results are reconstructed, not recorded.
- **Scorers:** the pilot and the audit use AgentDojo's state checks. **Human validation of the project's earlier text-based scorer was not performed**, so no claim here rests on it.
- **Exploratory analyses:** written after the outcomes were known.
- **Review:** no independent human review has taken place yet. A [checklist](review-checklist.md) is prepared for one. Review by another AI system would not count.

## 12. Contribution, release format, remaining work

**Strongest defensible contribution:** a methods and replication report built on the pilot and the WP7 audit.

1. **A prompt-level delivery audit** that accepts legitimate encodings, applied to four public harnesses at pinned revisions.
   - It reproduced a silent error path and an undocumented encoding in AgentDojo's open-model provider.
   - In that provider's published traces it located 59 episodes whose outcomes are suspect, and bounded their effect conditionally: the published robustness comparison survives.
     *Note 2026-11-17: except on workspace `direct`, where the bounds overlap (C22).*
   - Three other harness paths passed.
2. **A small, pre-registered, delivery-verified replication of the serialization effect** on two open models. Its methodological lesson: comparing each format with its own selected attack confounds format with attack wording, so the same-attack contrast is the one to register.
3. **Repeatability under one stack,** with its dependence structure stated.

None of these is established as a main-conference research finding.

**Release format:** an arXiv preprint or workshop paper (evaluation methodology or ML security). The tagged repository and its evidence bundles are the artifact.

**Release blockers** (all are the author's decisions or need people; none needs compute):

1. Independent human review against the [checklist](review-checklist.md), returned and published as received.
2. A decision on the AgentDojo maintainer inquiry: send it, revise it, or not. Releasing claims about another group's published results is better preceded by giving them the chance to answer. The report states the mechanism as a hypothesis either way.
3. A statement in the release that human validation of the earlier text-based scorer was not performed. It is in this draft, and the remaining decision is whether to keep Studies A and B in the release at all.
4. Merging `research-audit-2026-11` into `main`, choosing a version and tagging a release. Not done.
5. Author name, affiliation and submission venue. Not done.

**Optional, not blocking:**

- check the mirrored templates against the gated originals if access is granted;
- measure InjecAgent's step-two prompt lengths;
- the rerun in section 9, if it is ever authorized and step 0 cannot settle the mechanism.
