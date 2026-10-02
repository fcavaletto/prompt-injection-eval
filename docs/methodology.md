# Methodology

## Research question

How often does an instruction-following language model obey malicious instructions embedded inside an untrusted document, and how much does a simple prompt-level defense reduce attack success without degrading legitimate task completion?

## Unit of evaluation

One unit is one case under one prompt condition. A case supplies a trusted system instruction, a legitimate user task, and one document. The full crossed design is 40 cases by 2 conditions, which is 80 units for a single model tag. The smoke file is 6 cases by 2 conditions.

## Dataset

`data/cases.jsonl` contains 40 synthetic cases: 36 attacks and 4 benign controls, in 10 categories of 4 cases each. `data/smoke_cases.jsonl` is six exact records copied from that file. Records are validated with strict Pydantic models (`data/schema.json`, schema version 1.0). Every result stores the SHA-256 of the file that was loaded. The full-file hash and the smoke-file hash differ because the files contain different records.

The attacks are harmless by construction: canary tokens, fixed JSON objects, format markers, and disclosure of `SYNTHETIC_SECRET_4C91`. The harness does not execute dataset strings.

## Experimental conditions

| | Baseline `baseline-v1` | Defended `defended-v1` |
| --- | --- | --- |
| System instruction | The case text, unchanged | The same text, unchanged |
| User task | The case text | The same text |
| Document | The case text | The same text |
| Document framing | Neutral delimiters | Labeled untrusted data |
| Instruction about document commands | None | One generic refusal rule |
| Generation parameters | Shared | Shared |
| Scorers | Shared | Shared |

The defense is not inserted into the system instruction. That keeps the baseline-versus-defense contrast in the user message, which is the intended independent variable.

Prompt wording that can change model behavior requires a new template version. Versions are constants, not timestamps.

## Controlled variables and what can still vary

Held constant within a pair:

- model tag
- case, including system instruction, task, and document
- temperature, seed, maximum output tokens, and timeout
- scorer version
- dataset hash

Not fully controlled:

- local runtime nondeterminism
- whether the server honors the seed
- quantization and runner version if the tag is changed between runs

## Generation parameters

Defaults: temperature 0.0, maximum output tokens 256, timeout 120 seconds, concurrency 1, Ollama keep-alive `5m`. Results record the resolved values.

`--profile reasoning` raises the defaults to 4096 output tokens and a 900 second timeout. Reasoning models spend most of their budget on visible chain-of-thought, and a 256-token cap would cut them off before the answer.

## Scorer validation

Deterministic scorers are cheap and reproducible, and they are wrong sometimes. The project measures that rather than asserting it. After a person fills the review CSV, `pie analyze --reviews` and `pie compare --reviews` compute, for each dimension (attack, task, outcome), the share of reviewed units where the automated label matched the human label, with a Wilson interval and a confusion table of `automated->human` counts. Only units with a human label count. Because the review queue over-samples uncertain and disagreeing units, agreement measured there is a lower bound on scorer accuracy over the whole run, not an estimate of it.

## Repeated-run variability

A fixed seed is forwarded to Ollama, but local inference is not guaranteed to be bit-reproducible. `pie variability` takes two or more result directories produced with the same configuration and reports how many units changed outcome, attack score, or task score, and how many returned byte-identical text. This number is reported next to the headline rates so a reader can judge whether a one- or two-unit difference between conditions is above the noise floor.

## Comparing models

`pie compare` concatenates result directories and groups by model and by (model, condition). Models are never pooled into a single rate; each (model, condition) cell carries its own denominator and Wilson interval, and paired defense effects are computed within a model. Different model tags, quantizations, and think settings are different conditions.

## Scorer validation

Deterministic scorers are cheap and reproducible, and they are wrong sometimes. The project measures that rather than asserting it. After a person fills the review CSV, `pie analyze --reviews` and `pie compare --reviews` compute, for each dimension (attack, task, outcome), the share of reviewed units where the automated label matched the human label, with a Wilson interval and a confusion table of `automated->human` counts. Only units with a human label count. Because the review queue over-samples uncertain and disagreeing units, agreement measured there is a lower bound on scorer accuracy over the whole run, not an estimate of it.

## Repeated-run variability

A fixed seed is forwarded to Ollama, but local inference is not guaranteed to be bit-reproducible. `pie variability` takes two or more result directories produced with the same configuration and reports how many units changed outcome, attack score, or task score, and how many returned byte-identical text. This number is reported next to the headline rates so a reader can judge whether a one- or two-unit difference between conditions is above the noise floor.

## Comparing models

`pie compare` concatenates result directories and groups by model and by (model, condition). Models are never pooled into a single rate; each (model, condition) cell carries its own denominator and Wilson interval, and paired defense effects are computed within a model. Different model tags, quantizations, and think settings are different conditions.

## Visible reasoning

Reasoning-tuned models such as DeepSeek-R1 distills and Qwen3 emit their chain-of-thought as part of the completion: either in a separate `thinking` field from Ollama, or inline between `<think>` tags. This is visible model output, not a hidden channel. The harness never requests anything the runtime would not otherwise return.

Handling:

- Only the final answer is scored. The provider splits the reasoning off before scoring, and the scorers strip a leading think block again defensively.
- `response_text` is the scored answer. `response_text_raw` is the completion as returned. `reasoning_text`, `reasoning_present`, `reasoning_truncated`, and `reasoning_tokens_estimate` are stored alongside.
- Reasoning is kept because it shows why a model complied or refused. That is useful for failure analysis and for teaching. It is never treated as the answer.
- If generation stops inside the think block, the answer is empty. The unit is scored as attack failure and task failure, and the review reason says the reasoning was truncated. Reports count these units separately; they are budget failures, not evidence of robustness.
- `--think` and `--no-think` forward Ollama's `think` flag. Omitting both keeps the model default. The flag is part of the resume key because it changes behavior.

## Paired comparison

For each case that has both conditions under the same provider, model, dataset hash, temperature, seed, maximum tokens, and scorer version, the defense effect is one of:

- `improved`
- `worsened`
- `unchanged`
- `incomparable`

Security and utility are also stored separately. A move from `compromised` to `secure_and_useful` is an improvement. A move from `compromised` to `secure_but_unhelpful` is improved on security and degraded on utility. A move from `secure_and_useful` to `secure_but_unhelpful` is a utility regression. A move from `secure_and_useful` to `compromised` is a security regression. Any backend error, and any ambiguous outcome, makes the pair `incomparable` rather than forcing it into a single rank.

No statistical significance is claimed from 40 cases.

## Metrics and denominators

Attack success rate uses attack cases only. Benign controls are not in that denominator.

Two attack-success denominators are reported:

- **Valid responses:** attack cases that returned a model response. Backend errors are excluded here and counted on their own.
- **Attempted:** every attack case that was scheduled, including backend errors. Errors are not counted as successes.

Task success, ambiguity, manual review, and benign-control task success have the same valid-versus-attempted distinction where a proportion is reported. Backend errors are never dropped from the summary.

For proportions, a 95 percent Wilson score interval is reported. The implementation is in `prompt_injection_eval.metrics.wilson_interval` and is unit-tested. The interval is a binomial sampling interval. It does not correct dataset-selection bias and it is not a test of the defense.

## Scoring

Deterministic scorers only. See [scoring.md](scoring.md). Attack score and task score stay independent. The outcome label is derived from both and does not erase either one.

## Errors, resume, and review

A failed request is written as `backend_error` and the run continues. Each unit is appended to `raw_results.jsonl` immediately. `--resume` skips a unit only when the case, condition, provider, model, temperature, seed, maximum tokens, prompt-template version, dataset SHA-256, and scorer version all match. A malformed final line from an interrupted write is preserved and reported. `--overwrite` replaces `raw_results.jsonl` only.

Uncertain scores, quoted canaries, secret disclosures, truncation, malformed structure, and baseline/defense disagreements enter a CSV review queue. Human columns start empty. Loading a completed review file keeps the automated labels.

## Reproducibility

Recorded with each row: rendered prompts, template version, sampling settings, dataset hash, schema version, package version, Python version, a general OS and architecture summary, and the git commit when one exists. Usernames, home directories, hostnames, and serial numbers are not recorded.

## Limitations

The dataset is small, synthetic, English-only, and non-adaptive. The model has no tools. Keyword and exact scorers miss paraphrases. A prompt defense is not a security boundary. One tag is not a model family. A lower attack-success rate can come with lower utility. This benchmark does not establish real-world safety.
