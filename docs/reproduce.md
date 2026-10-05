# Reproduce

The published numbers were produced on a laptop with Ollama, temperature 0, and seed 42. A re-run can still differ. The variability note on the results page is the measurement of that, for the smoke file, on this runtime.

## Install

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,notebook]"
pie doctor --provider ollama --model qwen2.5:7b
```

`pie doctor` checks the dataset hash, that the output directory is writable, and that the model tag is already installed. It does not download weights. Pull a tag yourself with `ollama pull` if the doctor says it is missing.

## Smoke, then the full file

```bash
pie run \
  --provider ollama \
  --model qwen2.5:7b \
  --dataset data/smoke_cases.jsonl \
  --condition all \
  --seed 42 \
  --output-dir results/qwen2.5-7b-smoke

pie analyze \
  --input-dir results/qwen2.5-7b-smoke \
  --output-dir reports/qwen2.5-7b-smoke
```

Read `reports/qwen2.5-7b-smoke/report.md` before scheduling the full file. For `deepseek-r1:14b`, add `--profile reasoning` so the output budget is 4096 tokens and the timeout is 900 seconds. Without that, a reasoning model spends the default 256 tokens inside the think block and the answer is empty.

The full study is 40 cases and three conditions, 120 generations per model:

```bash
pie run \
  --provider ollama \
  --model deepseek-r1:14b \
  --dataset data/cases.jsonl \
  --condition all \
  --profile reasoning \
  --seed 42 \
  --output-dir results/deepseek-r1-14b-full
```

Run one model at a time. A 14B reasoning model and a 7B instruct model do not need to be resident together.

## Compare, review, repeat

```bash
pie compare \
  --input-dir results/deepseek-r1-14b-full \
  --input-dir results/qwen2.5-7b-full \
  --reviews results/deepseek-r1-14b-full/manual_review.csv \
  --reviews results/qwen2.5-7b-full/manual_review.csv \
  --output-dir reports/compare

pie variability \
  --input-dir results/deepseek-r1-14b-smoke-r1 \
  --input-dir results/deepseek-r1-14b-smoke-r2 \
  --input-dir results/deepseek-r1-14b-smoke-r3 \
  --output-dir reports/deepseek-r1-14b-variability
```

`pie review` writes the queue with empty human columns. Fill those yourself. The harness will not invent them.

## Without a model

```bash
jupyter nbconvert --execute --to notebook --stdout notebooks/01_walkthrough.ipynb > /dev/null
```

That cell path uses `MockProvider` only. The published tables are in `results-published/`, and notebook 02 reads them without calling Ollama.
