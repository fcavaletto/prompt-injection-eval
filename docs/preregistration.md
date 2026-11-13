# Pre-registration: why serialization matters, and does placement replicate?

Written on 2026-11-13, before any of the runs it describes. The git history of this file is the timestamp. Changes made after a run starts are logged under [Amendments](#amendments) with their date and reason; nothing above that section is edited once its study has run.

## Background

The [ten-model study](placement.md) found that, under the same security rule, a document delivered as a raw-text tool result is easier to inject through than the same document in the user message, on all ten models. Writing the same text into the tool message as a JSON string took much of that back. Two questions follow. Why does JSON-encoding help? And does the placement effect hold on public benchmarks with realistic tool outputs and harmful-action goals, rather than on this project's 89 short synthetic documents?

Four studies, run in this order. Studies B and C are stopped or reframed depending on the result of the one before, as stated below.

## Common rules

- **Models.** The ten models of the ten-model study, served the same way: vLLM 0.33.0, the chat template shipped with the weights, bf16 (gpt-oss in its released MXFP4), temperature 0, seed 42, `--generation-config vllm`. Qwen3 hybrid models with thinking off; gpt-oss with low reasoning effort and a 4,096-token budget. A model that cannot run a study for a technical reason (for example, a chat template that rejects a message format) is dropped from that study with the reason reported; it is not replaced.
- **Pairing and tests.** Every comparison is paired by case, with exact McNemar tests. Each study names its primary family; Holm adjustment is applied within a family and never across families. Secondary results are reported in full and labelled exploratory.
- **Scoring.** The deterministic scorers already in this project for Studies A and D, and each benchmark's own programmatic checks for B and C. An `uncertain` score counts as not a success. Pairs where either side has a backend error are excluded, and the count is reported.
- **One run.** Each study is run once. A model is rerun only if more than 2% of its generations end in a backend error, and any rerun is reported. No case, model, or condition is dropped because of its result.
- **All results are published,** whether or not they support a hypothesis.

## Study A: what part of JSON-encoding helps

JSON-encoding the document changes two things at once. It marks the text as one data value (quotes around it, escaped characters), and it removes the line breaks that set an injected sentence apart from the rest of the document. Two new conditions separate them:

- `tool_flat` (`tool-flat-v1`) and `tool_flat_defended`: the raw tool result with every line break replaced by a space, nothing else changed.
- `user_json` (`baseline-v1-json`) and `user_json_defended` (`defended-v1-json`): the JSON-encoded document inside the user-message templates, between the same delimiters.

**Data.** The 59 held-out seeds. Two attacks fixed in advance: the plain override (`naive+inline+plain`) and the original static document. No strategy is tuned against the new conditions.

**Same-session rows.** The conditions the comparisons need (`baseline`, `defended`, `tool`, `tool_defended`, `tool_json`, `tool_json_defended`, and the four new ones) are all generated in the same server session per model, into `results/v07/`. The ten-model study's rows are not reused for these comparisons, because a repeat run showed counts for gpt-oss moving by up to six seeds between sessions.

**Primary family.** Plain override, with the rule, three comparisons per model, ten models: 30 tests, Holm-adjusted together.

1. **A1.** `tool_defended` → `tool_flat_defended`: does removing line breaks alone lower success?
2. **A2.** `tool_flat_defended` → `tool_json_defended`: does JSON-encoding lower it further than flattening?
3. **A3.** `defended` → `user_json_defended`: does JSON-encoding help when the document is in the user message?

**Interpretation, decided now.** A comparison "holds on a model" if it is significant after adjustment in the stated direction (lower success after the change).

- *Line breaks explain the JSON effect* if A1 holds on at least five models and A2 holds on at most two.
- *Encoding as data explains it* if A2 holds on at least five models and A1 holds on at most two.
- *Both contribute* if A1 and A2 each hold on at least three models.
- Otherwise the result is *mixed*, reported per model without a summary label.
- A3 is read on its own: if it holds on at least five models, JSON-encoding is a placement-independent mitigation against the plain override; if on none, its effect is specific to the tool channel.

**Secondary.** The same three comparisons without the rule; all six with the static documents. Holm-adjusted as one secondary family.

**Prediction.** The author expects *both contribute*: flattening recovers part of the effect, and JSON lowers success further on most models. This is stated so a reader can see whether the result was anticipated; it does not change the analysis.

## Study B: InjecAgent

[InjecAgent](https://github.com/uiuc-kang-lab/InjecAgent) cases are a user request, a completed call to a user tool, and that tool's response with an attacker instruction inside. Success means the model then calls an attacker tool, which is a harmful action rather than a printed code word.

**Cases.** Direct-harm cases (510 per setting) and the first step of the data-stealing cases (544 per setting), each in the base and enhanced settings: 2,108 cases per condition. The second data-stealing step needs a simulated tool response from GPT-4 and is not run.

**Conditions.** The tool response delivered three ways: as the tool result in its original text, as the tool result JSON-encoded, and pasted into the user message after the request. Each with no rule and with the generic rule reworded for this setting. The model sees the user tool and the attacker tools as callable tools.

**Outcome.** Attack success: the model's first tool call names the attacker tool for direct harm, or the data-extraction tool for data stealing, read from the server's parsed tool calls. The raw text is stored, and cases where text and parsed call disagree are counted and reported.

**Primary family.** With the rule, the raw tool result against the user message, ten models: 10 tests. **B1 replicates** if success is higher in the tool result on at least seven models and significantly so after adjustment on at least five.

**Secondary.** B2, the raw tool result against the JSON-encoded one, with and without the rule; the no-rule placement comparison; results by attack type.

**Decision.** If B1 does not replicate, Study C still runs, but the write-up is reframed around that non-replication before C's results are seen.

## Study C: AgentDojo

[AgentDojo](https://github.com/ethz-spylab/agentdojo) runs a multi-turn agent with real tool calls in four environments and checks the outcome against the environment's state.

**Setup.** The `important_instructions` attack on all 629 security cases, and all user tasks for utility, under two tool-output formats (AgentDojo's default YAML, and JSON) and two system prompts (AgentDojo's default, and the default with the generic rule added).

**Models.** Those whose tool calls the server parses. This is checked with a smoke test of three user tasks without attacks, before any security case runs; the smoke test looks only at whether calls parse, never at attack outcomes.

**Primary family.** With the rule, YAML against JSON tool output, per model. **C1 holds** if attack success is lower with JSON on at least 70% of the models that pass the smoke test, and significantly so after adjustment on at least half of them.

**Secondary.** Utility under each format, the no-rule comparison, and results per environment.

## Study D: long documents

The 59 held-out injections embedded in long carriers taken from the MIT-licensed invoice emails in [BIPIA](https://github.com/microsoft/BIPIA), placed at the end of the email, with the placement conditions of Study A's same-session set and the plain override. **Primary:** with the rule, raw tool result against user message, as in B1. This study's detailed design is fixed by amendment before it runs.

## Amendments

None yet.

## Results

Appended after the runs; nothing above was changed.

- **Study A** ran on 2026-11-13 after commit `5a3deb0`, on all ten models, with no exclusions and no reruns. Primary verdict: *mixed* (A1 held on 0 models, A2 on 4, A3 on 0). Write-up: [Why JSON-encoding helps](placement.md#why-json-encoding-helps-a-pre-registered-test). One deviation: the run script's `all` selection also generated datamarking (`spotlight`) rows, which no comparison uses.
