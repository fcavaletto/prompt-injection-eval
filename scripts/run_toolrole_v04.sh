#!/usr/bin/env bash
# The tool-result placement arm of the 0.4.0 adaptive study: the same strategy library,
# tuning seeds, and held-out seeds, with the document delivered as the result of a
# `read_document` tool call (conditions `tool` and `tool_defended`, see
# src/prompt_injection_eval/adaptive/toolrole.py). Every step resumes.
#
#   HF_HUB_CACHE=/path/to/huggingface/hub scripts/run_toolrole_v04.sh
set -eu

OUT=${OUT:-results/v04}
export HF_HUB_OFFLINE=1
LABELS=(qwen3-4b qwen3-14b gpt-oss-20b)

flags() {  # identical to scripts/run_adaptive_v04.sh
  case "$1" in
    qwen3-4b) echo "--provider mlx --model mlx-community/Qwen3-4B-Instruct-2507-4bit" ;;
    qwen3-14b) echo "--provider mlx --model mlx-community/Qwen3-14B-4bit --no-think" ;;
    gpt-oss-20b)
      echo "--provider mlx --model mlx-community/gpt-oss-20b-MXFP4-Q4" \
        "--reasoning-effort low --profile reasoning" ;;
  esac
}

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

for label in "${LABELS[@]}"; do
  log "tool grid $label"
  # shellcheck disable=SC2046
  pie adaptive grid $(flags "$label") --condition toolrole --output-dir "$OUT/$label-grid"
  # Ranks every condition in the grid directory. The template rankings do not change.
  pie adaptive rank --input-dir "$OUT/$label-grid" --output "$OUT/$label-ranking.json" --top 3
  log "tool test $label"
  # shellcheck disable=SC2046
  pie adaptive test $(flags "$label") --ranking "$OUT/$label-ranking.json" \
    --output-dir "$OUT/$label-test"
  log "tool static $label"
  # shellcheck disable=SC2046
  pie adaptive static $(flags "$label") --condition toolrole --output-dir "$OUT/$label-test"
  log "tool carrier $label"
  # shellcheck disable=SC2046
  pie adaptive carrier $(flags "$label") --condition toolrole --output-dir "$OUT/$label-carrier"
  log "placement control $label"
  # defended-v1 without the line after the document: is it the tool role or the position?
  # shellcheck disable=SC2046
  pie adaptive control $(flags "$label") --output-dir "$OUT/$label-test"
done
log "done"
