#!/usr/bin/env bash
# Study A of docs/preregistration.md: the JSON mechanism controls for one model, with every
# condition the comparisons need generated in the same server session.
#
#   PIE_OPENAI_BASE_URL=https://<server> scripts/run_mechanism_controls.sh LABEL MODEL [pie flags]
#
# Two fixed attacks (the static document and the plain override) on the 59 held-out seeds,
# under the three templates, the raw and JSON-encoded tool results, and the four mechanism
# conditions. Resumable. A ranking with no conditions is written so `pie adaptive report`
# builds the placement and mechanism tables without a tuning grid.
set -eu

label=$1
model=$2
shift 2
OUT=${OUT:-results/v07}
flags=(--provider openai --model "$model" "$@")
mkdir -p "$OUT/$label-grid" "$OUT/$label-carrier"
[ -f "$OUT/$label-ranking.json" ] || echo '{"conditions": {}, "conditions_plain": {}}' > "$OUT/$label-ranking.json"

for selection in all toolrole tooljson mechanism; do
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $label $selection"
  pie adaptive control "${flags[@]}" --condition "$selection" --output-dir "$OUT/$label-test"
done
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] done $label"
