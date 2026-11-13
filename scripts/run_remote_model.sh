#!/usr/bin/env bash
# One model through the full placement protocol, against a vLLM server (for example a
# rented GPU pod). The harness runs here; only prompts and answers cross the network.
#
#   PIE_OPENAI_BASE_URL=https://<server> \
#   PIE_OPENAI_LAUNCH_ARGS="vllm/vllm-openai:v0.33.0 --dtype bfloat16 ..." \
#   scripts/run_remote_model.sh LABEL MODEL [extra pie flags, e.g. --no-think]
#
# Steps, all resumable: the tuning grid under the three templates and the two
# tool-result placements, the ranking, the held-out test, the original static documents
# under all five conditions, the clean carriers, and the placement controls.
set -eu

label=$1
model=$2
shift 2
OUT=${OUT:-results/v06}
flags=(--provider openai --model "$model" "$@")

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

log "grid $label"
pie adaptive grid "${flags[@]}" --condition all --output-dir "$OUT/$label-grid"
pie adaptive grid "${flags[@]}" --condition toolrole --output-dir "$OUT/$label-grid"
pie adaptive rank --input-dir "$OUT/$label-grid" --output "$OUT/$label-ranking.json" --top 3
log "test $label"
pie adaptive test "${flags[@]}" --ranking "$OUT/$label-ranking.json" --output-dir "$OUT/$label-test"
log "static $label"
pie adaptive static "${flags[@]}" --condition all --output-dir "$OUT/$label-test"
pie adaptive static "${flags[@]}" --condition toolrole --output-dir "$OUT/$label-test"
log "carrier $label"
pie adaptive carrier "${flags[@]}" --condition all --output-dir "$OUT/$label-carrier"
pie adaptive carrier "${flags[@]}" --condition toolrole --output-dir "$OUT/$label-carrier"
log "control $label"
pie adaptive control "${flags[@]}" --output-dir "$OUT/$label-test"
# The tool-result placements again, with the document JSON-encoded in the tool message.
pie adaptive control "${flags[@]}" --condition tooljson --output-dir "$OUT/$label-test"
log "done $label"
