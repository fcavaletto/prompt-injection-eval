# Changelog

## Unreleased

- **Feasibility stage F1 (2026-11-16).** A dedicated development-only phase `feasibility` (the baseline attack on the 72 banking development pairs in both formats, in a fixed balanced order), feasibility accounting that keeps interrupted episodes as censored observations and unstarted ones as missing coverage, a `--fail-fast` option for any phase, and `scripts/check_serving_render.py`. Plan and ordering committed before inference.
- **Pilot smoke evidence (2026-11-15).** The Qwen3-32B development smoke test (24 banking episodes, criterion `smoke-v1` passed) is archived in `results-published/pilot-smoke-2026-11-15/qwen3-32b/` with its traces, plan, manifest, reports, serving check, prompt-hash verification, timings and cost record. `scripts/verify_pilot_prompts.py` checks every stored prompt hash against a local rendering (126 of 126 match). Reports now separate termination (round limit) from validity and outcomes. The launch schedule in `docs/pilot-design.md` is replaced by one built from the smoke's measurements, and a further development-only stage is proposed but not authorized.
- **Pilot launch fixes (2026-11-15).** Episodes end at the first prompt that fails the delivery check, without executing its tool calls; the smoke phase starts no further episode after an invalid one. The client deadline is checked before every episode start and every model request, request timeouts are bounded by the time left, and cut-off episodes are written as `interrupted`. The smoke pass criterion is frozen as `smoke-v1` and used by both the exit status and the report. `scripts/pod_expiry.py` deletes a rented pod from inside at a fixed time; the docs no longer describe client deadlines as a dollar cap.
- **Pilot harness (2026-11-15).** `src/prompt_injection_eval/pilot/` and `pie pilot`: a pinned AgentDojo adapter (0.1.35, benchmark v1.2.2), a canonical record with free-text and JSON serializers, state-preserving prefix replay and branching through AgentDojo's own executor and loop, a delivery check that compares decoded schemas, calls and results with what was sent, a crossed attack evaluation with selection from a fixed library, manifests, complete traces, resume checks, a wall-clock deadline, and a report built from traces. Offline tests use scripted agents; no model has been run. Design and launch package: `docs/pilot-design.md`. Registered as Amendment 2. New optional extra `pilot`; a separate CI job runs its tests.
- **Corrections (2026-11-15).** `docs/corrections.md` lists ten published statements that are invalid, unsupported or overstated, with a dated note at each place they appear (README, home page, adaptive, placement, InjecAgent, related work, pre-registration) and `results-published/CORRECTIONS.md` beside the untouched rows. The main ones: Phi-4-mini and Granite 3.3 were not validly run with tools in Study B; the gpt-oss prompts cannot be checked; "it is the role, not the position" is withdrawn as worded.
- **Rendering census (2026-11-15).** `scripts/rendering_census.py` renders four fixed conversations through 26 model templates at pinned revisions and 11 Ollama library templates, and compares 144 stored vLLM prompts with a local rendering. No weights, no generation. Results in `results-published/rendering-census-2026-11-15/`, write-up in `docs/rendering-census.md`, counts pinned by `tests/test_rendering_census.py`. The sample, fixtures and script were committed before the census ran.
- **Literature re-verified (2026-11-15).** The closest papers were read in full text. The novelty assessment is revised: ToolHazard already reports the serialization effect with numbers, and several papers study the serving stack as a confound. `docs/research-next-step.md` now recommends a narrower pilot and states that no novel contribution is established yet.
- **Human validation prepared, not done.** `docs/annotation-protocol.md` and a blinded 239-item sample (`data/annotation/study-b-v1/`, drawn by `scripts/annotation_sample.py`). No rater has labelled anything.
- **Evidence audit (2026-11-14).** Added `docs/research-next-step.md` and its appendix: an audit of Studies A and B, a novelty assessment against the closest literature, and a proposal for the next study. Exploratory re-analysis (`scripts/audit_exploratory.py`, tables in `results-published/audit-2026-11-14/`) found that Phi-4-mini was never shown tool definitions in Study B, that Granite 3.3 was not shown the completed call, that no prompt was stored for gpt-oss, and that InjecAgent's cases are 17 user contexts crossed with 62 attacker goals. Dated notes on the placement, InjecAgent and pre-registration pages qualify the affected claims; the published text and verdicts are unchanged.
- **Guards.** The InjecAgent runner now fingerprints every request and refuses to resume a results file written from a different prompt, tool set or server configuration. Each row records what the chat template dropped or re-encoded (`render_defects`), and the smoke test fails when a tool definition or a completed call is missing from the rendered prompt.
- `docs/preregistration.md`: hypotheses, primary families, and interpretation rules for four follow-up studies, committed before any of them ran.
- Study A (JSON mechanism controls): conditions `tool_flat` and `user_json` (with `_defended` variants), `pie adaptive control --condition mechanism`, a mechanism table with its own Holm families, and `scripts/run_mechanism_controls.sh`. Run on the ten models; pre-registered verdict *mixed* (removing line breaks helped on no model; JSON-encoding the flattened text helped significantly on four). Rows and report in `results-published/v07/`; write-up in `docs/placement.md`.
- `pie adaptive report` no longer fails when there are no adaptive rows to chart.
- Study B (InjecAgent replication): InjecAgent's data vendored at upstream `f19c9f2c` (MIT), `pie injecagent smoke|run|report`, and tool calling in the remote provider (`tool_choice`, parsed calls recorded). Ten models, 126,480 generations, no errors. Pre-registered verdict: the placement effect does not replicate (4 of 10 models, all Qwen3; criterion 7). Rows and report in `results-published/v08/`; write-up in `docs/injecagent.md`; the placement claim is narrowed in the README and `docs/placement.md`.

## 0.6.0

The placement result on ten models, and a correction.

- **Remote serving.** `--provider openai` sends prompts to an OpenAI-compatible chat server, written for vLLM: tool conversations in wire format, `chat_template_kwargs` for thinking, `reasoning_effort`, retries on a busy proxy, and the server's rendered prompt stored with every row (`return_prompt_text`). The server address is never written. Settings come from `PIE_OPENAI_*` variables. The adaptive runner sends requests in parallel when a provider declares `concurrency`, and still writes rows in plan order.
- **JSON-encoded tool result.** Conditions `tool_json` (`tool-json-v1`) and `tool_json_defended` (`tool-json-defended-v1`) put the document into the tool message as a JSON string. `pie adaptive control --condition tooljson` runs them with the two fixed attacks.
- **The ten-model study.** Qwen3-4B, 8B, 14B and 32B, Qwen2.5-7B, Hermes 3 8B, Granite 3.3 8B, Phi-4-mini, gpt-oss-20b and gpt-oss-120b, at full precision on vLLM 0.33.0, through the full adaptive protocol and both placement controls: 58,622 generations, no backend errors, 0 of 4,450 clean documents flagged. With the generic rule, a raw-text tool result raises the plain override on all ten models (significant on eight after Holm adjustment over 160 comparisons); JSON-encoding takes much of it back on most. The adaptive strategy still gets 45 to 58 of 59 with the rule. Findings in `docs/placement.md`; rows, rankings, rendered-prompt samples and the report in `results-published/v06/`. About $3.40 of rented GPU time.
- **Correction.** 0.5.0 reported that the tool placement protected gpt-oss-20b (41 to 23 of 59). The MLX chat template JSON-encodes tool content; with raw content on vLLM the same move goes from 25 to 47, and JSON-encoding there gives 20. The claim is withdrawn in `docs/adaptive.md`, `docs/related-work.md`, and the README.
- `pie adaptive report`: `--static-dir` is optional; new tables for placement counts and for a repeated held-out run (`LABEL-repeat`), a second placement figure, and the static-versus-adaptive figure wraps into rows for many models.
- `scripts/run_remote_model.sh` runs the protocol for one model against a server. The v06 rows record package version 0.5.0.

## 0.5.0

Three answers to the most direct criticisms of the 0.4.0 study.

- **Without the blank character.** `pie adaptive rank` also ranks the 12 strategies with ordinary spacing (`conditions_plain` in the ranking file), and `pie adaptive test` runs that ranking's first strategy. Under datamarking it gets 17, 28, and 23 of 59 on Qwen3-4B, Qwen3-14B, and gpt-oss-20b, against 1 to 3 for the static documents. The report has a section for it.
- **Quiet successes.** An attack success on a row whose task also passed. The report counts them per condition and per goal. Only the secret-disclosure and tool-call goals allow one; on those 16 held-out seeds, 4 to 6 attacks per model and defense are quiet.
- **Tool-result placement.** Conditions `tool` (`tool-v1`) and `tool_defended` (`tool-defended-v1`) deliver the document as the result of a `read_document` tool call, rendered by each model's own chat template. Providers accept a full message list and tool schemas (`GenerationRequest.messages` and `tools`); Ollama reports them as unsupported. `pie adaptive static` reruns the original documents under new conditions. The plain override succeeds 57/59 and 51/59 on the Qwen3 models with the rule and the document in a tool result, against 14 and 12 in the user message; on gpt-oss-20b the placement alone takes it from 41 to 23, and an adaptive strategy still gets 48.
- **Placement control.** Condition `defended_no_tail` (`defended-v1-no-tail`) is `defended-v1` without the line after the document. `pie adaptive control` runs the static documents and the plain override under it. On Qwen3 the role, not the position of the document, accounts for most of the placement effect. The report has a paired placement table, Holm-adjusted over its rows.
- The tool-result conditions are their own Holm family, so the template family's adjusted p-values do not change.
- `scripts/run_toolrole_v04.sh` records the run; rows, rankings, and the report in `results-published/v04/` now include it. The tool-result rows record package version 0.4.0.
- README: a section for reviewers and a note on how the project was built.

## 0.4.0

An adaptive attacker for the defenses the 0.3.0 study measured.

- `data/adaptive_seeds.jsonl`: the 89 attack cases as a benign carrier plus a one-sentence ask, split by hash, stratified by goal, into 30 tuning and 59 held-out seeds before any adaptive run. Built by `scripts/build_adaptive_seeds.py`; the hash is pinned by a test.
- `pie adaptive`: `grid`, `rank`, `test`, `carrier`, `attacker`, and `report`. The strategy library (`strategies-v1`) is a 6 x 2 x 2 factorial of framing, boundary, and spacing. Strategies are ranked on the tuning seeds by greedy coverage and the first-ranked one is run once on each held-out seed. Prompts, providers, scorers, and the row format are the static study's.
- A reference strategy (the plain override on the same seeds), a clean-carrier control, cross-model transfer, and a patched template `defended-v3` (condition `hardened`) for one defender round.
- The 0.4.0 study: Qwen3-4B, Qwen3-14B, and gpt-oss-20b. First-ranked strategy, one try, 59 held-out seeds: 50 to 57 successes against the generic rule and 22 to 47 against datamarking, where the static documents had 1 to 7 and 1 to 3. The patch takes Qwen3-4B from 40/59 to 26/59. Findings in `docs/adaptive.md`; rows, rankings, and the report in `results-published/v04/`, rows gzipped.
- A model-written attack arm (Qwen3-14B as attacker, five attempts, with and without feedback) solved 0 to 3 of 59 seeds because the attacker model mostly did not write instructions. It is published as a failed arm and supports no claim.
- The rows record package version 0.3.0: they were generated before the version was raised.
- `scripts/run_adaptive_v04.sh` records the run sequence. README and the site homepage now lead with the adaptive result; `docs/results.md` is titled "Static results".
- DeepSeek-R1 from the static study was not rerun.

## 0.3.0

A larger case file, stronger local models, and paired statistics.

- `data/cases_v2.jsonl`: 105 cases (89 attacks, 16 benign controls, 11 categories). The first 40 lines are the 0.2.0 file, byte for byte; `data/cases.jsonl` is unchanged and its hash is pinned by a test. The 65 new cases add lookalike benign controls, instructions buried in prose, light obfuscation, template-aware delimiter escapes, the secret requested through extra fields, seven longer documents, and a `tool_call_request` category. Each new case states why it exists in its `notes`. See `docs/dataset.md`.
- Schema 1.1: the `tool_call_request` category, the `tool_call_text` attack goal, and the `keyword_groups` task check. Every 1.0 file still validates.
- Scorers `attack-v2` and `task-v2`. They add the new goal and task types and detect the secret written with separators between its characters. On all 240 published 0.2.0 responses they return the same labels as v1, and a test enforces that.
- MLX provider (`--provider mlx`, optional install `.[mlx]`) for local safetensors snapshots, with Harmony-format parsing for gpt-oss and `--reasoning-effort`. A model that cannot be loaded stops the run before any row is written.
- `--num-ctx` for Ollama, recorded in each row and in the resume key when set. Each row now records `runtime_info`: runtime version, and the snapshot or digest, quantization, and size of the weights.
- `pie stats`: exact McNemar tests, paired bootstrap intervals, Holm adjustment, power and precision tables, a lenient task reading reported next to the strict score, and a tool-call text proxy. The lenient reading is calibrated, in sample, against the author's 0.2.0 labels.
- `pie variability` reports text changes that left every label unchanged separately from label flips.
- The 0.3.0 study: gpt-oss-20b, Qwen3-14B, Qwen3-4B-Instruct-2507 (MLX) and deepseek-r1:14b (Ollama) on the 105-case file under all three conditions. Each MLX model was repeated once on the full 315-unit grid. A third full repeat was not run. DeepSeek's repeat is two passes of the six-case smoke file. Raw rows stay in `results/v03/`; the cleaned bundle is `results-published/v03/`. Findings in `docs/results.md`; the 0.2.0 findings are kept on the same page, and `results-published/deepseek-r1-14b/` and `results-published/qwen2.5-7b/` are unchanged.
- `scripts/run_study_v03.sh` records the exact run sequence. `scripts/analyze_study_v03.sh` builds `results-published/v03/` from those rows and does not call a model.
- A Wilson lower bound for a zero count is exactly 0. Float error had left 0/89 a hair above 0, and the comparison chart then refused to draw the error bar.
- The dataset path check no longer mistakes a JSON-escaped newline after a colon (`Task:\n`) for a Windows drive letter.

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
