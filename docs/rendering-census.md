# Rendering census (2026-11-15)

A chat API receives a list of messages and a list of tools. The model receives one string. The code in between, a chat template plus the serving software around it, decides what that string contains. This census asks what that code does to one fixed conversation with a completed tool call, across the models this project and its closest literature have made claims about.

No model weights were downloaded and nothing was generated. The census cost nothing.

**What it found, in one paragraph.** Among 18 distinct templates, 3 do not show the model its tool definitions, 6 do not show the completed call with its function name, and 3 do not show the tool result. Only one of them, Gemma 3, says so with an error; the others render a prompt that looks normal. The turn that carries a tool result is a user turn in 5 templates, a dedicated tool role in 7, and something else in 3. Four templates JSON-encode tool output by themselves, so "raw text" passed by a harness reaches the model quoted and escaped. In all eight families where both could be rendered, the Hugging Face template and the Ollama library template disagree on at least one of these points.

## How each observation was obtained

Every row in the results says which of these it is. They are not interchangeable.

| Label | What ran | What it is evidence of |
| --- | --- | --- |
| `transformers` | `tokenizer.apply_chat_template` from transformers 5.22.1, on the tokenizer files of a pinned repository revision | The actual implementation, at tokenizer level. Not a server. |
| `transformers_jinja` | The template file rendered by the Jinja environment transformers uses, without the tokenizer | Same, without token IDs. Used for Kimi K2, whose tokenizer needs remote code, which was not run. |
| `vllm_replay` | Prompts that a vLLM 0.33.0 server returned during Study B, compared with a transformers rendering of the same conversation | A server observation, but of the Study B conversations (one completed call, string content), not of the census fixtures. |
| `ollama_template` | Ollama library templates, rendered by Ollama's own `template` package at v0.34.4 through a small Go program that mirrors `server.renderPrompt` | Code-level. No Ollama server ran: the truncation, tokenization and request checks a server adds are not exercised. |
| not observed | llama.cpp; vLLM's Harmony path for gpt-oss; Mistral's `mistral-common` path; any hosted API | Nothing. See "What it could not establish". |

An attempt to observe a running Ollama server failed: the four models listed on this machine had manifests but no weight files, and weights were not downloaded.

## Sample and its limits

The sample was fixed, with revisions pinned, in commit `99124bd` before any model other than Qwen3-8B (used to develop the script) had been rendered. It is in [`data/rendering_census/sample.json`](https://github.com/fcavaletto/prompt-injection-eval/blob/research-audit-2026-11/data/rendering_census/sample.json).

- **Group A (10 repositories):** every model in Studies A and B.
- **Group B (13):** open models used as the agent or probe model in the closest literature: ChatInject, ToolHazard, Role Confusion, Silent Failures, the serving-stack confounds paper, and Yu et al.
- **Group C (3):** the Study R candidates not already included.
- **Ollama (11 library tags):** the Ollama entries for the Group A families plus Llama, Gemma, Mistral and DeepSeek-R1.

Limits:

- It is not a random or popularity-weighted sample of open models. It is the set of models this project and its closest literature made claims about, so it says how often these issues touch that literature, not how often they occur on the Hub.
- Models that share a template are one observation. The 26 repositories reduce to 18 templates: five Qwen3 checkpoints share one, the two Qwen2.5 checkpoints share one, the two gpt-oss checkpoints share one.
- Four official repositories are gated (Llama 3.1, Llama 3.2, Llama 4, Gemma 3). Ungated mirrors were read instead and are recorded as mirrors.
- Two repositories ship no chat template (Mistral Small 3.2, DeepSeek-V3.2) and are not counted. One of the 18 templates (Gemma 3) rejects any tool message with an error.
- Closed models cannot be observed at all.

## Fixtures

Four conversations in [`data/rendering_census/fixtures.json`](https://github.com/fcavaletto/prompt-injection-eval/blob/research-audit-2026-11/data/rendering_census/fixtures.json). Every string that must survive carries a marker, so each check is a string search and not a judgment.

- **`single_call`:** system, user, an assistant tool call, its result; two tool definitions.
- **`multi_tools`:** the same with four definitions: a nested object, an array, an enum, and quotes and non-ASCII text in descriptions.
- **`hostile_output`:** the tool output is one record with quotes, newlines, a tab, a backslash, non-ASCII text, nested data, and strings that look like control tokens. It is sent four ways: free text, `json.dumps`, `yaml.safe_dump` (the AgentDojo default), and an OpenAI content-parts list.
- **`multi_turn`:** two user turns, an earlier completed call, an assistant text turn, then one assistant message with text and two parallel calls, and two results.

Variants on `single_call`: arguments sent as a JSON string (the OpenAI wire format, unconverted), no system message, and no `tools` argument.

## Results: Hugging Face templates

Counts are over the 18 templates. Model names stand for their template.

| Property | Result |
| --- | --- |
| Tool definitions in the prompt | 15 yes. Not rendered, silently: Phi-4-mini, Phi-3-mini. Error: Gemma 3. |
| Completed call, with its function name | 12 yes. Dropped silently: Granite 3.3, Phi-4-mini, Phi-3-mini, GLM-4-32B. Kimi K2 renders the arguments and call id but no function name. Error: Gemma 3. |
| Tool result in the prompt | 15 yes. Dropped silently: Phi-3-mini, GLM-4-32B. Error: Gemma 3. |
| Turn that carries the result | User turn: Qwen3, Qwen3-235B-2507, Qwen2.5, Granite 4.0, Nemotron 3. Dedicated role: Hermes 3, Granite 3.3, Phi-4-mini (`tool`); Llama 3.1, 3.2, 4 (`ipython`); GLM-4.5 (`observation`). Other: gpt-oss (a message authored by the function), Kimi K2 (a system-family token named after the tool), Gemma 4 (inside the model's own turn). |
| Tool output passed as a string | Verbatim in 11. JSON-encoded by the template (quoted, newlines escaped) in 4: gpt-oss, Llama 3.1, Llama 3.2, Llama 4. |
| Two parallel calls with two results | All calls rendered in 9. Llama 3.1 and 3.2 refuse with an error. gpt-oss renders only the first call and attributes both results to the first tool. The templates that drop single calls drop these too. |
| Tool output passed as a content-parts list | Flattened correctly in 3. Printed as a Python list in 8. Tool result silently empty in Qwen3 (both templates). Error in 3. |
| Arguments passed as a JSON string | Handled in 5. Double-encoded in 5 (Qwen2.5, gpt-oss, Llama 3.1, 3.2, 4). Error in 4. |
| Today's date inserted | 4: Granite 3.3, gpt-oss, Llama 3.2, Llama 4. The prompt changes with the day the study runs. |
| Control-token strings inside tool output | In all 12 templates whose own delimiters were in the fixture, the tokenizer maps them to the real control tokens. |

Two of these confirm defects the audit found in Study B, now at a pinned template revision: Phi-4-mini's template renders neither tool definitions nor calls, and Granite 3.3's drops calls.

## Results: does this match a real server?

For the eight Study B models whose rows stored the prompt vLLM returned, all 144 stored prompts (18 per model, 3 per condition) are byte-identical to the transformers rendering of the same conversation at the pinned revision. This holds once tool-call arguments are parsed into objects, which vLLM does before rendering: with arguments left as the JSON string the client sent, only 6 of 18 Qwen2.5 prompts match.

So for these eight models, on vLLM 0.33.0, for conversations with one completed call and string content, the tokenizer-level rendering is the prompt the server used. That is not shown for the census fixtures, for other models, or for other servers. The two gpt-oss models stored no prompt, because vLLM renders them through Harmony and returns none.

## Results: Ollama library templates

Rendered by Ollama's template package, not by a server.

| Property | Result (11 library tags) |
| --- | --- |
| Tool definitions after a tool result | Rendered in 6. Not in `llama3.1`, `llama3.2`, `mistral-small3.2`: these render definitions only while the user's message is last, so once a result is in the history the definitions are gone. `gemma3` and `deepseek-r1` have no tool support. |
| Completed call | Rendered in 9. |
| Calls in an assistant message that also has text | Dropped in `qwen3`, `qwen2.5`, `hermes3`, `granite3.3`, `mistral-small3.2`. |
| Caller's system message | Dropped by `hermes3` whenever tools are passed; the template substitutes its own. |
| Tool result | Verbatim in 9. Dropped silently by `gemma3` and `deepseek-r1`. |
| Argument order | Keys are sorted alphabetically in every template, because arguments pass through a Go map. |

The server's `chatPrompt` also drops messages from the front of the conversation when the prompt exceeds the context window. That was read in the source, not run.

## The same family on two stacks

| Family | Hugging Face template | Ollama library template |
| --- | --- | --- |
| Hermes 3 | Result in a `tool` turn; system message kept | Result in a `user` turn; system message dropped when tools are passed |
| Granite 3.3 | Completed call dropped; result in a `tool` turn | Completed call rendered; result in a `tool_response` turn |
| Phi-4-mini | No tool definitions, no call | Both rendered |
| gpt-oss | Tool output JSON-encoded; only the first of two parallel calls | Tool output verbatim; both calls |
| Llama 3.1 and 3.2 | Tool output JSON-encoded; definitions kept; parallel calls refused | Tool output verbatim; definitions gone after a tool result; parallel calls rendered |
| Qwen3 and Qwen2.5 | Calls kept when the message also has text | Calls dropped when the message also has text |

For Hermes 3 the role token on the tool result differs between the two. Any claim about "the tool role" on that model is a claim about one of them.

## Defaults, alternatives, mistakes, unsupported

- **Supported default.** The template shipped in the repository, with the parser the serving documentation names. vLLM's 0.33.0 tool-calling page documents this for Qwen2.5, Hermes and Granite 4.0. On those and on Qwen3 it renders definitions, calls and results.
- **Documented alternative.** vLLM's 0.33.0 tool-calling page recommends a replacement template for Llama 3.x, Llama 4, Mistral, Granite 3.0 and DeepSeek. The census read the repository templates, not those.
- **Configuration mistake.** Serving Phi-4-mini for tool use with its repository template, as Study B did. vLLM has a parser for it, but its tool-calling page does not mention the model and the repository template has no tool support. Passing arguments as a JSON string or content as a parts list straight to a template is the same kind of mistake; a server normally converts both first.
- **Unsupported.** Granite 3.3 with vLLM's `granite` parser: the documentation covers 3.0 and 3.1 only, and the 3.3 template drops calls. Gemma 3, whose template rejects tool messages. GLM-4-32B with standard messages: its template drops both the call and the result.

Study B's Phi-4-mini run was a configuration mistake and its Granite 3.3 run was an unsupported combination. Neither was detected, because nothing failed.

## What it established

1. In the models that this literature uses, silent loss of tool definitions, calls or results is common enough that it cannot be assumed away: 5 of 18 templates lose at least one of the three in the simplest conversation without an error, and a sixth refuses the conversation.
2. "Tool role" names at least five different prompt-level constructions. On every Qwen template a tool result is text in a user turn.
3. "Raw" and "JSON" tool output are not properties a harness controls. On Llama and gpt-oss templates a string is JSON-encoded by the template, so a harness that sends JSON gets it encoded twice.
4. Template and stack disagree for the same family, including on the role token.
5. For eight models, vLLM 0.33.0's prompt equals the transformers rendering.

## What it could not establish

- **Any effect on behavior.** The census shows what the model is given. It does not show that any of these differences changes attack success. That needs inference.
- **How common these issues are in general.** The sample is purposive.
- **What a running Ollama or llama.cpp server sends.** The Ollama results are code-level. llama.cpp was not run and often ships a different template inside the GGUF file.
- **What vLLM sends gpt-oss.** The Harmony path returns no prompt. Whether it JSON-encodes tool output, as the repository template does, is unknown. This is the first thing to check on a server.
- **Mistral Small 3.2 and DeepSeek-V3.2**, which need their own tokenizer libraries.
- **Whether the official gated templates equal their mirrors.**
- **Closed models.**
- Two Ollama findings (the Hermes 3 template printing tool schemas as a Go structure, and its dropped system message) follow from the template source and Ollama's rendering code, but were not confirmed against a running server.

## Reproduce

```bash
pip install transformers pyyaml                         # not project dependencies; Go is needed for the Ollama stage
python scripts/rendering_census.py transformers     # downloads tokenizer files only
python scripts/rendering_census.py vllm-replay
(cd scripts/ollama_render && go build -o /tmp/ollama_render .)
python scripts/rendering_census.py ollama --renderer /tmp/ollama_render
python scripts/rendering_census.py summary
```

Results are in `results-published/rendering-census-2026-11-15/`: one JSON line per configuration, fixture and variant; the rendered text of every prompt; token IDs; a summary table; and the software versions. A test pins the headline counts.
