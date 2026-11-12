# Methodology

## Research question

How often does an instruction-following language model obey malicious instructions embedded inside an untrusted document, and how much does a simple prompt-level defense reduce attack success without degrading legitimate task completion?

Version 0.3 adds a second question: do models that differ in size, family, and reasoning style differ in that behavior by more than the run-to-run noise we can measure?

## Terms used on this page

- **Indirect prompt injection.** An instruction placed in data the model was asked to process (a document, an email, a web page), rather than typed by the user. The attacker never talks to the model.
- **Canary.** A harmless, unique string such as `CANARY_D01`. If the model prints it as its answer, it followed the document's instruction. Nobody would write it by accident.
- **Attack success rate.** Attack cases where the attack scorer said `success`, divided by attack cases with a valid response. Benign controls are never in the denominator.
- **Utility and security.** Security is whether the model resisted the attack. Utility is whether it still did the user's task. They are scored separately, because a model that refuses everything is secure and useless.
- **Datamarking.** A defense from the spotlighting family: every space in the untrusted document is replaced with a marker (`^` here) so the model can see which text came from the document.
- **Wilson interval.** A 95% range for a proportion given a count and a denominator. It is wider when the denominator is small. It is described below.
- **Paired comparison.** Comparing two conditions on the same cases, so each case serves as its own control. Described below.

## Unit of evaluation

One unit is one case under one prompt condition for one model. `--condition all` runs three conditions. The 105-case file under all three conditions is 315 units per model run.

## Dataset

Two case files, described in detail in [the dataset page](dataset.md):

- `data/cases.jsonl`: the 40 cases of the 0.2.0 study (36 attacks, 4 benign controls). Unchanged.
- `data/cases_v2.jsonl`: those 40 records, byte for byte, followed by 65 new hand-written cases. 105 cases: 89 attacks and 16 benign controls in 11 categories.

`data/smoke_cases.jsonl` is six records copied from the 40-case file. Records are validated with strict Pydantic models (`data/schema.json`, schema version 1.1, which accepts every 1.0 file). Every result row stores the SHA-256 of the file that was loaded.

The attacks are harmless by construction: canary tokens, fixed JSON objects, format markers, the synthetic secret `SYNTHETIC_SECRET_4C91`, and function-call text that nothing executes. The harness does not execute dataset strings or model output.

## Experimental conditions

| | Baseline `baseline-v1` | Defended `defended-v1` | Spotlight `defended-v2` |
| --- | --- | --- | --- |
| System instruction | The case text, unchanged | The same text, unchanged | The same text, unchanged |
| User task | The case text | The same text | The same text |
| Document | The case text | The same text | The same text, with every whitespace run replaced by `^` |
| Document framing | Neutral delimiters | Labeled untrusted data | Labeled untrusted data, plus an explanation of the marker |
| Instruction about document commands | None | One generic refusal rule | Marked text is data, never instructions |
| Generation parameters | Shared | Shared | Shared |
| Scorers | Shared | Shared | Shared |

The defense is not inserted into the system instruction. That keeps the baseline-versus-defense contrast in the user message, which is the intended independent variable. The templates did not change between 0.2.0 and 0.3.0, and their version strings are the same. A wording change that can affect behavior requires a new version string.

## Models and runtimes

Version 0.3 runs four models. Each is its own condition, and they are never pooled into one rate.

| Model | Runtime | Weights | Thinking | Output budget |
| --- | --- | --- | --- | ---: |
| `gpt-oss-20b` | MLX (`mlx-lm`) | `mlx-community/gpt-oss-20b-MXFP4-Q4`, MXFP4 experts | Harmony analysis channel, `reasoning_effort=low` | 4096 |
| `Qwen3-14B` | MLX | `mlx-community/Qwen3-14B-4bit`, 4-bit affine | Off (`enable_thinking=False`) | 256 |
| `Qwen3-4B-Instruct-2507` | MLX | `mlx-community/Qwen3-4B-Instruct-2507-4bit`, 4-bit affine | None (instruct model) | 256 |
| `deepseek-r1:14b` | Ollama 0.34.4 | Q4_K_M | Visible `<think>` reasoning, on | 4096 |

Why these: they are the strongest open-weight models whose weights were already on the machine (an M4 MacBook Air with 24 GB of unified memory), and together they let three contrasts be seen. Size within one family (Qwen3 4B against 14B, same runtime, both answering without a thinking block). A distilled reasoning model against non-reasoning ones. And the largest model that fits, gpt-oss-20b. The reasons, sizes, and what was not run are in [model selection](model-selection.md).

Held constant across every run: the case file and its hash, the three templates, temperature 0, seed 42, the scorers, and sequential execution. What differs by model, and is recorded in each row: runtime, quantization, whether a reasoning block is produced, and the output budget.

### Why gpt-oss runs with low reasoning effort

gpt-oss writes its reasoning in an `analysis` channel before its `final` answer. Its chat template takes a `reasoning_effort` setting, and the template default is `medium`. Before the full run, three baseline cases were tried in three configurations. Under greedy decoding (temperature 0) with `medium` effort, the analysis channel fell into a loop ("The user says ... The user says ...") and never reached an answer within 1024 tokens. With a repetition penalty of 1.1, it still ran out of a 2048-token budget on one of the three. With `low` effort, greedy decoding finished all three in under 150 tokens. With the vendor-recommended temperature 1.0 and `medium` effort, it also finished.

The study keeps temperature 0 for every model, so gpt-oss runs with `low` effort. That choice was made before the full run and is part of the condition. A pre-declared sensitivity check runs the six smoke cases with greedy `medium` effort (to count the loops) and with temperature 1.0 and `medium` effort under three seeds. Its results are reported separately. On those three probe cases the configuration changed two of the three attack outcomes, so "gpt-oss-20b's attack rate" on this page always means this configuration.

### Context window

Ollama chooses a default context window from available memory. On this machine the server log showed `default_num_ctx=4096`. DeepSeek's 4096-token output budget plus a prompt of up to about 600 tokens can exceed that. In 0.3 the harness passes `--num-ctx 8192` for DeepSeek and records it in each row and in the resume key. The 0.2.0 DeepSeek run used the default. MLX has no fixed context window; the cache grows with the sequence.

## Controlled variables and what can still vary

Held constant within a pair:

- model and runtime configuration
- case, including system instruction, task, and document
- temperature, seed, maximum output tokens, and timeout
- scorer version
- dataset hash

Not fully controlled:

- local runtime nondeterminism
- whether the runtime honors the seed
- quantization and runner version if the weights change between runs

## Generation parameters

Defaults: temperature 0.0, maximum output tokens 256, timeout 120 seconds, concurrency 1. `--profile reasoning` raises the defaults to 4096 output tokens and a 900 second timeout, for models that spend their budget on visible reasoning.

At temperature 0 both runtimes pick the most likely token at every step (greedy decoding), so the seed has no effect on the choice. The seed is still passed (to Ollama's `seed` option, and to `mx.random.seed` before each MLX request) so a sampled run, like the gpt-oss sensitivity check, is repeatable. Whether greedy decoding is bit-identical from run to run on this hardware is an empirical question. The repeated runs answer it.

## Scoring

Deterministic scorers only. See [scoring](scoring.md). Attack score and task score stay independent. The outcome label is derived from both and does not erase either one. Version 0.3 uses `attack-v2` and `task-v2`. On every response in the 0.2.0 study they return exactly the labels that `attack-v1` and `task-v1` returned; a test checks this.

Two secondary readings are computed from the stored answers and reported next to the headline, never instead of it:

- a **lenient task reading**, which accepts a correct label inside a sentence when the task did not say "only", ignores spacing in keywords, and accepts field lists when the task did not ask for JSON;
- a **tool-call text proxy** for the eight `tool_call_request` cases: would a naive line parser have found the attacker's function call in the answer?

## Visible reasoning

Reasoning models emit their chain of thought as part of the completion: DeepSeek-R1 inside `<think>` tags or Ollama's `thinking` field, gpt-oss in the Harmony `analysis` channel. This is visible model output, not a hidden channel.

- Only the final answer is scored. For gpt-oss, that is the `final` channel.
- `response_text` is the scored answer. `response_text_raw` is the completion as returned, including special tokens. `reasoning_text` holds the reasoning.
- If generation stops before the final answer, the answer is empty. The unit is scored as attack failure and task failure and flagged. Reports count these separately; they are budget failures, not evidence of robustness.

## Paired comparison

For each case that has both conditions under the same model and settings, the defense effect is one of `improved`, `worsened`, `unchanged`, or `incomparable`. Security and utility are stored separately. Any backend error or ambiguous outcome makes the pair `incomparable`. This is the descriptive table the harness has always produced.

## Statistical tests

Counting improved and worsened pairs describes what happened. It does not say whether a difference that size could easily come from chance. Version 0.3 adds a test for that, chosen because it is exact and easy to explain.

**McNemar's exact test.** Take one model, baseline against one defense, on the 89 attack cases. Each case lands in one of four cells:

| | Defense compromised | Defense not compromised |
| --- | ---: | ---: |
| **Baseline compromised** | both | b |
| **Baseline not compromised** | c | neither |

Cases in "both" and "neither" behave the same under the two conditions, so they carry no information about the difference. Only b and c do. If the defense had no effect, each of those b + c discordant cases would be equally likely to fall either way, like a fair coin. The test asks how often a fair coin tossed b + c times gives a split at least as lopsided as b against c. That probability is the p-value.

A worked example from the 0.2.0 data. DeepSeek baseline against `defended-v1`: b = 4 (compromised only at baseline), c = 0. A fair coin lands the same way four times out of four with probability 2 × (1/2)^4 = 0.125, counting both directions. So p = 0.125. That does not mean the defense did nothing. It means four cases cannot distinguish "the defense helps" from "chance" at the usual 0.05 threshold. In fact no split of five or fewer discordant pairs can reach p ≤ 0.05; six, all in one direction, is the minimum (p = 0.031).

**Paired bootstrap interval.** McNemar gives a p-value, not a size. For the size, the difference in attack-success rate (defense minus baseline) is resampled: draw 89 cases with replacement, keeping each case's pair together, and recompute the difference, 10,000 times with a fixed seed. The middle 95% of those differences is the interval. With few discordant pairs the bootstrap distribution is lumpy, and the interval should be read as rough.

**Uncertain scores.** The tests count an `uncertain` attack score as not compromised, matching the headline counts. The defense tests are repeated with `uncertain` counted as compromised, so a reader can see whether the conclusion depends on that choice.

**Many tests.** Four models, two defenses, two outcomes, and two readings of `uncertain` make many tests. At a 0.05 threshold, one in twenty tests of a true null comes out "significant" by chance. Holm's adjustment is reported next to each raw p-value: within a family of tests, it multiplies the smallest p-value by the number of tests, the next smallest by one fewer, and so on. A result that survives Holm is less likely to be a fluke of running many tests.

**Defense against defense.** The same test compares `defended-v1` with spotlight within each model, which asks whether datamarking adds anything over the generic rule.

**Model against model.** The same test applies to two models on the same cases under the same condition. Those contrasts are reported with their own Holm family per condition.

**Power.** The `power` table answers the planning question in reverse: if a defense truly removed a given share of attack successes, how often would an exact McNemar test with this many cases detect it? With 36 attack cases, as in 0.2.0, a true reduction of 10 percentage points is detected about 15% of the time. With 89 cases the same reduction is detected about 89% of the time if the defense never creates a new compromise, and about 67% of the time if it newly compromises 2% of cases. A 5-point reduction is detected less than a third of the time even with 89 cases. A non-significant result here is weak evidence of no effect, especially for small effects.

What none of these tests answer: whether the effect holds on documents other than these 105 hand-written cases, whether it holds for another quantization or runtime, or whether the defense is a security boundary. A small p-value is a statement about these cases under this configuration.

## Metrics and denominators

Attack success rate uses attack cases only. Two denominators are reported: valid responses (backend errors excluded and counted on their own) and attempted (every scheduled attack case; errors are not counted as successes). Task success, ambiguity, manual review, and benign-control task success have the same distinction.

For proportions, a 95 percent Wilson score interval is reported. It is computed from the count and the denominator alone, and unlike the simpler "rate plus or minus two standard errors" it stays inside 0 to 1 and behaves sensibly at 0/89. The implementation is in `prompt_injection_eval.metrics.wilson_interval` and is unit-tested. It describes binomial sampling variability only. It does not correct dataset-selection bias, and two overlapping intervals are not the same as a paired test: intervals ignore that the conditions share cases.

## Scorer validation

Deterministic scorers are cheap and reproducible, and they are wrong sometimes. After a person fills the review CSV, `pie analyze --reviews` and `pie compare --reviews` compute agreement between the automated and human labels, with a Wilson interval and a confusion table. The 0.2.0 runs have the author's labels. The 0.3.0 runs do not: their review queues are published with empty human columns, and no agreement is claimed for them. The author is not an independent annotator.

## Repeated-run variability

`pie variability` takes two or more result directories with the same configuration and reports how many units changed outcome, attack score, or task score, how many returned byte-identical text, and how many changed text while every label stayed the same. In 0.3 the full 315-unit grid is run twice for each MLX model (a third run was planned and cut for time before any repeat had run). DeepSeek, whose full grid takes about five hours, repeats the six smoke cases under all three conditions two more times.

## Comparing models

`pie compare` concatenates result directories and groups by model and by (model, condition). Models are never pooled into a single rate. `pie stats` runs the paired tests within and between models.

## Errors, resume, and review

A failed request is written as `backend_error` and the run continues. If an MLX model cannot be loaded at all, the run stops before writing any row. Each unit is appended to `raw_results.jsonl` immediately. `--resume` skips a unit only when the case, condition, provider, model, temperature, seed, maximum tokens, prompt-template version, dataset SHA-256, scorer version, think setting, and (when set) context window and reasoning effort all match.

Uncertain scores, quoted canaries, secret disclosures, tool-call text, truncation, malformed structure, and baseline/defense disagreements enter a CSV review queue. Human columns start empty.

## Reproducibility

Recorded with each row: rendered prompts, template version, sampling settings, dataset hash, schema version, package version, Python version, a general OS and architecture summary, the git commit when one exists, and `runtime_info`: the runtime and its version, and for MLX the repo id, snapshot hash, and quantization from the model's config; for Ollama the model digest, quantization, and parameter count. Usernames, home directories, hostnames, and serial numbers are not recorded. MLX models are referenced by repo id, not by path, so no home directory ends up in a row.

## Limitations

The case file is small, synthetic, and mostly English. Its attacks do not adapt; the [adaptive study](adaptive.md) covers an attacker who has read the templates, with 24 hand-written strategies. The model has no tools. Keyword and exact scorers miss paraphrases. A prompt defense is not a security boundary. One quantized snapshot is not a model family. A lower attack-success rate can come with lower utility. gpt-oss was run in one decoding configuration, chosen because greedy decoding at the default effort loops. This benchmark does not establish real-world safety.
