# Appendix: evidence audit of 2026-11-14

Detail behind [Research audit and next step](research-next-step.md). Section D was replaced on 2026-11-15 after the closest papers were read in full; the rest is as written on 2026-11-14. Every analysis on this page is **exploratory**: it was designed after the Study A and Study B outcomes were known, and it carries no confirmatory weight. The published rows in `results-published/v07` and `results-published/v08` were read and not changed.

To rebuild every table here from the published rows, without a GPU:

```bash
python scripts/audit_exploratory.py   # writes results-published/audit-2026-11-14/
```

Intervals are 95% percentile intervals from 10,000 bootstrap replicates (seed 20261114). "Two-way" resamples both crossed factors.

## A. State of the repository

Checked on 2026-11-14. Branch `remote-provider` at `7e006a9`, pushed, working tree clean. `main` is at `d7da74f` (0.5.0), so the ten-model study, the pre-registration, and Studies A and B are not yet on `main`. This audit is on a new branch, `research-audit-2026-11`.

## B. What the model actually saw

The single most consequential finding of the audit. Each Study B row stores a hash of the prompt the server rendered, and the first three rows per condition store the prompt itself. Reading them:

| Model | Tool definitions in the prompt | Completed tool call rendered (tool placements) | Rendered prompt stored |
| --- | --- | --- | --- |
| Qwen3 (4), Qwen2.5-7B, Hermes 3 | Yes | Yes | Hash on every row, text for 18 rows |
| Granite 3.3 8B | Yes | **No.** An empty assistant turn precedes the tool result | Same |
| Phi-4-mini | **No.** No tool name or schema appears anywhere in the prompt | **No** | Same |
| gpt-oss-20b, gpt-oss-120b | Unknown | Unknown | **None.** No hash and no text on any of 25,296 rows |

- **Phi-4-mini** was served with the chat template shipped with its weights, which does not render the `tools` list the API passes. Its 0 parsed calls in 12,648 rows are not behavior and not "a floor of the measure". The model was never told a tool existed. The same template was used for the synthetic study, where its tool placement was `<|assistant|><|end|><|tool|>document`, with no schema and no call.
- **Granite 3.3** saw the tools, but its template dropped the assistant's completed call from the history. In the synthetic study its tool placements had the same empty assistant turn.
- **gpt-oss.** vLLM's Harmony path does not return the rendered prompt. The one sample kept in `results-published/v06/renders/` was produced separately, and it reads "Reasoning: medium" where the runs requested low effort. Whether the requested effort reached the prompt is not verifiable from what was stored.
- **Qwen3 and Qwen2.5** render a tool result inside a *user* turn, wrapped in `<tool_response>` tags. Hermes 3, Granite and Phi use a separate `tool` role token.
- **The smoke test could not have caught this.** It used benign tool responses, where answering in text is correct, so nine of ten models produced no parsed call (0 of 18 units). Nothing before the main run showed that any model could produce a call the server would parse.
- **InjecAgent's "raw" tool response is already quoted.** The stored string is a Python-style dictionary inside double quotes. "JSON-encoded" in Study B therefore means encoding an already quoted string a second time, which is a much smaller change than in Study A.

`render_defects` in `src/prompt_injection_eval/injecagent.py` now performs this check on every row, and a test reproduces the Phi-4-mini and Granite defects from the published prompts.

## C. The review concerns, one by one

### C1. Causal attribution

**Evidence.** The user-message and tool-result conditions of the synthetic study differ in all of these:

1. The wrapper tokens around the document (template-specific).
2. The `--- BEGIN UNTRUSTED DOCUMENT ---` and `--- END ... ---` lines, present only in the user message.
3. The label "Untrusted document:", present only in the user message.
4. The rule's wording ("the following document" against "the output of the read_document tool").
5. The rule's distance: same turn in one, two turns earlier in the other.
6. An assistant tool-call turn between the rule and the document.
7. A tool definition in the system prompt, present only in the tool conditions.
8. The sentence "The document for this task is available through the read_document tool."
9. The line "Complete the original task." after the document.

The `defended_no_tail` control removes only item 9. In Study B the user-message placement additionally has no completed call, which changes the agent's task state.

**Judgment.** The reviewer is right, and the problem is larger than stated: on Qwen the role token is `user` in both conditions, so the claim "it is the role" is false at the level of tokens for the family where the effect is clearest.

**Severity.** High. **Remedy.** Describe the result as a difference between two prompt constructions. In new work, vary one rendered feature at a time and make no claim about roles.

### C2. Statistical inference

**Interactions.** Study A's pre-registered rule read A3 (JSON in the user message, with the rule) as "specific to the tool channel" because it was significant on no model. Tested directly, pooled over ten models and 59 held-out seeds:

| Cell | Raw successes of 590 | JSON successes of 590 | Change, points | Change, relative |
| --- | ---: | ---: | ---: | ---: |
| Tool result, rule | 364 | 218 | −24.7 | −40% |
| User message, rule | 107 | 78 | −4.9 | −27% |
| Tool result, no rule | 519 | 379 | −23.7 | −27% |
| User message, no rule | 357 | 223 | −22.7 | −38% |

| Contrast | Pooled, points | Two-way interval | Models down / up |
| --- | ---: | --- | --- |
| JSON by placement, with the rule | −19.8 | −28.5 to −11.2 | 10 / 0 |
| JSON by placement, no rule | −1.0 | −14.2 to 11.9 | 5 / 5 |
| JSON in the user message, with the rule (A3) | −4.9 | −10.2 to −0.2 | 6 / 2 |
| Removing line breaks (A1) | −6.1 | −11.4 to −1.5 | 9 / 0 |
| JSON after removing line breaks (A2) | −18.6 | −25.1 to −12.9 | 10 / 0 |

**Judgment.** The reviewer's method point is right. The direct test does find an additive interaction with the rule. But it is absent without the rule, and on the ratio scale the four cells look alike. The user-message cell with the rule starts at 18%, so it has little room to fall. The better reading is that JSON-encoding lowers plain-override success by roughly a quarter to two fifths wherever the document sits. Two published sentences are corrected by dated notes: "its effect is specific to the tool channel", and "flattening contributed nothing measurable".

**Absence.** With 59 seeds and Holm over 30 tests, a per-model test could reach significance only with 11 or more discordant seeds all in one direction (about 19 points). "Held on 0 models" for A1 was a statement about power.

**Severity.** Medium. **Remedy.** Pre-register interaction contrasts and their scale; claim absence only inside a stated margin.

### C3. Dependence and generalization

**Verified.** The vendored data has 2,108 cases built from 17 user contexts (one instruction, one tool, one argument set and one response template each), 62 attacker goals (30 direct harm, 32 data stealing), and 2 wordings. Every enhanced case is its base case with one fixed sentence in front of the instruction. The design is fully crossed: 17 × 62 × 2.

**Effect on the primary comparison** (raw tool result minus user message, with the rule), in percentage points:

| Model | Difference | Interval, cases as independent | Two-way interval | Design effect | User contexts up / down | Sign-flip p over 17 contexts | McNemar p as published |
| --- | ---: | --- | --- | ---: | --- | ---: | ---: |
| Qwen3-4B | +14.0 | 12.0 to 15.9 | 7.7 to 20.7 | 11.1 | 16 / 1 | 0.0002 | 4e-48 |
| Qwen3-8B | +6.3 | 4.6 to 8.1 | −2.1 to 14.9 | 23.3 | 13 / 2 | 0.17 | 3e-13 |
| Qwen3-14B | +10.5 | 9.0 to 12.1 | 4.7 to 18.5 | 20.7 | 16 / 1 | 0.00005 | 3e-45 |
| Qwen3-32B | +6.0 | 4.5 to 7.6 | 0.9 to 13.2 | 16.4 | 11 / 2 | 0.018 | 2e-17 |
| Qwen2.5-7B | −2.2 | −4.2 to −0.1 | −6.2 to 1.8 | 3.9 | 5 / 10 | 0.14 | 0.04 |
| Hermes 3 8B | −48.9 | −51.3 to −46.4 | −59.1 to −38.4 | 18.2 | 0 / 17 | 0.00002 | under 1e-300 |
| gpt-oss-20b | −0.1 | −0.9 to 0.5 | −1.3 to 1.3 | 3.1 | 2 / 5 | 0.81 | 0.78 |
| gpt-oss-120b | −0.5 | −0.9 to 0.0 | −1.6 to 0.0 | 4.0 | 0 / 2 | 0.50 | 0.05 |

Granite 3.3 and Phi-4-mini are omitted: every cell is zero, for the reasons in section B. The design effect is the ratio of the two-way bootstrap variance to the variance with the 1,054 crossed cells treated as independent.

**Judgment.** The reviewer's count is exact. Two refinements. First, the crossed design gives 62 clusters on the attacker side and a clean estimate within each user context; the weak direction is generalizing to *new user tasks*, where there are 17. Second, the published verdict does not change: the criterion needed seven models and got four, and under clustering by user context three of the four keep an interval above zero, two after Holm adjustment over the ten tests. The statement "significantly so on all four" does not survive for Qwen3-8B.

The four Qwen3 sizes are one family. Among the three families whose conversations were valid and checkable (Qwen3, Qwen2.5, Hermes 3), the effect appears in one, is absent in one, and is reversed by a confound in one.

**Severity.** High. **Remedy.** Two-way cluster bootstrap as the primary interval, a sign-flip test over the smaller factor as a check, and results counted by family.

### C4. Measurement validity

Per model, with the rule (the full table for all six conditions is `injecagent_competence.csv`):

| Model | Condition | Rows with a parsed call | First call is the attacker's tool | First call re-runs the user's tool | Cut off at the budget | Target named in text, no call |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3-4B | user message | 600 | 578 | 22 | 78 | 103 |
| Qwen3-4B | tool result | 883 | 873 | 9 | 80 | 81 |
| Qwen3-8B | user message | 373 | 357 | 1 | 2 | 193 |
| Qwen3-8B | tool result | 493 | 489 | 1 | 5 | 122 |
| Qwen2.5-7B | user message | 755 | 531 | 196 | 77 | 136 |
| Qwen2.5-7B | tool result | 616 | 485 | 128 | 41 | 82 |
| Hermes 3 8B | user message | 1,825 | 1,040 | 596 | 5 | 29 |
| Hermes 3 8B | tool result | 10 | 10 | 0 | 2 | 170 |
| gpt-oss-20b | user message | 58 | 45 | 13 | 0 | 125 |
| gpt-oss-20b | tool result | 69 | 42 | 27 | 0 | 101 |

- **The placement effect is mostly about whether any call is made.** On Qwen3, 94% to 100% of calls go to the attacker's tool in every condition; what changes is how often the model calls anything.
- **The security rule raised attacker calls on three models.** Qwen3-8B 82 to 357 in the user message and 204 to 489 in the tool result; Hermes 3 705 to 1,040; Qwen2.5-7B 419 to 531. In the user message, all three survive clustering by user context (p at most 0.0007). The rule ends with "complete the original task", which may prompt tool use. This was visible in the published table and not discussed.
- **Tool name against harmful objective.** For direct harm, where the attacker's instruction names an identifier or an address, 77% to 98% of attacker calls carry all of them in their arguments (model and condition pairs with at least 30 such calls; the lowest are gpt-oss-120b). The tool name is a fair proxy there. For data stealing, success is a read; the send step is not run, and the email tool appears in the same turn in at most 178 of 571 successes.
- **The "named in text" flag is crude.** On Qwen3-8B in the user message it fires on 253 rows without the rule, three times the number of successes. It needs human labels before it means anything.
- **Truncation** reached 121 of 2,108 rows (Qwen3-4B) and 144 (Granite) in one condition, under the 256-token budget.
- **InjecAgent's function schemas are odd.** Its converter turns an array parameter into an array of objects with the parameter's own name, so models emit `{"guest_ids": [{"guest_ids": "guest_amy01"}]}`. This is upstream behavior, ported unchanged.

**Judgment.** The reviewer is right. The stored-label test shows the code is consistent, not that the label means "the attacker's goal was achieved". **Severity.** High. **Remedy.** Positive controls read before attack outcomes, the rendered-prompt check, outcome-level scoring, and a blind human sample.

### C5. Reproducibility

| Item | Found | Status |
| --- | --- | --- |
| Model revision | Model name only; no commit hash requested or recorded | Open |
| Tokenizer and chat template | Not hashed. Recoverable only from stored prompts, which gpt-oss lacks | Open |
| Parser | Recorded in `launch_args`, a string the operator types | Open: declared, not verified |
| Serving image | Tag `v0.33.0`, not a digest | Open |
| Dependencies | Lower bounds in `pyproject.toml`; no lock file | Open |
| Rendered prompt | Every row in Study A (eight models); hash plus 18 samples per model in Study B; nothing for gpt-oss | Partly open |
| Resume keys | Did not include the prompt, the tools, the tool choice or the serving flags, so an edited prompt or a restarted server could silently reuse or mix rows | **Fixed for the InjecAgent runner;** open for the adaptive runner |

**Judgment.** Correct on every point. **Severity.** Medium now, high for a paper. **Remedy.** Work package WP1.

## D. Literature, re-verified on 2026-11-15

The first version of this section (2026-11-14, commit `31b63c5`) was written from a fetching tool that returned the opening of each paper and a summary of the rest. On 2026-11-15 the closest papers were read directly from the arXiv full text, their figures and, where released, their code. Bibliographic data for every entry was checked against the arXiv API. Three statements in the first version were wrong and are corrected here:

- **ToolHazard does report numbers.** They are in its Figure 4, which the first version had not read.
- **A controlled study of the serving stack does exist**, for tool-call capability though not for security: Tang and Zheng, with Pape et al. and Masoudian et al. for benchmarks in general. The first version said two searches had found none.
- **Yu et al. do not re-format tool results.** Their defense has a model extract only the fields it needs.

"Direct" means the cited sections were read in full text by the assistant on 2026-11-15. "Metadata only" means title, authors, date and venue comment were checked and the content claim still rests on the 2026-11-14 partial reading. No claim in this project should cite a "metadata only" row for content without reading it first.

### D1. Closest work

| Work | Verified how | What it establishes | What it leaves open |
| --- | --- | --- | --- |
| Shaw, *Silent Failures in Agentic Security Evaluation*, arXiv:2609.32691 v1 (single author, not peer reviewed) | Direct, whole paper. Code not located: the paper says it is released but the text read gives no address. | Four defect classes in one benchmark harness (Sec. IV): payloads never delivered (39 of 43), success scored by tool name (21.7% against 1.2% by arguments, Table I), incapacity and environment errors scored as defense rejections, no per-scenario trace. A capability probe; a model that cannot call tools is "unmeasurable rather than secure" (Sec. VII-C). Loader-level feasibility checks (Sec. V-D). | Delivery is checked against the environment, not against the prompt the model receives. Nothing on chat templates, serving stacks or serialization. Scenarios are treated as independent. 43 attack scenarios, one harness. |
| Mou et al., *ToolHazard*, arXiv:2608.11878 v1 ("Work in Progress") | Direct: Sec. 6.1, 7.1, 7.2, Fig. 4 (image read), App. D. Code read at commit `544b73b`. | **Tool-output format changes attack success on frontier models** (Sec. 7.2, Fig. 4). GPT-4.1, "basic combined" attack: 52.6% free-form, 5.9% JSON, 1.2% YAML. GPT-4.1, "tool selection": 80.4%, 62.0%, 75.6%. Gemini-3.1-Pro, "basic combined": 4.7%, 2.4%, 3.5%; "tool selection": 77.7%, 40.5%, 32.6%. | Two models, two attacks, 87 tasks, no intervals. The formats are not defined in the paper. The released agent has a YAML formatter, an older free-form formatter left as comments, and no JSON formatter or switch that I could find, so the figure cannot be rebuilt from the release as it stands. All reported results use prompt mode, where tool output is appended as a user message (README). Attacks are fixed, not written for each format. No defense. The proposed reason ("semantic boundaries") is a hypothesis without a test. |
| Tang and Zheng, *Measuring the Serving Stack Instead of the Model*, arXiv:2609.26693 v1 (REALM workshop at EMNLP 2026) | Direct, whole paper except some tables. Code not read. | **The serving layer confounds tool-use evaluation.** Ollama gates the `tools` request per model, a refused request is logged as a model that did not call, and a capable model is reported at 0%. The same request is handled four ways by Ollama, llama.cpp, vLLM and SGLang. A checklist: fix and report the stack, log serving failures separately, diagnose a 0% call rate before blaming the model. | About emitting a tool call, not about what a tool result looks like once it is in the history. Capability, not security. No attack, no defense. |
| Chang, Jun, Lee, *ChatInject*, arXiv:2509.22830 v3 (arXiv comment: ICLR 2026) | Direct: Sec. 3, 4.1, 4.2, 5.1, 6, App. B, C.3, C.4, D. | Wrapping a payload in the target's own role tags raises success (5.18% to 32.05% on AgentDojo, 15.13% to 45.90% on InjecAgent, abstract); transfer grows with template similarity (Sec. 5.1); prompt defenses do not stop it (Sec. 6.1). | Models were reached through OpenRouter providers (App. D), so the serving stack is neither controlled nor known. The paper does not say whether the forged tags reached the model as control tokens. Tool-output serialization is not varied. |
| Ye, Cui, Hadfield-Menell, *Prompt Injection as Role Confusion*, arXiv:2603.12277 v6 (PMLR 306, ICML 2026) | Direct: abstract, Sec. 1, 4.2, 5.2, 7.4, App. G, J, K. | In four open models, text that sounds like a user is represented as user text even inside tool tags: "Userness" stays at 76% to 88% (Sec. 4.2, Table 1). On gpt-oss-20b, how an injection is framed predicts success from 2% to 70% (Sec. 5.2, Fig. 10); frames that look like tool data or JSON score lowest (App. J, Fig. 31). | Varies the attacker's wrapping, not the harness's rendering. One model for the behavioral result, 10 web pages, one command. No comparison of serializations chosen by the defender, and no defense. Its finding predicts that changing only the role tag should do little, which agrees with this audit's reading of Study B. |
| Pape, Evertz, Schönherr, *The Silent Hyperparameter*, arXiv:2605.19537 v3 | Abstract only | Inference backend alone shifts benchmark scores by up to 16.6 points; the stack is rarely reported. | General benchmarks; cause traced to numerical optimizations, not templates. Not security. |
| Masoudian et al., *What We Observe as LLM Behavior Can Be a Side-effect of Inference Backend*, arXiv:2608.04714 v1 | Direct: abstract, Sec. 1 | Five backends, three small models, six benchmarks: backend is a non-negligible factor; names template rendering as one route. | Not tool use, not security. |
| Yao et al., *Harness-Bench*, arXiv:2605.27922 v2 | Abstract only | Agent results vary by harness with the model fixed. | Not security. |
| Yu, Cheng, Liu, *Defense ... via Tool Result Parsing*, arXiv:2601.04795 v1 | Direct: Sec. 3.2, 3.3, 4.1 | A second model call extracts only the fields the agent needs from a tool result; AgentDojo; gpt-oss-120b, Llama-3.1-70B, Qwen3-32B. | A filtering defense, not a serialization comparison. |
| Rashidi, *Structural Role Injection in Handlebars-Templated LLM Prompts*, arXiv:2606.18120 v1 | Abstract direct; body not re-read | HTML escaping in a prompt template neutralizes angle-bracket role delimiters and not others. | Application templates, user content. |
| Deng et al., *Automating Agent Hijacking via Structural Template Injection*, arXiv:2602.16958 v1 | A few passages only | Attack success depends on tag-like structure surviving. | Not read closely. |
| Fogel et al., *Inference-Time Backdoors via Chat Templates*, arXiv:2602.04653 v4 | Metadata only | Chat templates as a supply-chain attack surface. | **Unresolved**: not read. |
| AgentDojo, arXiv:2406.13352 v3, and its code at commit `089ed46` | Code read: `tool_execution.py`. Paper: metadata only. | Tool results are rendered with `yaml.safe_dump` by default; the docstring notes `json.dumps` would also work. The arXiv comment on v3 records "fixing a bug in the Llama implementation". | No format comparison in the code read. |
| Hofer, Debenedetti, Tramèr, arXiv:2606.10525 v1 | Direct: Sec. 2.1 and the configuration appendix | Notes that one attack "was not evaluated against Gemma3-4B because no compatible" chat template was available. | The census finds the same: Gemma 3's template rejects tool messages. |

### D2. Checked for metadata only

Nasr et al., *The Attacker Moves Second* (arXiv:2510.09023); Zhan et al., *Adaptive Attacks Break Defenses...* (arXiv:2503.00061, Findings of NAACL 2025); Zhan et al., *InjecAgent* (arXiv:2403.02691, Findings of ACL 2024); McCauley et al., *IH-Benchmark* (arXiv:2607.25987); Zhang et al., *IHEval* (arXiv:2502.08745, NAACL 2025); Nguyen et al., *INFUSE* (arXiv:2610.20776); Lee et al., *Will the User Ever Know?* (arXiv:2608.30362, EMNLP 2026); Abdelnabi and Bagdasarian (arXiv:2605.17634). What the first version said about their content has not been re-verified.

### D3. Novelty claims that remain unresolved

- **Whether anyone has published the crossed structure of InjecAgent as a statistical problem.** Not found in the papers read; no targeted search was run.
- **Whether a prompt-level delivery check exists elsewhere.** Shaw's checks are the nearest and work at the environment level. Code for that paper was not located.
- **Fogel et al.** has not been read.
- **Search coverage.** Two extended web searches on 2026-11-15. Work that does not use the words "template", "serialization" or "serving" could have been missed.

## E. Files

- `scripts/audit_exploratory.py`: the analyses.
- `results-published/audit-2026-11-14/`: `injecagent_dependence.csv`, `injecagent_competence.csv`, `injecagent_subgroups.csv`, `injecagent_smoke.csv`, `study_a_pooled.csv`, `study_a_per_model.csv`, `study_a_relative.csv`, `summary.json`.

Added 2026-11-15:

- `scripts/rendering_census.py`, `scripts/ollama_render/`, `data/rendering_census/`: the [rendering census](rendering-census.md); results in `results-published/rendering-census-2026-11-15/`.
- `scripts/annotation_sample.py`, `data/annotation/study-b-v1/`: the blinded sample for the [human validation protocol](annotation-protocol.md). Not yet labelled.
- [Corrections](corrections.md) and `results-published/CORRECTIONS.md`.
