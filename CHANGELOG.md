# Changelog

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
