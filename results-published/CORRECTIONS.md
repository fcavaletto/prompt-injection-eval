# Corrections to the published results (added 2026-11-15)

The rows and reports in this directory are kept exactly as they were written. Some of what the reports say is now known to be invalid or overstated. Read `docs/corrections.md` before using them. In short:

- `v08/phi-4-mini`: **invalid as an agent measurement.** The chat template rendered no tool definitions and no completed call. The model was never told a tool existed.
- `v08/granite-3.3-8b`, conditions `tool`, `tool_json` and their `_defended` forms: **invalid.** The template dropped the completed tool call.
- `v06` and `v07`, `phi-4-mini` and `granite-3.3-8b`, tool placements: the tool turn was malformed in the same way.
- `v06`, `v07`, `v08`, `gpt-oss-20b` and `gpt-oss-120b`: **unverifiable.** The server returned no prompt for these models.
- `v08/report/report.md`: the Holm-adjusted tests treat 2,108 cases as independent. They are 17 user contexts crossed with 62 attacker goals and 2 wordings. Cluster-aware intervals are in `audit-2026-11-14/`, labelled exploratory.
- No scorer in any of these results has been validated by a human rater.

`rendering-census-2026-11-15/` holds the evidence for the template defects. `audit-2026-11-14/` holds the exploratory re-analysis.
