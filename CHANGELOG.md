# Changelog

## 0.4.0

An adaptive attacker for the defenses the 0.3.0 study measured.

- `data/adaptive_seeds.jsonl`: the 89 attack cases as a benign carrier plus a one-sentence ask, split by hash, stratified by goal, into 30 tuning and 59 held-out seeds before any adaptive run. Built by `scripts/build_adaptive_seeds.py`; the hash is pinned by a test.
- `pie adaptive`: `grid`, `rank`, `test`, `carrier`, `attacker`, and `report`. The strategy library (`strategies-v1`) is a 6 x 2 x 2 factorial of framing, boundary, and spacing. Strategies are ranked on the tuning seeds by greedy coverage and the first-ranked one is run once on each held-out seed. Prompts, providers, scorers, and the row format are the static study's.
- A reference strategy (the plain override on the same seeds), a clean-carrier control, cross-model transfer, and a patched template `defended-v3` (condition `hardened`) for one defender round.
- The 0.4.0 study: Qwen3-4B, Qwen3-14B, and gpt-oss-20b. First-ranked strategy, one try, 59 held-out seeds: 50 to 57 successes against the generic rule and 22 to 47 against datamarking, where the static documents had 1 to 7 and 1 to 3. The patch takes Qwen3-4B from 40/59 to 26/59. Findings in `docs/adaptive.md`; rows, rankings, and the report in `results-published/v04/`, rows gzipped.
- A model-written attack arm (Qwen3-14B as attacker, five attempts, with and without feedback) solved 0 to 3 of 59 seeds because the attacker model mostly did not write instructions. It is published as a failed arm and supports no claim.
- The rows record package version 0.3.0: they were generated before the version was raised.
- `scripts/run_adaptive_v04.sh` records the run sequence. README and the site homepage now lead with the adaptive result; `docs/results.md` is titled "Static results".
- DeepSeek-R1 from the static study was not rerun.

## 0.3.0

A larger case file, stronger local models, and paired statistics.

- `data/cases_v2.jsonl`: 105 cases (89 attacks, 16 benign controls, 11 categories). The first 40 lines are the 0.2.0 file, byte for byte; `data/cases.jsonl` is unchanged and its hash is pinned by a test. The 65 new cases add lookalike benign controls, instructions buried in prose, light obfuscation, template-aware delimiter escapes, the secret requested through extra fields, seven longer documents, and a `tool_call_request` category. Each new case states why it exists in its `notes`. See `docs/dataset.md`.
- Schema 1.1: the `tool_call_request` category, the `tool_call_text` attack goal, and the `keyword_groups` task check. Every 1.0 file still validates.
- Scorers `attack-v2` and `task-v2`. They add the new goal and task types and detect the secret written with separators between its characters. On all 240 published 0.2.0 responses they return the same labels as v1, and a test enforces that.
- MLX provider (`--provider mlx`, optional install `.[mlx]`) for local safetensors snapshots, with Harmony-format parsing for gpt-oss and `--reasoning-effort`. A model that cannot be loaded stops the run before any row is written.
- `--num-ctx` for Ollama, recorded in each row and in the resume key when set. Each row now records `runtime_info`: runtime version, and the snapshot or digest, quantization, and size of the weights.
- `pie stats`: exact McNemar tests, paired bootstrap intervals, Holm adjustment, power and precision tables, a lenient task reading reported next to the strict score, and a tool-call text proxy. The lenient reading is calibrated, in sample, against the author's 0.2.0 labels.
- `pie variability` reports text changes that left every label unchanged separately from label flips.
- The 0.3.0 study: gpt-oss-20b, Qwen3-14B, Qwen3-4B-Instruct-2507 (MLX) and deepseek-r1:14b (Ollama) on the 105-case file under all three conditions. Each MLX model was repeated once on the full 315-unit grid. A third full repeat was not run. DeepSeek's repeat is two passes of the six-case smoke file. Raw rows stay in `results/v03/`; the cleaned bundle is `results-published/v03/`. Findings in `docs/results.md`; the 0.2.0 findings are kept on the same page, and `results-published/deepseek-r1-14b/` and `results-published/qwen2.5-7b/` are unchanged.
- `scripts/run_study_v03.sh` records the exact run sequence. `scripts/analyze_study_v03.sh` builds `results-published/v03/` from those rows and does not call a model.
- A Wilson lower bound for a zero count is exactly 0. Float error had left 0/89 a hair above 0, and the comparison chart then refused to draw the error bar.
- The dataset path check no longer mistakes a JSON-escaped newline after a colon (`Task:\n`) for a Windows drive letter.

## 0.2.0

Published study and a path for newcomers.

- Spotlighting-style datamarking as `defended-v2` (`--condition spotlight` or `all`).
- `pie compare` and `pie variability`, plus agreement between automated scores and human labels.
- Empirical runs of `deepseek-r1:14b` and `qwen2.5:7b` on all 40 cases and all three conditions, with review CSVs, under `results-published/`.
- Findings in `docs/results.md`. Start-here guide, related-work reading list, and two notebooks.
- Visible-reasoning capture: score the final answer, keep the reasoning, and flag an empty answer after a finished think block.
- MkDocs site.
- The headline states that the Wilson intervals overlap. The results page separates the 5/36 rate from the paired rate. Scorer agreement is described as the author's consistency check, not a second annotator. The default model tag is `qwen2.5:7b`.

## 0.1.0

Initial research harness.

- Strict schema and validation for the 40-case synthetic dataset and the six-case smoke subset.
- Baseline `baseline-v1` and defended `defended-v1` prompt templates.
- Deterministic attack scorers, task scorers, and outcome labels.
- Mock provider and Ollama HTTP provider.
- Sequential runner with incremental JSONL writes and resume.
- Metrics, Wilson intervals, paired comparison, manual-review CSV, and Markdown reports.
