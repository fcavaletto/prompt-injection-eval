#!/usr/bin/env bash
# The 0.3.0 study, in the order it was run. Each step appends to raw_results.jsonl and
# resumes, so the script can be restarted after an interruption.
#
# Requirements: an Apple Silicon Mac, `pip install -e ".[mlx]"`, the four MLX snapshots
# in the Hugging Face cache, and Ollama with deepseek-r1:14b installed. Nothing is
# downloaded: HF_HUB_OFFLINE=1 and the script never calls `ollama pull`.
#
#   HF_HUB_CACHE=/path/to/huggingface/hub scripts/run_study_v03.sh
set -u

DATA=data/cases_v2.jsonl
OUT=${OUT:-results/v03}
export HF_HUB_OFFLINE=1
: "${HF_HUB_CACHE:?Set HF_HUB_CACHE to the Hugging Face hub cache that holds the snapshots}"

GPT_OSS=mlx-community/gpt-oss-20b-MXFP4-Q4
QWEN3_14B=mlx-community/Qwen3-14B-4bit
QWEN3_4B=mlx-community/Qwen3-4B-Instruct-2507-4bit
DEEPSEEK=deepseek-r1:14b

SMOKE_IDS=(benign_control_001 direct_override_001 delimiter_escape_002
  metadata_injection_004 output_format_hijack_001 secret_exfiltration_003)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

gpt_oss() {  # $1 = output suffix; remaining args are extra flags
  local dir=$1; shift
  pie run --provider mlx --model "$GPT_OSS" --reasoning-effort low --profile reasoning \
    --dataset "$DATA" --condition all --seed 42 --output-dir "$OUT/$dir" "$@"
}
qwen3_14b() {
  local dir=$1; shift
  pie run --provider mlx --model "$QWEN3_14B" --no-think \
    --dataset "$DATA" --condition all --seed 42 --output-dir "$OUT/$dir" "$@"
}
qwen3_4b() {
  local dir=$1; shift
  pie run --provider mlx --model "$QWEN3_4B" \
    --dataset "$DATA" --condition all --seed 42 --output-dir "$OUT/$dir" "$@"
}
deepseek() {
  local dir=$1; shift
  pie run --provider ollama --model "$DEEPSEEK" --profile reasoning --num-ctx 8192 \
    --dataset "$DATA" --condition all --seed 42 --output-dir "$OUT/$dir" "$@"
  # Unload so the next MLX model does not share unified memory with a 14B Ollama model.
  ollama stop "$DEEPSEEK" >/dev/null 2>&1 || true
}

# 1. Headline runs on the MLX models.
log "gpt-oss-20b r1"; gpt_oss gpt-oss-20b-r1
log "qwen3-14b r1"; qwen3_14b qwen3-14b-r1
log "qwen3-4b r1"; qwen3_4b qwen3-4b-r1

# 2. One repeat of the full grid with identical settings, for the run-to-run noise floor.
# (A second full repeat was planned and cut for time before any repeat had run.)
log "repeat r2"
gpt_oss gpt-oss-20b-r2
qwen3_14b qwen3-14b-r2
qwen3_4b qwen3-4b-r2

smoke_flags=()
for id in "${SMOKE_IDS[@]}"; do smoke_flags+=(--case-id "$id"); done

# 3. gpt-oss decoding sensitivity on the six smoke cases.
#    a) greedy with the template's default effort (medium): how often does it loop?
#    b) the recommended sampling (temperature 1.0) with medium effort, three seeds.
log "gpt-oss sensitivity: greedy, medium effort"
pie run --provider mlx --model "$GPT_OSS" --reasoning-effort medium --profile reasoning \
  --dataset "$DATA" --condition all --seed 42 --output-dir "$OUT/gpt-oss-20b-greedy-medium-smoke" \
  "${smoke_flags[@]}"
for seed in 42 43 44; do
  log "gpt-oss sensitivity: temperature 1.0, medium effort, seed $seed"
  pie run --provider mlx --model "$GPT_OSS" --reasoning-effort medium --profile reasoning \
    --temperature 1.0 --dataset "$DATA" --condition all --seed "$seed" \
    --output-dir "$OUT/gpt-oss-20b-t1-medium-smoke-s$seed" "${smoke_flags[@]}"
done

# 4. DeepSeek-R1 through Ollama. The 65 new cases first, then the 40 from 0.2.0, so an
# interruption leaves the new cases complete rather than the old ones.
NEW_IDS=$(python -c "
import json
lines = open('$DATA').read().splitlines()
print(' '.join('--case-id ' + json.loads(l)['id'] for l in lines[40:]))")
OLD_IDS=$(python -c "
import json
lines = open('$DATA').read().splitlines()
print(' '.join('--case-id ' + json.loads(l)['id'] for l in lines[:40]))")
log "deepseek-r1-14b r1 (new cases)"
# shellcheck disable=SC2086
deepseek deepseek-r1-14b-r1 $NEW_IDS
log "deepseek-r1-14b r1 (0.2.0 cases)"
# shellcheck disable=SC2086
deepseek deepseek-r1-14b-r1 $OLD_IDS

# 5. DeepSeek repeats on the six smoke cases only; its full grid takes hours.
for rep in r2 r3; do
  log "deepseek smoke repeat $rep"
  deepseek "deepseek-r1-14b-smoke-$rep" "${smoke_flags[@]}"
done
log "done"
