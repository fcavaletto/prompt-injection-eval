# Appendix: evidence audit of 2026-11-14

Detail behind [Research audit and next step](research-next-step.md). Every analysis on this page is **exploratory**: it was designed after the Study A and Study B outcomes were known, and it carries no confirmatory weight. The published rows in `results-published/v07` and `results-published/v08` were read and not changed.

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

## D. Literature notes

Read on 2026-11-14 through a fetching tool that returned the first 40,000 characters or so of each paper verbatim and a machine summary of the rest. "Partly verified" marks claims that rest on the summary. Venue information for the two 2026 conference papers comes from search listings, not from the papers.

| Work | Identifier | Verification | Note relevant here |
| --- | --- | --- | --- |
| Nasr, Carlini et al., *The Attacker Moves Second* | arXiv:2510.09023 | Partly | 12 defenses; search and RL attacks and a human red-team; spotlighting and prompt sandwiching above 95% under search on AgentDojo. Nothing on serialization. |
| Zhan, Fang, Panchal, Kang, *Adaptive Attacks Break Defenses...* | arXiv:2503.00061 (Findings of NAACL 2025) | Partly | White-box GCG variants; 100 InjecAgent cases; Vicuna-7B and a fine-tuned Llama 3 8B; above 50% against all eight defenses. |
| Chang, Jun, Lee, *ChatInject* | arXiv:2509.22830 (listed as ICLR 2026) | Partly | Forged role tags in tool output. Explains success by the role hierarchy; evidence is success rates, template similarity and attention. No placement or serialization comparison. |
| Ye, Cui, Hadfield-Menell, *Prompt Injection as Role Confusion* | arXiv:2603.12277 (listed as ICML 2026) | Partly: sections 1 to 4.2 verbatim | Role probes on gpt-oss, Nemotron and Qwen3; forged reasoning traces; a style ablation. No behavioral role swap with content fixed was found in the text read; no causal intervention; no AgentDojo or InjecAgent. |
| Debenedetti et al., *AgentDojo* | arXiv:2406.13352 | Partly | 97 user tasks, 27 injection targets, 629 crossed cases. Tool output is YAML by default; no format ablation reported. Position ablation: injections near the end work best. |
| Zhan et al., *InjecAgent* | arXiv:2403.02691 | Partly | 17 user cases × 62 attacker cases, stated in the paper. Success by the tool invoked. Single turn acknowledged as a limit; the number of user cases is not. |
| Mou et al., *ToolHazard* | arXiv:2608.11878 | Text of section 7.2 verbatim; figure 4 not read | "Work in progress." Free-form output gives higher success than JSON or YAML "under identical settings". No numbers, models or case counts in the text. |
| Shaw, *Silent Failures in Agentic Security Evaluation* | arXiv:2609.32691 | Verbatim | Single-author audit of one harness. Undelivered payloads; tool-identity scoring 21.7% against 1.2% by arguments; incapacity scored as rejection. Scenarios treated as independent. |
| McCauley, Kan, Martin, *IH-Benchmark* | arXiv:2607.25987 | Partly | 2,336 scenarios, 37 models. System-over-user compliance does not predict resistance to tool-output injection. No matched content across channels. |
| Zhang et al., *IHEval* | arXiv:2502.08745 (NAACL 2025) | Partly | 3,538 examples, 13 models. A priority instruction in the system prompt did not help. |
| Rashidi, *Structural Role Injection in Handlebars-Templated LLM Prompts* | arXiv:2606.18120 | Partly | Escaped against raw template slots; escaping helps only for angle-bracket delimiters. User message only. |
| Yu, Cheng, Liu, *Defense ... via Tool Result Parsing* | arXiv:2601.04795 | Partly | Re-formatting tool results as a defense on AgentDojo. Point estimates only. |
| Hofer, Debenedetti, Tramèr, *Assessing Automated Prompt Injection Attacks in Agentic Environments* | arXiv:2606.10525 | Partly | GCG and TAP on AgentDojo; could not run one model for lack of a compatible tool-call template. |
| Nguyen et al., *INFUSE* | arXiv:2610.20776 | Partly | 19 models; validates its judge against blinded human labels; intervals treat cells as independent. |
| Lee, Kim, Lee, *Will the User Ever Know?* | arXiv:2608.30362 (EMNLP 2026) | Partly | Covert against overt success on AgentDojo. |
| Abdelnabi, Bagdasarian, *AI Agents May Always Fall for Prompt Injections* | arXiv:2605.17634 | Partly | Position paper with experiments; argues separation of data and instructions cannot be sufficient. |

Two searches aimed specifically at the proposed gap (attack success under different tool-result encodings with the template held fixed; sensitivity of results to the serving stack) returned no controlled study. That is evidence of a gap, not proof.

## E. Files

- `scripts/audit_exploratory.py`: the analyses.
- `results-published/audit-2026-11-14/`: `injecagent_dependence.csv`, `injecagent_competence.csv`, `injecagent_subgroups.csv`, `injecagent_smoke.csv`, `study_a_pooled.csv`, `study_a_per_model.csv`, `study_a_relative.csv`, `summary.json`.
