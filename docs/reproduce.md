# Reproduce

The published numbers were produced on one laptop (Apple M4, 24 GB), temperature 0, seed 42. A re-run can still differ. The repeated-run section of the results page measures how much, on this machine.

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,notebook]"      # the harness, tests, and notebooks
pip install -e ".[mlx]"               # only for the MLX models, Apple Silicon only
pie validate-data --dataset data/cases_v2.jsonl
```

`pie validate-data` prints the case counts and the SHA-256 computed from the file. For the 0.3.0 study it must print `8b79034bb6549532b47a4f9fd00d1eafc554f261c8b637d9754f26b51c6d15e6`. For the 0.2.0 study, `data/cases.jsonl` must print `2d5f9b3b937d24de8476ff2b4dbd7c2f7c5b6bb4ae4db34c88ccad9001609fa8`.

## Where the models come from

The harness never downloads weights.

- **MLX models** are read from a Hugging Face cache. Point `HF_HUB_CACHE` at it and set `HF_HUB_OFFLINE=1`. The 0.3.0 study used `mlx-community/gpt-oss-20b-MXFP4-Q4`, `mlx-community/Qwen3-14B-4bit`, and `mlx-community/Qwen3-4B-Instruct-2507-4bit`; the snapshot hash of each is recorded in every row under `runtime_info.snapshot`. If your snapshot differs, your weights differ.
- **Ollama models** must already be installed (`ollama list`). `pie doctor --provider ollama --model deepseek-r1:14b` checks that.

## Smoke first

```bash
export HF_HUB_CACHE=/path/to/huggingface/hub HF_HUB_OFFLINE=1
pie doctor --provider mlx --model mlx-community/Qwen3-4B-Instruct-2507-4bit
pie run --provider mlx --model mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --dataset data/smoke_cases.jsonl --condition all --seed 42 \
  --output-dir results/qwen3-4b-smoke
pie analyze --input-dir results/qwen3-4b-smoke --output-dir reports/qwen3-4b-smoke
```

Read `reports/qwen3-4b-smoke/report.md` before scheduling anything longer.

## The 0.3.0 study

`scripts/run_study_v03.sh` is the generation sequence. It writes `results/v03/`. It resumes, so an interrupted run continues in the same JSONL instead of starting over. `scripts/analyze_study_v03.sh` copies those files into `results-published/v03/` and builds the reports. It does not call a model. The core generation commands are:

```bash
# gpt-oss-20b: low reasoning effort, 4096-token budget
pie run --provider mlx --model mlx-community/gpt-oss-20b-MXFP4-Q4 \
  --reasoning-effort low --profile reasoning \
  --dataset data/cases_v2.jsonl --condition all --seed 42 --output-dir results/v03/gpt-oss-20b-r1

# Qwen3-14B with thinking off; Qwen3-4B-Instruct as is
pie run --provider mlx --model mlx-community/Qwen3-14B-4bit --no-think \
  --dataset data/cases_v2.jsonl --condition all --seed 42 --output-dir results/v03/qwen3-14b-r1
pie run --provider mlx --model mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --dataset data/cases_v2.jsonl --condition all --seed 42 --output-dir results/v03/qwen3-4b-r1

# DeepSeek-R1 14B through Ollama, with an explicit 8192-token context window
pie run --provider ollama --model deepseek-r1:14b --profile reasoning --num-ctx 8192 \
  --dataset data/cases_v2.jsonl --condition all --seed 42 --output-dir results/v03/deepseek-r1-14b-r1
```

Approximate time on the M4 Air, one model at a time: gpt-oss-20b about 25 minutes for 315 generations, Qwen3-14B about 30, Qwen3-4B about 8, DeepSeek-R1 about five hours.

## Analysis

```bash
# Per-model reports and review queues
pie analyze --input-dir results/v03/gpt-oss-20b-r1 --output-dir reports/v03/gpt-oss-20b
pie review --input results/v03/gpt-oss-20b-r1/raw_results.jsonl \
  --output reports/v03/gpt-oss-20b/manual_review.csv

# All models side by side, and the paired tests
pie compare --input-dir results/v03/gpt-oss-20b-r1 --input-dir results/v03/qwen3-14b-r1 \
  --input-dir results/v03/qwen3-4b-r1 --input-dir results/v03/deepseek-r1-14b-r1 \
  --output-dir reports/v03/compare
pie stats --input-dir results/v03/gpt-oss-20b-r1 --input-dir results/v03/qwen3-14b-r1 \
  --input-dir results/v03/qwen3-4b-r1 --input-dir results/v03/deepseek-r1-14b-r1 \
  --output-dir reports/v03/stats

# Run-to-run noise. The study ran r1 and r2. A third full repeat was not run.
pie variability --input-dir results/v03/gpt-oss-20b-r1 --input-dir results/v03/gpt-oss-20b-r2 \
  --output-dir reports/v03/variability/gpt-oss-20b
```

DeepSeek's full grid is one pass. The script then repeats six smoke cases, all three conditions, twice (`results/v03/deepseek-r1-14b-smoke-r2` and `deepseek-r1-14b-smoke-r3`). gpt-oss decoding checks, greedy medium effort and temperature 1.0 at medium effort for seeds 42, 43, and 44, are separate directories and are not pooled with the headline rate.

`pie stats` re-reads each row's case from the dataset file the row names and refuses to run if that file's hash no longer matches.

`pie review` writes the queue with empty human columns. Fill those yourself. The harness will not invent them.

## The 0.4.0 adaptive study

```bash
HF_HUB_CACHE=/path/to/huggingface/hub scripts/run_adaptive_v04.sh
```

The script runs, per model, the tuning grid (24 strategies × 30 tuning seeds × 3 conditions), the ranking, the held-out test, and the clean-carrier control; then the patch round on Qwen3-4B, cross-model transfer, the attacker-model arm, and the report. It took about 20 hours on an M4 with 24 GB. Every step resumes. In the published run the patch round ran in parallel with the Qwen3-14B grid; the script runs it in sequence, which does not change any unit.

To rebuild the tables from the published rows without a model:

```bash
pie adaptive report --results-dir results-published/v04 --static-dir results-published/v03 \
  --label qwen3-4b --label qwen3-14b --label gpt-oss-20b --output-dir /tmp/adaptive-report
```

The published rows record package version 0.3.0 and the commit before this work, because they were generated from an uncommitted tree. The seed-file hash, strategy-library version, template versions, and scorer versions in each row identify what ran. Method and findings are in [adaptive.md](adaptive.md).

## The 0.2.0 study

The 40-case study is still reproducible from `data/cases.jsonl` with the commands in that release:

```bash
pie run --provider ollama --model qwen2.5:7b --dataset data/cases.jsonl \
  --condition all --seed 42 --output-dir results/qwen2.5-7b-full
pie run --provider ollama --model deepseek-r1:14b --profile reasoning --dataset data/cases.jsonl \
  --condition all --seed 42 --output-dir results/deepseek-r1-14b-full
```

The 0.2.0 rows were produced without `--num-ctx`. Rerunning the six smoke cases of `qwen2.5:7b` on 4 November 2026 returned byte-identical answers for all 18 units, with and without `--num-ctx 8192`.

## Without a model

```bash
jupyter nbconvert --execute --to notebook --stdout notebooks/01_walkthrough.ipynb > /dev/null
```

That path uses `MockProvider` only. The published tables are in `results-published/`, and notebook 02 reads them without calling a model.
