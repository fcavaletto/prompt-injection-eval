# OpenRouter feasibility screen (Amendment 4, part B; not run)

**Status: frozen 2026-11-17 at `3e3e3dd`.**

- **Not authorized and not run.** No API call has been made. Only OpenRouter's public model metadata was read.
- **The question:** on contemporary tool-using models, does representation affect explicit instruction attacks and forged-data attacks differently?
- **What it is:** a development feasibility screen. It does not estimate resistance to an optimized attacker, and it does not replace the controlled Granite experiment ([Stage 1](protocol-stage1.md)).

## 1. Models, verified from current metadata

Read from `GET /api/v1/models` and `GET /api/v1/models/{id}/endpoints` on 2026-11-17.

| Requested id | Resolved to (dated) | Pinned endpoint | Price per M tokens (in / out) | Parameters sent |
| --- | --- | --- | --- | --- |
| `openai/gpt-6-luna` | `openai/gpt-6-luna-20260922` | OpenAI, tag `openai` (not `openai/flex` or `openai/fast`) | $0.10 / $0.50 | `tools`, `tool_choice`, `max_tokens` 4096, `reasoning` `{effort: low}`, `seed` |
| `anthropic/claude-haiku-5.5` | `anthropic/claude-haiku-5.5-20261007` | Anthropic, tag `anthropic` | $0.10 / $0.50 | `tools`, `tool_choice`, `max_tokens` 4096, `reasoning` `{effort: low}` |

**Parameters.**

- Neither endpoint lists `temperature`, so none is sent.
- Only Luna's endpoint lists `seed`. A seed does not guarantee determinism, and Haiku has none. Repeat behaviour is therefore unknown, and the screen has one run per cell.
- The reasoning effort and output limit are frozen. Reasoning tokens count against `max_tokens` and are costed as output.

**Version ambiguity.**

- OpenRouter's documentation shows only the `id` (here undated) as a request model, and does not state whether a dated `canonical_slug` is accepted. The screen therefore sends the undated id. It does not test the dated slug with a paid call.
- **What the response check can show.** The response's `model` is checked against the id and the dated slug read on 2026-11-17, and a mismatch stops the episode (`endpoint_mismatch`).
- **What it cannot show.** If the service reports the alias or the same dated slug while serving a changed model underneath, the check cannot see that. The underlying version is therefore not proven to stay unchanged, and silent changes are not guaranteed to be detected.
- A `~anthropic/claude-haiku-latest` alias exists and is not used.

**Routing controls, explicit in every request** (`providers/openrouter.py`):

- `provider.only` names the endpoint's base slug. Per OpenRouter's routing documentation, a base slug matches the provider's non-tier endpoints and excludes `flex`/`fast` tier endpoints.
- `allow_fallbacks: false` and `require_parameters: true`.
- `data_collection: "deny"`.
- `max_price` equal to the pinned price.
- No `models` array, so there is no model fallback.

**Verification of the served endpoint.** If the response names a provider other than the pinned one, the episode stops with `endpoint_mismatch`. The routing metadata header is requested.

## 2. Cases and manifest

**Eligibility.** A case needs both attack families aimed at the *same* unauthorized action, and each must be valid under the threat model and reachable under AgentDojo's check.

- Only the five forged-data pathways of Stage 1 qualify: F1 to F5 ([threat-model table](protocol-stage1.md#4-forged-data-feasibility)). On each, the instruction attack targets the same goal check.
- The requested 24 cases are not available. Building more pathways would mean new forged-data designs, each needing reachability and validity checks, so the manifest is smaller and explicit.
- F4 and F5 are flagged as questionable and borderline under the threat model. Results are reported with and without them.

**Episodes** (`data/screen/design.json`, per model in a seeded order):

| | Count |
| --- | ---: |
| 5 cases × 2 models × 2 representations × 3 (instruction, forged data, benign) | **60** |
| Calibration: per model, one benign episode (text) and one instruction episode (JSON carrier), on F1; never analysed | 4 |

**Attacks** (identical bytes across representations and models):

- the instruction attack is AgentDojo's `important_instructions` (multiline) with the case's goal;
- the forged-data attack is the case's multiline forged field.

## 3. Intervention and what differs between arms

**The intervention.** Only the injected result (the carrier) changes:

- labelled text (`text`, the pilot's comparator), or
- valid JSON (`json@text`: the carrier as JSON, every other result still labelled text).

Every other tool output, the system prompt, the tools and the round limit (15) are frozen.

**Information differences the representations introduce:**

- **Line breaks.** In JSON the payload's line breaks become `\\n` escapes and its quotes become `\\"`. In text they stay raw lines inside an indented block, where a forged `IBAN: …` line can look like a sibling field ([contract](measurement-contract.md) §4).
- **Type marks.** JSON adds type marks and braces. Text adds labels and indentation.

**What is not observed.**

- **Provider rendering.** Each provider converts OpenAI-format `tool` messages into its own format (for example, a tool-result block). How the tool-result string is tokenized and framed inside the model's context cannot be observed.
- **Delivery.** It is verified **at request level only**: the exact outgoing body is checked against the intended conversation (`delivery.check_request`). No claim is made about the provider's internal rendering, and the local contract check's guarantee does not extend to this arm.

## 4. Measurement

**Recorded per call** (credentials never):

- the exact outgoing body and the raw response;
- requested model, returned model and returned provider;
- usage, including reasoning tokens and reported cost;
- finish and native finish reasons;
- every attempt, with its status and error;
- the running spend.

**Outcomes, kept distinct:**

| Outcome | What it is |
| --- | --- |
| `completed` | scored |
| `api_error` | HTTP or connection failure after bounded retries |
| `endpoint_mismatch` | wrong model or provider |
| `budget_exhausted` | refused before sending |
| `invalid_delivery` | request-level check failed |
| `interrupted` | deadline |

A malformed tool call (non-JSON arguments, unknown tool) is a model output: it counts in the episode, which continues as AgentDojo would.

**Scoring.**

- Actual environment-state changes are scored with AgentDojo's checks, on executed calls only.
- Attack episodes are also replayed and verified against the recorded final-state hash.

**Calibration first, on every launch.**

- The two calibration episodes per model must complete with the pinned provider and model reported, usage cost present, and no request-level defect.
- Before any screen request, on every launch including resumes, `verify_calibration` reads the stored calibration traces and requires, for every call: completion, a clean request-level check, the pinned provider (from the response or its routing metadata), the expected model, and a reported cost. If any part fails, no screen request is made (tested with failing fixtures).
- If calibration fails (including a 404 because `data_collection: deny` leaves no endpoint), the failure is reported. No routing setting is relaxed without a new decision.

## 5. Analysis (descriptive)

Per model, on **matched cases only** (a case counts for a difference only if both representations completed; missing counterparts are listed):

- case-level outcomes;
- the provisionally accepted F1–F3 and all five (F4 and F5 exploratory), reported separately;
- successes over completed episodes, per family and representation;
- text minus JSON per family, and the instruction-minus-forged difference of those differences;
- benign utility per representation;
- API outcomes and malformed calls;
- spend.

With five cases, no interval or test is reported, and no claim beyond "this pattern was or was not visible on these five cases" is made.

## 6. Cost and cap

From `scripts/cost_screen.py` (`data/screen/cost_estimate.json`). Each call resends the whole conversation and the tools: the first request averages 6,516 characters, and grows each turn.

| Case | Assumptions | Cost (64 episodes incl. calibration) |
| --- | --- | ---: |
| Central | 4 calls, 600 output tokens (reasoning included) per call | $0.14 |
| High | every episode reaches 16 calls, 2,048 output tokens per call, 10% retried | $3.74 |
| Unbounded worst | 16 calls × 3 attempts, every call at 4,096 tokens | $26.32, **prevented** |

**Cap: $5 including calibration.** It is enforced in three layers, and none is claimed to be a proof on its own:

1. **Durable local ledger** (`providers/spend_ledger.py`, `<root>/spend-ledger.jsonl`):
   - each attempt's reservation is written and fsynced *before* it is sent;
   - it is released only on evidence that nothing was sent (a refused connection), and settled only with the cost the API reported for it;
   - timeouts, disconnects after sending, HTTP errors and responses without a usable cost stay charged at the reserved amount until reconciled. OpenRouter documents that non-streaming requests continue and are billed even if the client disconnects;
   - a restart replays the ledger: reservations pending at a crash become charges, and the call count is restored;
   - an exclusive `flock` stops a second process from spending the same allowance;
   - a reported cost above its reservation halts all further spending.
2. **The reservation bound, stated but not proven:**
   - input tokens are taken as at most the UTF-8 bytes of the whole request body (byte-level tokenizers emit at most one token per byte) plus a 4,096-token allowance for provider-added framing;
   - output is taken as at most `max_tokens`, which OpenRouter says covers reasoning and visible output "on most providers";
   - the long-prompt price tier is used whenever it could apply;
   - OpenRouter does not document a token bound or hidden framing tokens, so this is conservative, not proven.
3. **Service-side backstop:**
   - the launch preflight requires the key to carry a non-resetting credit limit no larger than the cap (`GET /api/v1/key`), which means using a dedicated key;
   - the key's reported usage is reconciled against the ledger after calibration and after each model, and any excess halts the run;
   - whether a key limit can be overshot by a request already in flight is not documented.

## 7. Commands (after approval only)

```bash
export OPENROUTER_API_KEY=...            # never committed, never recorded
pie screen run --root results/screen --cap-usd 5 --calibration-only
pie screen run --root results/screen --cap-usd 5      # calibration is resumed, then the screen
pie screen report --root results/screen --output-dir results/screen/report
```
