# Draft report: what reaches the model, and does tool-output serialization change injection success?

**Status: draft, 2026-11-16. Not submitted, not released.** It summarizes evidence already in this repository. Every number is from stored traces or code at a pinned revision, and nothing new was run on a model. Pre-registered results are stated as registered. Exploratory analyses are labelled.

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
- **External audit** ([WP7](wp7-audit.md)): a common fixture is passed through other harnesses' own message-building code and the published configurations' templates. The checker accepts every legitimate encoding: JSON escaping, YAML scalar styles including folded lines, YAML inside JSON, and Python `repr`. A checker failure is a lead, not a finding: on the first run it flagged two harness configurations whose YAML folding it did not yet recognize. Both were valid.

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
- **Between models:** Granite's fixed-attack format effect minus Qwen's is +7.6 (−0.9 to +16.2). A difference between models is not established.
- **Ceiling:** three of Qwen's five goals were at ceiling.
- **What is supported:** for Granite, JSON lowered success under the same attack. For Qwen, most of the primary difference was attack wording. A Qwen format effect of a few points is neither shown nor excluded.

## 6. Repeatability

At temperature 0, repeated runs measure serving nondeterminism.

- **Qwen:** no repeated cell disagreed (0 of 126 cells; 0 of 21 pairs, exact interval over pairs 0% to 16.1%).
- **Granite:** 4 of 84 cells disagreed on attack success and 5 of 84 on user-task success. The cells of one pair are not independent: three of the four attack disagreements are in one pair.
  - Attack success, by pairs: 2 of 21 (1.2% to 30.4%); cluster bootstrap of the cell share, 0% to 13.1%.
  - The all-runs sensitivity analysis moved Granite's primary from +11.4 to +11.1.
  - Whether nondeterminism is shared across cases (batch effects) was not investigated, so first-run intervals assume it is not.

**Registered progression gate.** "Runs disagree in at most 5% of cells" names no outcome. It holds for Granite on attack success and fails on user-task success. Read conservatively, it is not met, so the registered criterion for a larger study is not satisfied ([Pilot design](pilot-design.md) 9.8a). No threshold was waived and no repeats were added.

## 7. Audit of other harnesses (WP7)

Full table: [WP7](wp7-audit.md).

**Pass:**

- InjecAgent's published prompted path (all content delivered; its Llama 2 template folds the system prompt into the user turn);
- ToolHazard's published prompt mode (YAML tool output in a user turn);
- AgentDojo's `vllm_parsed` path;
- Agent Data Injection's JSON tool messages, at the message level only: the model was a hosted API.

**Two findings in AgentDojo's `local` path**, which produced its published Llama 3.3 70B and Meta-SecAlign-70B results:

1. **Server errors become defended episodes.** `chat_completion_request` catches any exception and returns an empty answer, which ends the episode and is scored.
   - In the published traces, all 48 Llama 3.3 episodes and 11 SecAlign episodes that end this way are in workspace. Within each model, each one's last request is longer than every other trace's: at least 16,564 tokens against at most 16,537 for Llama 3.3; at least 17,804 against at most 17,584 for SecAlign.
   - That is consistent with a server context limit. The server's limit was not recorded, so it is not proven.
   - All attacked ones were scored as defended. For Llama 3.3 under `important_instructions` on workspace, the published 6.8% would lie between 7.2% (excluding them) and 12.0% (if all had succeeded). Over all suites, 23.1% would lie between 23.8% and 26.1%.
   - SecAlign moves by at most 0.4 points. The published conclusion that SecAlign is far more robust holds at every bound.
2. **Tool results are triple-encoded.** LocalLLM sends `{"result": [{"type": "text", "content": "<YAML>"}]}` where its code intends `{"result": "<text>"}`, and the Llama 3.x template JSON-encodes the string again. The payload arrives intact, but in a representation nobody documented. Given section 5, the representation is not neutral, though its effect on these numbers is unmeasured.

Also found, in configurations that no published result used:

- AgentDojo's prompting path now sends its system text twice, once as `developer`.
- ToolHazard's formatter would skip YAML for non-string outputs.
- Agent Data Injection's unused delivery flag misfires on escaped payloads.

## 8. What is demonstrated and what is not

**Demonstrated:**

- Delivery was verified on every pilot request.
- The registered pilot results.
- The exact decomposition of Qwen's primary contrast.
- For Granite, a same-attack format effect with an interval above zero, on 21 Slack tasks and 5 goals.
- In AgentDojo's `local` path, the error-to-answer path and the triple encoding, reproduced from pinned code.
- The token-threshold split in the published traces.
- Clean passes for three other harness paths.

**Uncertain:**

- Whether the 59 empty AgentDojo episodes were context-limit errors, and what they would have scored.
- Whether the triple encoding changed AgentDojo's published success rates.
- Whether Granite's format effect generalizes beyond Slack, these goals and this attack library.
- Whether the effect differs between the two models.
- Whether serving nondeterminism is shared across cases.
- Whether the mirrors' templates equal the gated originals.
- How hosted services render what they receive.

## 9. The smallest experiment for the WP7 finding

This is not run, not authorized, and not the existing serialization proposal.

**Step 0, free:** ask the AgentDojo maintainers for the serving command and logs of the 2025-07-25 runs. A recorded `--max-model-len` below about 16.5k tokens, or logged 400 errors, settles the mechanism.

**Step 1, only if needed:** rerun exactly the 59 affected episodes.

- **Configuration:** the published one (provider `local`, benchmark v1.2.1, same attacks), with a context window that fits them (32,768), and the provider patched to record a failed request as an error instead of an empty answer.
- **Models:** Llama 3.3 70B Instruct, and Meta-SecAlign-70B (a LoRA adapter on the same base; gated, so it needs access).
- **Outcome:** each episode's attack and task result, substituted into the published counts to replace the bounds in section 7 with an estimate.
- **Why this addresses the finding:**
  - The finding concerns those 59 episodes and nothing else in the runs.
  - Rerunning them measures its consequence directly.
  - With the original limit restored, the same requests should fail, which tests the mechanism.
- **Limits:** a rerun is not the original run (serving nondeterminism, server version). It answers what these episodes score with the failure removed, not what they scored then.
- **Rough size:** about 59 episodes of up to about 20 calls, on two 80 GB GPUs for a 70B model in bf16, with startup dominated by downloading about 140 GB of weights. On the order of 1 to 2 GPU-hours. Prices were not checked because no rental is authorized.

The triple encoding (finding 2) needs a different experiment: the same model on a stratified subset of episodes under both representations. It is a serialization study of AgentDojo's own pipeline, larger than step 1, and lower priority.

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
- **Audit scope:** bounded by design (four harnesses, one fixture). Hosted services are invisible, and some templates are mirrors.
- **Scorers:** AgentDojo's state checks are the scorers. The project's earlier text-based scorer has no human validation (its protocol is prepared, not carried out).
- **Exploratory analyses:** written after the outcomes were known.

## 12. Contribution, release format, remaining work

**Strongest defensible contribution:** a methods and replication report with three parts.

1. A prompt-level audit method that accepts legitimate encodings, with evidence that it works: it found silent defects in this project's own earlier studies, two issues in AgentDojo's published open-model path with bounded consequences, and clean passes elsewhere.
2. A small, pre-registered, delivery-verified replication of the serialization effect on two open models. Its main lesson is about design: comparing each format with its own selected attack confounds format with attack wording, and the same-attack contrast is the one to register.
3. Repeatability measured under one stack, with its dependence structure stated.

None of these is established as a main-conference research finding.

**Release format:** an arXiv preprint or workshop paper (evaluation methodology or ML security), with the tagged repository and its evidence bundles as the artifact.

**Remaining work before release:**

- Report the two AgentDojo findings to its maintainers and ask for the serving configuration. This is outward-facing, so it is your decision.
- Decide whether step 1 of section 9 is worth funding.
- Merge `research-audit-2026-11` and tag a release. Your decision; not done.
- Have someone other than the author check the WP7 renderings and the decomposition code.
- Either carry out the human validation protocol for the earlier scorer or state plainly that it was not done.
- Optionally:
  - verify the mirrored templates against the gated originals if access is available;
  - measure InjecAgent's step-two prompt lengths.
