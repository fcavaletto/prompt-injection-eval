#!/usr/bin/env bash
# Rebuild everything under results-published/v03/ from the raw runs in results/v03/.
# No model is called. Run from the repository root after scripts/run_study_v03.sh.
set -u

RAW=${RAW:-results/v03}
PUB=${PUB:-results-published/v03}
MODELS=(gpt-oss-20b qwen3-14b qwen3-4b deepseek-r1-14b)
mkdir -p "$PUB"

present=()
for model in "${MODELS[@]}"; do
  run="$RAW/$model-r1"
  [ -s "$run/raw_results.jsonl" ] || { echo "missing $run"; continue; }
  present+=("$model")
  mkdir -p "$PUB/$model"
  cp "$run/raw_results.jsonl" "$PUB/$model/raw_results.jsonl"
  pie analyze --input-dir "$PUB/$model" --output-dir "$PUB/$model"
  # Human columns stay empty: nobody has labelled the 0.3.0 rows.
  pie review --input "$PUB/$model/raw_results.jsonl" --output "$PUB/$model/manual_review.csv"
done

inputs=()
for model in "${present[@]}"; do inputs+=(--input-dir "$PUB/$model"); done
pie compare "${inputs[@]}" --output-dir "$PUB/compare"
pie stats "${inputs[@]}" --output-dir "$PUB/stats"

# The 0.2.0 runs again, with the author's labels, to calibrate the lenient reading.
pie stats --input-dir results-published/deepseek-r1-14b --input-dir results-published/qwen2.5-7b \
  --reviews results-published/deepseek-r1-14b/manual_review.csv \
  --reviews results-published/qwen2.5-7b/manual_review.csv \
  --output-dir "$PUB/stats-v02"

# Repeats. Raw files are published so the variability numbers can be checked.
for model in "${present[@]}"; do
  dirs=(--input-dir "$PUB/$model")
  for rep in r2 r3; do
    for candidate in "$RAW/$model-$rep" "$RAW/$model-smoke-$rep"; do
      if [ -s "$candidate/raw_results.jsonl" ]; then
        name=$(basename "$candidate")
        mkdir -p "$PUB/repeats/$name"
        cp "$candidate/raw_results.jsonl" "$PUB/repeats/$name/raw_results.jsonl"
        dirs+=(--input-dir "$PUB/repeats/$name")
      fi
    done
  done
  if [ "${#dirs[@]}" -ge 4 ]; then
    pie variability "${dirs[@]}" --output-dir "$PUB/variability/$model"
  fi
done

# The 40 original cases, 0.2.0 run against 0.3.0 run, for DeepSeek.
if [ -s "$PUB/deepseek-r1-14b/raw_results.jsonl" ]; then
  pie variability --input-dir results-published/deepseek-r1-14b --input-dir "$PUB/deepseek-r1-14b" \
    --output-dir "$PUB/variability/deepseek-r1-14b-v02-vs-v03"
fi

# gpt-oss decoding sensitivity.
for name in gpt-oss-20b-greedy-medium-smoke gpt-oss-20b-t1-medium-smoke-s42 \
  gpt-oss-20b-t1-medium-smoke-s43 gpt-oss-20b-t1-medium-smoke-s44; do
  if [ -s "$RAW/$name/raw_results.jsonl" ]; then
    mkdir -p "$PUB/sensitivity/$name"
    cp "$RAW/$name/raw_results.jsonl" "$PUB/sensitivity/$name/raw_results.jsonl"
    pie analyze --input-dir "$PUB/sensitivity/$name" --output-dir "$PUB/sensitivity/$name"
  fi
done
seeds=()
for seed in 42 43 44; do
  d="$PUB/sensitivity/gpt-oss-20b-t1-medium-smoke-s$seed"
  [ -s "$d/raw_results.jsonl" ] && seeds+=(--input-dir "$d")
done
if [ "${#seeds[@]}" -ge 4 ]; then
  pie variability "${seeds[@]}" --output-dir "$PUB/sensitivity/variability-t1-seeds"
fi
echo "analysis written under $PUB"
