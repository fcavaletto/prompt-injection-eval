# Measurement contract: what "delivered as intended" means

**Written 2026-11-17, before the delivery checkers were changed.** The expected verdicts in section 3 were committed with the corpus and with the results of the unchanged checkers. Only then were the checkers adapted. The commit history shows that order.

This page defines the property the pilot's delivery check is meant to establish, lists the deliberate mutations used to test it, and states each mutation's expected verdict. It is deliberately small: one pilot history in two formats and under two pinned templates, plus the WP7 fixture. **It does not extend WP7 to further harnesses.**

## 1. Scope

**The property.** A request is *delivered as intended* when the prompt the server returns contains the conversation the harness sent, in the turn structure the *pinned* chat template prescribes. That means: every offered tool's schema, every message's content in a turn of the right role, every call with its exact name and typed arguments, every tool result verbatim and attached to the right call, the payload in the carrier result in the form the format prescribes, nothing truncated, and nothing duplicated.

**Not the property.** Whether the model *understands* the conversation as intended, whether two serializations carry the *same information to a reader*, and whether a payload is *recognizable* as data. Free text is structurally ambiguous to a reader (section 4). A delivery check cannot certify semantic fidelity, and none of this page claims it.

**Template profiles.** The expected role mapping is read from each pinned template, not chosen by the checker:

| Profile | Template (pinned) | Turn | Tool schemas | Calls | Tool results | Generation header |
| --- | --- | --- | --- | --- | --- | --- |
| `qwen3` | `Qwen/Qwen3-32B@9216db5`, `enable_thinking=False` | `<\|im_start\|>{role}\n…<\|im_end\|>\n` | in the system turn, one JSON object per line inside `<tools>` | in the assistant turn, `<tool_call>\n{json}\n</tool_call>` | in a **user** turn, `<tool_response>\n…\n</tool_response>`; consecutive tool messages share one user turn | `<\|im_start\|>assistant\n<think>\n\n</think>\n\n` |
| `granite4` | `ibm-granite/granite-4.0-h-small@b8c0982` | `<\|start_of_role\|>{role}<\|end_of_role\|>…<\|end_of_text\|>\n` | same | same | in a **user** turn, as for `qwen3`, with a leading newline | `<\|start_of_role\|>assistant<\|end_of_role\|>` |
| `scripted` | the offline stand-in in `pilot/scripted.py` | as `qwen3` | same | same | in a user turn, **one turn per tool message** | `<\|im_start\|>assistant\n` |

**A legitimate template that renders tool results inside a user turn is not a defect.** Both pinned templates do so. A checker that required a `tool` role would reject every valid pilot request.

## 2. Contract items

| Item | Requirement | Strictness |
| --- | --- | --- |
| K1 Turn structure | The prompt is a sequence of the profile's turns with nothing outside them, ending with the generation header. The role sequence equals the one the profile derives from the messages, with tool messages grouped as the profile groups them. | exact |
| K2 Tool schemas | Each offered tool's schema appears in the system turn **exactly once**, as a JSON object that decodes equal to the one sent, with **strict scalar types** (`true` ≠ `1` ≠ `1.0`). No other schema-shaped object appears. | decoded, type-strict; key order and whitespace free |
| K3 System and user text | The system turn starts with the system message; each user turn's body is the user message. | verbatim (outer whitespace trimmed) |
| K4 Calls | Each assistant turn holds exactly the calls sent, in order, each with the exact name and type-strict arguments. No call is dropped, added or duplicated. | decoded, type-strict |
| K5 Results | Each tool message is one wrapped block, in order, in the expected turn. Its content is verbatim. In JSON, it decodes to the canonical record, type-strict. | verbatim; JSON decoded type-strict |
| K6 Association | Within a tool turn, block *k* follows call *k* of the preceding assistant turn. The number of blocks equals the number of calls. (These templates associate by position; there is no call id in the prompt.) | positional |
| K7 Payload | The payload is in the carrier record, and inside the carrier's block, in the prescribed form: verbatim lines in text, JSON-escaped in JSON. | within the carrier block |
| K8 Completeness | Nothing is cut: every item above holds and the generation header is present. | exact |

Tool schemas and call objects are serialized *by the template*, so a different key order or whitespace is a legitimate encoding and must be accepted. Tool results are serialized *by the harness*, and the intervention is their exact text, so a result must be verbatim. A re-escaped or re-indented result is a different intervention and is rejected.

## 3. Corpus and expected verdicts

**Base histories** (`tests/fixtures/checker_corpus/base_cases.json`, built by `scripts/build_checker_corpus.py`):

- **The source request.** One stored pilot request: Granite, banking, JSON, `text_fake_turn`, `user_task_12|injection_task_6`, the request for model turn 1. Its history is: system message, user message, one replayed call, the carrier result with the payload, one model turn with three parallel `send_money` calls (an integer `amount`), and three identical results.
- **The text format.** The same history with every tool record re-serialized as text.
- **Rendering.** Each history is rendered with both pinned templates, giving four base cases. A fifth valid case is the `scripted` rendering of one of them.
- **Generated variants.** Mutations are generated from these at test time (`src/prompt_injection_eval/pilot/checker_corpus.py`).

Expected verdict: **accept** (the request was delivered as intended) or **reject** (it was not). Expected verdicts are fixed per class before any checker was run on the corpus.

| Class | Mutation | Expected |
| --- | --- | --- |
| **valid** | V1 base rendering, each profile and format | accept |
| | V2 tool schemas re-serialized with other key order and indentation | accept |
| | V3 call arguments re-serialized with other key order | accept |
| | V4 the `scripted` rendering (one user turn per tool message) under the `scripted` profile | accept |
| | V5 the same history with the three parallel calls given distinct amounts (10000, 9000, 8000), substituted consistently in messages, records and rendering; and with the first amount set to 1 (the base for A5) | accept |
| **role** | R1 tool results moved from the user turn into a `tool`-role turn | reject |
| | R2 tool results appended inside the preceding assistant turn | reject |
| | R3 the user message rendered as a system turn | reject |
| | R4 the system text moved into the first user turn | reject |
| | R5 the end-of-turn delimiter between the user and assistant turns removed (turns merged) | reject |
| | R6 the grouped tool turn split into one turn per result under a grouping profile | reject |
| **schema** | S1 one tool schema removed | reject |
| | S2 one parameter renamed | reject |
| | S3 one parameter's declared type changed | reject |
| | S4 one tool description altered | reject |
| **arguments** | A1 an argument value changed | reject |
| | A2 an argument key renamed | reject |
| | A3 an integer argument rendered as a string (`10000` → `"10000"`) | reject |
| | A4 an integer argument rendered as a float (`10000` → `10000.0`) | reject |
| | A5 an integer argument rendered as a boolean, in a history where it is `1` (`1` → `true`) | reject |
| **duplicates** | D1 one tool schema listed twice | reject |
| | D2 one call rendered twice | reject |
| | D3 one tool result rendered twice | reject |
| **order** | O1 two parallel calls swapped | reject |
| | O2 the replayed call's result moved after the model's turn | reject |
| | O3 user turn moved after the first tool result | reject |
| **association** | X1 one block dropped from a three-result tool turn and another duplicated (count preserved, association broken) | reject |
| | X2 the carrier result moved into the later tool turn (counts per turn change) | reject |
| **truncation** | T1 prompt cut inside the last tool result | reject |
| | T2 generation header removed | reject |
| | T3 prompt cut inside the payload | reject |
| | T4 the start of the system turn cut (left truncation) | reject |
| **payload** | P1 one payload character changed | reject |
| | P2 payload line breaks collapsed (text) / escapes removed (JSON) | reject |
| | P3 carrier result re-encoded as a JSON string literal | reject |
| | P4 carrier result in JSON re-serialized with ASCII escapes or indentation (decodes equal, not verbatim) | reject |
| **WP7** (fixture prompt, `wp7.check`) | W0 the valid encodings already in `tests/test_wp7.py` | accept |
| | W1 a parameter renamed (`channel` → `chan`) | reject |
| | W2 a parameter's declared type changed (`string` → `integer`) | reject |
| | W3 the call's argument key renamed | reject |
| | W4 the call's argument value given another scalar type (string → list) | reject |

**Reading the counts.** For each checker and class: *detections* are rejects of mutations expected to be rejected; *false alarms* are rejects of variants expected to be accepted. Results are in [results-published/checker-validation-2026-11-17](https://github.com/fcavaletto/prompt-injection-eval/tree/main/results-published/checker-validation-2026-11-17).

## 4. Free text is structurally ambiguous

`serialize.to_text` writes strings raw. A multi-line string becomes an indented block, so a string whose lines look like labels renders exactly like a nested object or list:

```text
to_text({"a": "b: 1\nc: 2"})  ==  to_text({"a": {"b": 1, "c": 2}})  ==  "a:\n  b: 1\n  c: 2"
to_text({"a": "- x\n- y"})    ==  to_text({"a": ["x", "y"]})
to_text({"a": "(empty)"})     ==  to_text({"a": {}})
to_text({"a": "5"})           ==  to_text({"a": 5})
```

`serialize.from_text` recovers the record only because it is *given the record's shape*. So "the free text drops type marks and nothing else" (pilot design, section 1) is wrong: without the shape it can also drop the boundary between a string and structure. That is a property of the representation, not a delivery defect. The delivery check compares the exact text and is unaffected. But it matters for interpretation: a forged-data payload can make part of a string look like sibling or nested fields to a reader, and JSON's quoting prevents that. The Stage 1 protocol's third representation (labelled text with JSON-quoted string values) exists to separate this from the other differences between the formats.

## 5. Coverage claimed after validation

The mutation results (122 of 122 constructed defects detected, 0 of 24 valid variants rejected) are **evidence that the checker detects the fault classes tested**: these classes, these histories, these templates. They do not show that the checker is complete. A fault outside these classes, or a different instance of one of them, may go undetected. Nothing more is claimed. In particular, not:

- not other templates;
- not other harnesses;
- not attacks that write chat-control tokens into a payload;
- not hosted renderers;
- not semantic equivalence.

## 6. Populations: which checker covers what, and what rests on reconstruction

Added 2026-11-17. "Turns" are model requests in the pilot's new phases: Qwen's selection, Slack controls and evaluation, and all four of Granite's phases.

| Population | Count | Checker that covers it | Kind of evidence |
| --- | ---: | --- | --- |
| Turns recorded in scored (final) traces | 21,321 | the archived `delivery.check` at run time; SHA-256 of the server's prompt against a local rendering rebuilt from the stored conversation (`verify_pilot_prompts.py`) | the run-time check saw the real prompt. The hash comparison is a **reconstruction**: it needs the stored history and the pinned template |
| Turns recorded in superseded `infra_error` traces, history sufficient | 6 | the same | reconstruction; these episodes were never scored |
| Turns recorded in superseded traces, history insufficient | 11 | the archived `delivery.check` at run time only | not reconstructible: the stored conversation ends at the abort |
| Aborted requests | 6 | none | no prompt was returned, and none is recorded as a turn |
| **Published "21,327 match by hash"** | 21,321 + 6 | | reconstruction, all of it |
| Full server prompts retained | 787: 580 pilot, 145 F1, 62 smoke; all from scored traces | `check_contract` on the retained text itself (`kept_prompts_contract.json`). The 404 text-format prompts were checked without the record items | **retained prompt evidence** |
| Mutation corpus | 146 constructed cases from 1 retained request | both checkers | synthetic: evidence about fault classes, not about the pilot's requests |

**Which conclusions rest on which evidence:**

- **"Every scored turn was delivered as the pinned template renders the stored conversation."** This rests on reconstruction plus hash equality, for all 21,321 turns. The server's prompt text was kept for only 580 of them.
- **"The retained prompts meet the contract: roles, multiplicity, strict types, generation header."** This rests on the retained text, for 787 prompts.
- **"Every scored turn meets the contract."** This is an **inference**, not an observation. It combines two things: hash equality with the local rendering, and the fact that the pinned templates render conversations in contract-conforming layouts. That fact was checked on the corpus base renderings and the 787 retained prompts, not on every turn. The archived run-time check did not test roles or multiplicity (C19), so it cannot supply the missing part.
- **No conclusion rests on the 11 unreconstructible turns or the 6 aborted requests.** None of those belongs to a scored episode.
