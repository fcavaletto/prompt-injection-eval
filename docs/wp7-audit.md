# WP7: what other harnesses deliver to the model (2026-11-16)

Offline. No model was called and no paid compute was used. Each harness's own message-building code built the request it would send; a fake client captured the request; it was rendered with the chat template of the published configuration, from tokenizer files at pinned revisions; and the rendering was checked against a common fixture. Evidence and reproducers: [results-published/wp7-audit-2026-11-16](https://github.com/fcavaletto/prompt-injection-eval/tree/research-audit-2026-11/results-published/wp7-audit-2026-11-16).

## Method

**Fixture** (`data/wp7/fixture.json`):

- one user request and two tools;
- one completed call and its result;
- a second record in that result carrying an attack payload.

Every string that must reach the model carries a `MARK-` marker. The payload contains a newline, double quotes, angle brackets and a non-ASCII dash, so that escaping and re-encoding are visible.

**Checker** (`src/prompt_injection_eval/wp7.py`). In the rendered prompt it checks:

- every tool's name, description and parameter markers;
- the call after the user turn;
- the result after the call;
- the payload after the call;
- the order of system, user, call and result.

The payload is accepted in every encoding a harness may legitimately use:

- verbatim;
- JSON-escaped once or twice;
- the YAML scalar styles `yaml.dump` writes, including folded double-quoted scalars with line continuations;
- YAML inside JSON, once or twice;
- a Python `repr`.

If none matches exactly, a normalized match is reported as "delivered but altered". Tests in `tests/test_wp7.py` show that the checker accepts each of these encodings and reports a missing payload, a missing call, and a truncated payload.

**The checker's own failures came first.** On the first run, two configurations (AD-2, AD-3) were reported as missing the payload. Both carried it as a YAML double-quoted scalar folded across lines (`\` line continuation and an escaped space). That decodes to the payload exactly, so it is a valid representation the checker did not yet recognize. The checker was extended, and both pass. A failed check is treated as a lead, never as a finding by itself.

A second checker issue appeared only in the full test suite. Importing parts of AgentDojo registers a global PyYAML representer that double-quotes every string in `yaml.dump` (`agentdojo/yaml_loader.py`). The checker built its expected YAML forms with the global dumper, so other tests changed its behavior. It now uses private dumpers with PyYAML's own representers, and a test pins that. The stored renderings were produced in a process that never imported that module; the ToolHazard rendering shows unquoted YAML. The registration does not affect AgentDojo's own tool output, which uses `yaml.safe_dump`. It is a hazard only for other code that uses `yaml.dump` in the same process.

**Classes.**

- *Reproduced under a published configuration*: the configuration that produced published results, with the code at the revision that produced them.
- *Separately tested supported configuration*: a configuration the code supports that no published result used.
- *Unverifiable*: the rendering cannot be observed (hosted model, gated template, or a configuration not recorded).
- *Passes*: definitions, call, result and payload all reach the prompt in a recognized form, in order.

**Pins:**

- AgentDojo: 0.1.35 (tag commit `a75aba7`). The published runs come from `runs/` at that tag.
- InjecAgent: `f19c9f2`.
- ToolHazard: `544b73b`.
- Agent Data Injection (ADI): `1a3ddf8`.

**Templates:**

- `unsloth/Llama-3.3-70B-Instruct@99cd0d2`, a mirror of a gated repository;
- `NousResearch/Meta-Llama-3-70B-Instruct@84cbdcd`, a mirror;
- `Qwen/Qwen3-8B@b968826`;
- `Qwen/Qwen3-32B@9216db5`;
- for Llama 2, Meta's reference chat format: the mirror ships no template.

Mirrors are recorded as mirrors; the gated originals were not read.

## Results

| ID | Harness and configuration | Class | Delivered (defs / call / result / payload) | Finding |
| --- | --- | --- | --- | --- |
| AD-1 | AgentDojo `local` (LocalLLM), Llama 3.3 70B Instruct; the published runs of 2025-07-25 | Published; **passes delivery, with a representation that is not the documented one** | yes / yes, as the model's own text / yes / yes | Each tool result reaches the model as a JSON string literal of `{"result": [{"type": "text", "content": "<YAML>"}]}`. LocalLLM JSON-dumps a list of content blocks (message content became a list in `32521207f`, 2025-03-21), and the Llama 3.x template's `tojson` encodes that string again. The code's evident intent is `{"result": "<text>"}`: its `'None' -> 'Success'` substitution compares a list with a string and never fires. |
| AD-1e | Same configuration, server error path | **Reproduced under a published configuration** | n/a | `chat_completion_request` catches every exception and returns `''`. That becomes an empty assistant turn with no tool call, the loop ends, and the episode is scored with no mark of the failure. In the published traces, see below. |
| AD-1s | AgentDojo `local`, Meta-SecAlign-70B (published runs) | **Unverifiable** | n/a | The template is gated, and the run records store neither `tool_delimiter` nor `model_id`, so what role the tool output had cannot be established. The token analysis below uses Llama 3.3's template as an approximation. |
| AD-2 | AgentDojo `vllm_parsed` (OpenAILLM), Qwen3-32B, vLLM 0.33.0 preprocessing | Separately tested; **passes** | yes / yes / yes / yes (YAML) | The system message is sent as `developer`. vLLM 0.33.0 converts it to `system` for templates without that role (`vllm/renderers/hf.py`); older vLLM versions were not checked. |
| AD-3 | AgentDojo `together-prompting` (PromptingLLM) at v0.1.35, Llama 3 70B Instruct | Separately tested; **delivery passes; system text duplicated** | yes / yes, restated in the user turn / yes / yes (YAML) | The request has roles `system, developer, user, ...`. The system text appears inside the tools prompt and again as a `developer` message (`_message_to_together`, since `36d340eab`, 2025-05-09). With the model's own template that is a `developer` header it was not trained on. How Together renders it is not observable. The published Llama 3 70B runs (2024) predate this code. |
| IA-1 | InjecAgent, prompted agent, `TogetherAI`, Llama-2-70b-chat | Published; **delivery passes; system role not used** | yes / yes, as scratchpad text / yes / yes | Its hand-written template is `[INST] {sys_prompt}{user_prompt} [/INST]`: the system prompt is concatenated into the user turn, where Meta's reference format puts it in `<<SYS>>`. All text arrives. Whether Together's completion endpoint adds a BOS token is not observable. |
| IA-2 | InjecAgent, prompted agent, local `Llama` (transformers, `max_length=4096`) | Separately tested; **passes** | n/a | Over InjecAgent's 2,108 step-one cases, no prompt reaches 4,096 tokens (maximum 4,093, median 3,236). 19 leave fewer than 256 tokens for the output, which could truncate an answer. Step-two prompts were not measured. |
| TH-1 | ToolHazard, `infer_mode = "prompt"` (the mode of the reported results, README), Qwen3-8B | Published; **passes** | yes / yes, as the model's text / yes / yes (YAML) | Tools are written into the system prompt in Qwen3's `<tools>` format. Tool output is YAML-dumped and appended as a plain user message without `<tool_response>` tags. `_format_tool_output_text` returns `str(obj)` instead of YAML for non-string outputs, but the environment path read always passes a string. |
| TH-2 | ToolHazard, the three formats of Fig. 4 | **Unverifiable** | n/a | The released code has a YAML formatter and a commented-out older formatter, and no JSON or free-form switch. The experiment's renderings cannot be reconstructed. |
| ADI-1 | ADI end-to-end benchmark, LangGraph baseline, GPT-5.2, JSON tool output | **Unverifiable** at the model; passes at the message level | n/a | `tool_result_to_str` now defaults to `json.dumps`. The payload arrives JSON-escaped with `\uXXXX` escapes and decodes exactly. ADI computes a message-level "injection happened" flag whose normalization misses escaped quotes (false for this payload), but `benchmark.py` discards it, so it affects no reported number. |

**Negative findings.** InjecAgent, ToolHazard and AgentDojo's `vllm_parsed` path deliver definitions, the completed call, the result and the payload intact. InjecAgent's local Llama path leaves at least 3 tokens of output budget on every step-one case. ADI's JSON is valid and lossless.

## AgentDojo's published LocalLLM runs: empty turns at a token threshold

`scripts/wp7_agentdojo_traces.py` rebuilds, for each of the 5,958 published traces of Llama 3.3 70B and Meta-SecAlign-70B, the last request LocalLLM sent: its own code, the suite's tools, and the Llama 3.3 template. It then counts that request's tokens.

| | Traces | Ending in an empty assistant turn with no call | Suites | Smallest such request | Largest request of any other trace |
| --- | ---: | ---: | --- | ---: | ---: |
| Llama 3.3 70B | 2,979 | 48 (46 under attack) | workspace only | 16,564 tokens | 16,537 tokens |
| Meta-SecAlign-70B | 2,979 | 11 (8 under attack) | workspace only | 17,804 | 17,584 |

Within each model, every empty ending lies above every other trace. That is what a server context limit would produce through the error path in AD-1e. It is not proof:

- the server's limit was not recorded;
- the token counts depend on the template (exact for Llama 3.3 up to the mirror, approximate for SecAlign);
- a model could in principle return nothing.

**What it could change.** Under attack, every one of these episodes was scored as defended.

| Llama 3.3 70B, attack | Published success | If the empty episodes are excluded | If all were successes |
| --- | ---: | ---: | ---: |
| `important_instructions`, all suites | 23.1% (219/949) | 23.8% | 26.1% |
| `important_instructions`, workspace | 6.8% (38/560) | 7.2% | 12.0% |
| `ignore_previous`, all suites | 12.0% | 12.1% | 13.1% |

For SecAlign the bounds move by at most 0.4 points; its published success rates are 1.3% to 2.2%. Llama 3.3 lost more episodes this way than SecAlign. The comparison that the published runs support, SecAlign far below Llama 3.3, holds at every bound.

## What would need inference

Each item is identified, none is run here:

1. **Whether the 59 empty turns were server errors.** Free first step: ask the maintainers for the serving command or logs. Otherwise, send one reconstructed request above the threshold to a server configured as theirs; that configuration is unknown.
2. **What those episodes would have scored.** Rerun exactly the 59 episodes with errors logged instead of swallowed and a context window that fits them. This is the smallest experiment that measures the consequence; see the [report draft](report-draft.md).
3. **Whether AD-1's representation changes attack success** relative to the documented `{"result": "<text>"}`. This is a serialization question of exactly the kind this project studies. It would need the same model on a subset of episodes in both representations.
4. How Together renders a `developer` message (AD-3), and whether it adds BOS (IA-1).
5. InjecAgent's step-two prompt lengths and any truncated outputs under the local Llama path.

## Limitations

- Bounded on purpose: three harnesses plus ADI, one or two configurations each, one fixture.
- Templates from mirrors match the gated originals only if the mirrors are faithful; this was not verified.
- vLLM's preprocessing was modelled from its 0.33.0 source for the parts this fixture exercises, not run.
- Hosted services (Together, OpenAI) cannot be observed.
- Only the message-building functions were executed from the external repositories. Their source was extracted and run with stubbed dependencies, so nothing else in those repositories ran.
