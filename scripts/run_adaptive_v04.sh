#!/usr/bin/env bash
# The 0.4.0 adaptive study, in the order it was run. Every step appends to a
# raw_results.jsonl and resumes, so the script can be restarted after an interruption.
#
# Requirements: an Apple Silicon Mac, `pip install -e ".[mlx]"`, and the three MLX
# snapshots in the Hugging Face cache. Nothing is downloaded.
#
#   HF_HUB_CACHE=/path/to/huggingface/hub scripts/run_adaptive_v04.sh
set -eu

OUT=${OUT:-results/v04}
export HF_HUB_OFFLINE=1

LABELS=(qwen3-4b qwen3-14b gpt-oss-20b)

flags() {  # per-model generation flags, identical to the 0.3.0 static study
  case "$1" in
    qwen3-4b) echo "--provider mlx --model mlx-community/Qwen3-4B-Instruct-2507-4bit" ;;
    qwen3-14b) echo "--provider mlx --model mlx-community/Qwen3-14B-4bit --no-think" ;;
    gpt-oss-20b)
      echo "--provider mlx --model mlx-community/gpt-oss-20b-MXFP4-Q4" \
        "--reasoning-effort low --profile reasoning" ;;
  esac
}

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# 1. Per model: the dev grid (24 strategies x 30 dev seeds x 3 conditions), the ranking,
# the held-out test of the top three strategies per condition plus the plain override
# as a reference, and the clean carriers with nothing appended.
for label in "${LABELS[@]}"; do
  log "grid $label"
  # shellcheck disable=SC2046
  pie adaptive grid $(flags "$label") --output-dir "$OUT/$label-grid"
  pie adaptive rank --input-dir "$OUT/$label-grid" --output "$OUT/$label-ranking.json" --top 3
  log "test $label"
  # shellcheck disable=SC2046
  pie adaptive test $(flags "$label") --ranking "$OUT/$label-ranking.json" \
    --output-dir "$OUT/$label-test"
  log "carrier $label"
  # shellcheck disable=SC2046
  pie adaptive carrier $(flags "$label") --output-dir "$OUT/$label-carrier"
done

# 1b. Patch round on Qwen3-4B: the same grid against the patched template (condition
# `hardened`), the ranking rebuilt with four conditions, the held-out test (which also
# replays the strategy that was first-ranked against datamarking), and clean carriers.
label=qwen3-4b
log "patch $label"
# shellcheck disable=SC2046
pie adaptive grid $(flags "$label") --condition hardened --output-dir "$OUT/$label-grid"
pie adaptive rank --input-dir "$OUT/$label-grid" --output "$OUT/$label-ranking.json" --top 3
# shellcheck disable=SC2046
pie adaptive test $(flags "$label") --ranking "$OUT/$label-ranking.json" \
  --output-dir "$OUT/$label-test"
# shellcheck disable=SC2046
pie adaptive carrier $(flags "$label") --condition hardened --output-dir "$OUT/$label-carrier"

# 2. Transfer: the first-ranked strategy of the other two models, on each model's
# held-out seeds. Units already run in step 1 are skipped.
for label in "${LABELS[@]}"; do
  transfer=()
  for other in "${LABELS[@]}"; do
    [ "$other" = "$label" ] || transfer+=(--transfer-ranking "$OUT/$other-ranking.json")
  done
  log "transfer $label"
  # shellcheck disable=SC2046
  pie adaptive test $(flags "$label") --ranking "$OUT/$label-ranking.json" \
    "${transfer[@]}" --output-dir "$OUT/$label-test"
done

# 3. Attacker model on the held-out seeds of the two Qwen targets: with feedback, and
# the blind budget-matched control. In the published run this arm failed: the attacker
# model mostly did not write instructions. See docs/adaptive.md.
ATTACKER=mlx-community/Qwen3-14B-4bit
for label in qwen3-4b qwen3-14b; do
  for mode in feedback blind; do
    log "attacker $label $mode"
    # shellcheck disable=SC2046
    pie adaptive attacker $(flags "$label") --attacker-model "$ATTACKER" --mode "$mode" \
      --budget 5 --output-dir "$OUT/$label-attacker"
  done
done

# 4. Report.
labels=()
for label in "${LABELS[@]}"; do labels+=(--label "$label"); done
pie adaptive report --results-dir "$OUT" --static-dir results-published/v03 \
  "${labels[@]}" --output-dir "$OUT/report"
log "done"
