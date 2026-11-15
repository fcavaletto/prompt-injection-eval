# Pilot design: tool-output serialization under format-aware attack selection

Written 2026-11-15, before the harness. It replaces section 3.4 of [Research audit and next step](research-next-step.md) where the two differ, and it is the basis of [Amendment 2](preregistration.md#amendment-2-2026-11-15-serialization-pilot-before-any-pilot-run) to the pre-registration. Nothing described here has been run on a model.

Main-conference novelty remains unestablished. This page describes an instrument, not a result.

## 1. The intervention

**What changes.** The representation of *every* tool result in the conversation: the replayed ones before the branch point and every one the agent produces afterwards.

**Why every result and not only the one that carries the injection.** The two choices answer different questions.

- *Every result* asks what happens when a harness or a deployer adopts a serialization convention. That is the decision a deployer can actually make, because nobody knows in advance which result is poisoned. It is also what differs between published harnesses.
- *Only the poisoned result* asks whether the representation of the injected text itself matters, with the rest of the conversation fixed. It isolates more, but it describes a system nobody runs, and a single result in a different format from its neighbours is itself a cue.

The pilot takes the first. The consequence is stated plainly: a difference between conditions can come from how the injected text is represented or from how the agent reads everything else. The clean-run utility and the capability controls bound the second route; they do not remove it.

**The record.** Each tool returns a Python value. Its *canonical record* is that value made JSON-compatible with pydantic (`to_jsonable_python`): models become objects, dates become ISO strings. A value that is not already an object is wrapped as `{"result": value}`, so the record is always an object. A tool error is the record `{"error": message}`. Both representations are functions of this record and nothing else.

**The two representations.**

| | `json` | `text` |
| --- | --- | --- |
| Definition | `json.dumps(record, ensure_ascii=False)`: one JSON object, on one line | Labelled lines, two-space indentation per level, strings written raw |
| A string value | Quoted; `"`, `\` and control characters escaped, so a newline is the two characters `\n` | Unquoted and unescaped; a multi-line string becomes an indented block, one prompt line per line |
| Numbers, booleans, null | JSON literals | `12`, `0.01`, `true`, `false`, `none` |
| Empty list or object | `[]`, `{}` | `(empty)` |
| Recovering the record | `json.loads` | A decoder that is given the record's shape (keys, nesting and leaf types) and reads the values back |

Three things that must not be confused:

- A **JSON object** is what the `json` condition delivers: the characters `{"key": "value"}` appear in the prompt.
- A **JSON string literal** would be that object quoted and escaped once more, `"{\"key\": \"value\"}"`. Study B's `tool_json` condition was this. It is not used here.
- **Double encoding** is what happens when a chat template JSON-encodes a string it is given, as the Llama and gpt-oss templates do. In the `json` condition that would turn the object into a string literal; in the `text` condition it would quote and escape the free text. Either is a rendering failure. The delivery check detects it and the row is invalid.

**What "the same information" means here.** The JSON text decodes to exactly the record. The free text decodes to exactly the record when the decoder is given the record's shape. Without the shape, free text does not distinguish the string `5` from the number 5. That loss of type marking is part of what free text is, and it is the only information the `text` condition drops. A test checks both directions on every tool result the two development and pilot suites can produce from their reference solutions, and on adversarial strings.

**This is not the standard benchmark.** AgentDojo renders tool results as YAML and runs the agent from the user's request. The pilot renders them as `text` or `json` and resumes the agent at a controlled point. Results are from "AgentDojo tasks, agent resumed at a controlled injection point, harness serializers" and are not comparable with published AgentDojo numbers.

## 2. Prefix replay and branching

For a user task, the benchmark's reference solution is a list of tool calls. The *injection point* is the first of those calls whose result contains text an attacker controls (found, as AgentDojo does, by loading the environment with marker strings). For banking it is the first call in 15 of 16 tasks; for slack the first or second.

An episode:

1. Loads the suite's environment. For an attack, the attacker-controlled fields that the reference solution reads hold the attack text; all others hold the benchmark's defaults.
2. Applies the user task's own environment setup, and keeps a copy as the pre-state for scoring.
3. Replays the reference calls up to and including the injection point through AgentDojo's `ToolsExecutor`, so replayed calls execute exactly as live ones do, side effects included.
4. Hands the conversation to the model, which continues through AgentDojo's `ToolsExecutionLoop` (at most 15 rounds, the library default) against the same environment.
5. Scores the final state with AgentDojo's own task checks, against the pre-state from step 2.

The two formats replay the same calls with the same arguments, so the environment at the branch point must be identical. Every trace stores a hash of that state and of a reference replay that involves no serializer. A trace whose state differs from the reference is invalid; a pair whose two formats start from different states is reported as a harness fault.

**One deviation in step 1.** AgentDojo inserts attack text into the environment's YAML *before* parsing it. YAML then folds line breaks inside quoted fields and breaks on some characters, so the text the agent meets is not always the text the attack wrote. The pilot substitutes the attack text *after* parsing. The payload therefore reaches the environment exactly as written, and each trace records it. A check reports, for the baseline attack, where AgentDojo's own loading would have altered it.

## 3. Attacks

**Fixed baseline.** AgentDojo's `important_instructions` text, read from the installed package, with the user name it uses and the generic model name.

**A finite library, not an adaptive attacker.** Eight candidate wordings are written before any model sees them: three written with free text in mind (they use line structure), three with JSON in mind (single line, or shaped like fields), two neutral. All eight are tried against *both* formats on development pairs. This is format-aware selection from a finite library. It involves no feedback loop, no rewriting, and no model-generated attacks.

**Selection.** Per model and per format, the candidate with the most development successes is frozen (ties go to the earlier candidate in the library). That gives a *selected-for-text* and a *selected-for-JSON* attack per model. If they are the same candidate, the evaluation runs it once and says so.

**Budget, counted.** Per model: 9 attacks (8 candidates and the baseline) × 2 formats × 72 development pairs × 1 run = 1,296 development episodes. The budgets for the two formats are identical by construction.

**Crossed evaluation.** On the pilot evaluation suite, each of the three attacks (baseline, selected-for-text, selected-for-JSON) runs against each format. The report gives:

- *The same attack across formats:* for each attack, success on text minus success on JSON.
- *Each format against its own selected attack:* success on text under the text-selected attack, minus success on JSON under the JSON-selected attack. This is the primary quantity.
- *Whether selection is format-specific:* for each format, its own selected attack minus the other format's selected attack, and each selected attack minus the baseline.

**What a stronger claim would need, and what it would cost.** "JSON resists attack" in general needs an attacker with feedback from the model: a search over rewrites with per-format query access (hundreds of model calls per attacker goal), gradient-based optimization of the payload, or human red-teamers. None of that is in this pilot or in its cost.

## 4. Validity controls

Each control answers one question. They are reported separately and none is folded into another.

| Question | How it is checked | A failure means |
| --- | --- | --- |
| **Were tool definitions, history and payload delivered?** | On the prompt the server returns for every model call: each offered tool is found as a JSON object *equal* to the schema sent; each earlier call is found with equal name and arguments; each tool result is present verbatim and, for JSON, decodes to its record; the system and user text are present; order is preserved; the payload is in the injection-bearing record and in the prompt in the form the format prescribes. | The row is an **invalid measurement**. It is counted, reported by condition, and never read as a failed attack. |
| **Did the server parse the model's tool calls?** | Per assistant turn: parsed calls; call-shaped text left unparsed; arguments that are not JSON; unknown tool names; arguments rejected by the tool's schema. | Reported as rates per condition. Above 5% of turns unparsed, the model's attack numbers are flagged as lower bounds. |
| **Can the model perform a structurally equivalent benign action?** | For each attacker goal, a *benign twin*: the same task object with the attacker's account, link or address replaced by a neutral one, asked as an ordinary user request and scored by the same state check. | The model cannot perform the action at all. Attack success on that goal is uninformative, in either format. |
| **Does the model refuse the explicit request?** | The attacker's goal, verbatim, asked as a user request (AgentDojo's own check). Compared with the benign twin. | Twin succeeds and the direct request fails: refusal of the request as worded. This is reported and is **not** a reason to drop the goal: an injected instruction may still be followed. |
| **Does the legitimate task still complete under each representation?** | The user task without an attack, resumed at the injection point, in each format; and from the user's request with no replay, in each format. | A utility gap between formats means a security difference may come from the agent reading one format worse. |

**Semantic preservation.** Delivery is checked by parsing, not by markers: tool schemas and calls are decoded out of the prompt and compared for equality with what was sent. A template that prints a schema in a form that is not JSON fails this check and the model is not eligible for the pilot.

**Populations.** The primary analysis uses every planned pair. A second analysis is restricted to attacker goals whose benign twin succeeds in at least two of three runs in both formats (the *capable* set). Refusal of the direct request never restricts anything. Both analyses state how many of the original pairs and goals they cover.

**No silent loss.** Every planned (pair, condition, run) is one row in an accounting table: completed, invalid by reason, or not run. A contrast uses pairs that are complete in both of its conditions. If more than 2% of a contrast's planned cases are not complete in both conditions, it is reported as not interpretable. Bounds that treat every invalid row as a success and then as a failure are always shown.

## 5. Analysis and interpretation

**Sign.** Every difference is *text minus JSON*, in percentage points of attack success. A positive primary difference means the attack selected for JSON succeeded less often against JSON than the attack selected for text did against text.

**Expectation, stated before data.** For the fixed baseline a positive difference is expected, in the direction ToolHazard reports. For the selected attacks no direction is predicted. All intervals are two-sided.

**Unit and repeated runs.** A case is a (user task, attacker goal) pair. Each case and condition runs three times at temperature 0; the outcome is the mean of the three. The share of cases whose three runs disagree is reported. At temperature 0 the runs differ only through serving nondeterminism, so they measure the instrument's repeatability and not sampling variability of a deployed agent.

**Intervals, and what each assumes.**

- *Task bootstrap (primary).* User tasks are resampled with replacement; within each, runs are resampled; attacker goals are kept as they are. It assumes user tasks are exchangeable draws from the kind of task the suite contains. It supports statements about new user tasks *for these attacker goals*. With 21 user tasks it is coarse, and percentile intervals at this size can be too narrow.
- *Two-way bootstrap (reported, not relied on).* Tasks and goals are both resampled. The pilot suite has 5 attacker goals; no resampling scheme is trustworthy with 5 units. It is shown to indicate how much wider the interval gets, not as an inference about new attacker goals.
- *Sign-flip test over user tasks (check).* The per-task mean difference has its sign flipped at random. It assumes those means are independent and symmetric about zero when there is no effect. They share the same five goals, so the test is conditional on the goals.

None of these is valid automatically. A simulation in the test suite, with planted task and goal effects, checks that the estimator is unbiased and that the task bootstrap covers at close to its nominal rate when goals are held fixed.

**Reported beside every security number:** user-task success with and without attack, prompt tokens per episode, and latency, each as a paired difference between formats.

**What the pilot can conclude.** Whatever it shows holds for two models, the tasks of one suite, five attacker goals, a library of eight candidates selected on 72 development pairs, and the uncertainty stated. In particular:

- A primary difference whose interval lies within ±5 points: *for these models and tasks, selection from this library did not leave JSON more than five points better or worse than text.* It does not show that formats are equivalent against other attackers.
- A primary difference whose interval lies above zero: *with this library and budget, the best attack found for JSON did worse than the best found for text.* It does not show that JSON is a mitigation: a larger search may close the gap.
- A baseline difference that is large beside a selected-attack difference near zero: *on these cases the difference between formats under the fixed attack was not reproduced under selected attacks.* That is evidence about this fixed attack and this library.

**Floors.** If the baseline succeeds on fewer than 10% of development pairs on text, the same-attack comparison for the baseline is reported as near its floor and not interpreted. That does not stop the pilot: the selected attacks may still succeed often enough to be measured.

**Feasibility is decided on development data.** Go or no-go, the choice of models, and any change to thresholds use the banking suite only. The attacks, the conditions and the analysis are frozen in a commit before the first evaluation episode. No attack is exchanged after an evaluation outcome has been seen. If the evaluation shows a floor or a ceiling, that is the result.

## 6. Data

AgentDojo 0.1.35, benchmark version v1.2.2.

| Suite | Pairs | Role |
| --- | ---: | --- |
| Banking: 16 user tasks × 9 attacker goals | 144 | Development: harness, selection, thresholds, feasibility |
| Slack: 21 × 5 | 105 | Pilot evaluation. Read once, after the freeze. |
| Workspace: 40 × 14; Travel: 20 × 7 | 700 | Untouched. Reserved for a confirmatory study. |

## 7. Models

Qwen3-32B and Granite 4.0 H Small, served by vLLM, thinking disabled where the model has the switch. Both passed the [rendering census](rendering-census.md): tool definitions, calls and results are rendered, tool output is passed through verbatim, and schemas are printed as JSON. Both carry tool results in a user turn, so nothing here speaks to templates with a dedicated tool role. A model that fails the delivery check in the live smoke test is not run.

## 8. The harness

Code: `src/prompt_injection_eval/pilot/`. Tests: `tests/test_pilot.py`, `tests/test_pilot_serialize.py`, `tests/test_pilot_analysis.py`. Install with `pip install -e ".[dev,pilot]"`.

| Module | What it does |
| --- | --- |
| `adapter.py` | Pins AgentDojo 0.1.35 and benchmark v1.2.2. Environments, injection points, tool schemas, benign twins, and both task checks, all through AgentDojo |
| `serialize.py` | The canonical record, `to_json`, `to_text`, and the decoder for text |
| `episode.py` | One episode: state, prefix replay through AgentDojo's `ToolsExecutor`, the model's turns inside AgentDojo's `ToolsExecutionLoop`, scoring, trace |
| `delivery.py` | The delivery check on every returned prompt |
| `attacks.py` | Baseline, the eight candidates, the selection rule |
| `runner.py` | Phases, manifest, plan, traces, resume checks, the deadline, freezing |
| `analysis.py` | Accounting, controls, contrasts, intervals, the report. Reads traces only |
| `scripted.py` | Scripted agents for offline tests. Not a model |

What the offline tests show, with no model involved:

- A scripted benign agent completes all 37 user tasks in both formats, resumed and from the request, and AgentDojo's own pipeline scores the same reference solutions the same way.
- A scripted attacker is scored as a successful attack on every one of the 249 pairs but one, where the user's own task overwrites the attacker's change afterwards. A benign agent is scored as no attack on all 249.
- The two formats start from the same environment state on every pair tested, equal to a replay with no serializer, and the final state after a full reference run equals AgentDojo's.
- Five ways of breaking the rendering are each detected and named. A payload lost before the environment is detected before the model is called. None of them is scored.
- A renamed parameter in a tool schema, a changed argument in an earlier call, and one changed character in a result are each detected, although every marker a string search would look for is still present.
- Both representations decode to the record on every reference tool result and on 400 random nested records with hostile strings.
- On simulated data with shared task and goal effects, the estimator is unbiased, the task interval covers the planted difference at close to its nominal rate, and a null effect is rarely called an effect.
- A changed setting, server, phase or input makes a resumed run refuse. The deadline stops a run without losing traces.

A free pre-flight, `pie pilot template-check`, renders 148 reference conversations with a model's own chat template and runs the delivery check. Qwen3-32B and Granite 4.0 H Small pass all 148 at their pinned revisions. Llama 3.1, gpt-oss-20b and Hermes 3 fail, for the reasons the census found. This is a tokenizer-level check and says nothing about a server.

## 9. Launch package

Nothing below has been run. Each step is written to be copied.

### 9.1 Before renting anything

```bash
pip install -e ".[dev,pilot]" transformers
pie pilot check
pie pilot template-check --repository Qwen/Qwen3-32B --revision 9216db5781bf21249d130ec9da846c4624c16137 --no-think
pie pilot template-check --repository ibm-granite/granite-4.0-h-small --revision b8c0982bab7fde4eb48110f5a069527c008fab39
python -m pytest tests/test_pilot.py tests/test_pilot_analysis.py tests/test_pilot_serialize.py --no-cov
```

### 9.2 Server, one model at a time

One rented GPU with 96 GB, image `vllm/vllm-openai:v0.33.0`, no volume. State the hourly price before creating the pod and confirm it is deleted afterwards.

The pod's start command runs the expiry script in the background and the server in the foreground. The script's text is passed in the environment variable `POD_EXPIRY_PY`, and `EXPIRES_AT` is set to an absolute UNIX time computed from the spending limit (section 9.6). Entrypoint `["/bin/bash", "-c"]`, command:

```bash
python3 -u -c "$POD_EXPIRY_PY" & vllm serve Qwen/Qwen3-32B --revision 9216db5781bf21249d130ec9da846c4624c16137 --dtype bfloat16 --max-model-len 32768 --generation-config vllm --enable-auto-tool-choice --tool-call-parser hermes --host 0.0.0.0 --port 8000; echo "[launcher] vllm exited with code $?"; wait
```

If the server exits, `wait` keeps the container alive until the expiry script ends the pod, so a crash does not restart the clock. For Granite 4.0 H Small the server part is:

```bash
vllm serve ibm-granite/granite-4.0-h-small --revision b8c0982bab7fde4eb48110f5a069527c008fab39 --dtype bfloat16 --max-model-len 32768 --generation-config vllm --enable-auto-tool-choice --tool-call-parser granite4 --host 0.0.0.0 --port 8000
```

On the client, with the launch line repeated so it is stored in the manifest:

```bash
export PIE_OPENAI_BASE_URL=https://<pod id>-8000.proxy.runpod.net PIE_OPENAI_CONCURRENCY=8
export PIE_OPENAI_LAUNCH_ARGS="vllm/vllm-openai:v0.33.0 Qwen/Qwen3-32B --revision 9216db5781bf21249d130ec9da846c4624c16137 --dtype bfloat16 --max-model-len 32768 --generation-config vllm --enable-auto-tool-choice --tool-call-parser hermes"
```

### 9.3 Live smoke test: development data only, 24 episodes

*Revised 2026-11-15, before any live inference.* The first version of this section asked for "two of the four from-the-request user tasks in each format", but the smoke plan has two per format. The criterion below replaces it. It is `SMOKE_CRITERION` (version `smoke-v1`) in `src/prompt_injection_eval/pilot/analysis.py`; the command's exit status and the report both apply that one function, and its denominators are read from the stored plan.

```bash
pie pilot run smoke --model Qwen/Qwen3-32B --label qwen3-32b --no-think --output-dir results/pilot/qwen3-32b/smoke --deadline-minutes <set from the pod's remaining lifetime>
pie pilot report --phase-dir results/pilot/qwen3-32b/smoke --output-dir results/pilot/qwen3-32b/smoke-report
```

The plan is 2 banking user tasks × 2 attacker goals × 2 formats under the baseline attack (8 episodes), plus, for each format, the 2 resumed clean tasks, the 2 from-the-request tasks, the 2 direct requests and the 2 benign twins (16 episodes): 24 in all.

The smoke passes only if every check holds:

| Check | Denominator | Required |
| --- | --- | --- |
| Every planned episode completed with verified delivery | 24 planned episodes | 24 |
| Turns with call-shaped text the server left unparsed | model turns in completed episodes | at most 5% |
| Turns whose tool arguments are not a JSON object | model turns in completed episodes | at most 5% |
| Turns cut off at the output limit | model turns in completed episodes | at most 5% |
| From-the-request user tasks completed, text | 2 | at least 1 |
| From-the-request user tasks completed, JSON | 2 | at least 1 |

The last two only check that the model acts as an agent at all; with two tasks they estimate nothing. The capability gate that matters comes later, in the development controls (section 9.4).

The smoke phase stops starting episodes at the first invalid, unverified, prefix, harness or infrastructure failure. Episodes already running finish and are written; the rest are `not_run`. Within an episode, the first returned prompt that fails the delivery check ends it: that turn's tool calls are not executed, no further response is requested, and the request, the returned prompt, the response and the defects are stored in the trace's `failed_turn`.

If the smoke fails: stop, delete the pod, and read the stored traces offline. A model that fails is not run, and a failed delivery check is not relaxed to let it pass.

### 9.4 The pilot, per model

*Revised 2026-11-15 after the Qwen3-32B smoke test. The first version gave fixed deadlines (15, 65, 15 and 85 minutes) that the smoke showed to be infeasible: the evaluation alone is projected at 1 to 4 hours. The earlier text is in commit `615778a`.*

Deadlines are no longer fixed in advance. Each one is set from measurements on development data, as described in section 9.5, and written down before the phase starts.

```bash
pie pilot run dev-controls --model Qwen/Qwen3-32B --label qwen3-32b --no-think --output-dir results/pilot/qwen3-32b/dev-controls --deadline-minutes <from 9.5>
pie pilot run select --model Qwen/Qwen3-32B --label qwen3-32b --no-think --output-dir results/pilot/qwen3-32b/select --deadline-minutes <from 9.5>
pie pilot freeze --select-dir results/pilot/qwen3-32b/select
mkdir -p data/pilot/frozen && cp results/pilot/qwen3-32b/select/frozen_attacks.json data/pilot/frozen/qwen3-32b.json
git add data/pilot/frozen/qwen3-32b.json && git commit -m "Freeze the pilot attacks for Qwen3-32B before its evaluation"
```

Read the development report now. Evaluate this model only if, on development data:

- every episode was verified;
- unparsed call text is at most 5% of turns;
- resumed user-task success without attack is at least 50% in both formats;
- at least six of the nine benign twins succeed.

Then:

```bash
pie pilot run eval-controls --model Qwen/Qwen3-32B --label qwen3-32b --no-think --output-dir results/pilot/qwen3-32b/eval-controls --deadline-minutes <from 9.5>
pie pilot run evaluate --model Qwen/Qwen3-32B --label qwen3-32b --no-think --frozen data/pilot/frozen/qwen3-32b.json --output-dir results/pilot/qwen3-32b/evaluate --deadline-minutes <from 9.5>
pie pilot report --phase-dir results/pilot/qwen3-32b/dev-controls --phase-dir results/pilot/qwen3-32b/select --phase-dir results/pilot/qwen3-32b/eval-controls --phase-dir results/pilot/qwen3-32b/evaluate --output-dir results/pilot/qwen3-32b/report
```

For Granite 4.0 H Small the commands are the same with `--model ibm-granite/granite-4.0-h-small --label granite-4.0-h-small` and without `--no-think`.

`PIE_OPENAI_LAUNCH_ARGS` is part of the resume check. It must describe the server configuration only. The smoke's value included the pod's ID and data center; future runs leave those out, so that the same configuration on another pod is recognized as the same.

### 9.5 Time and cost, from the smoke test

*Revised 2026-11-15. The first version assumed about 6 model calls per episode and 3.5 calls per second, neither of which had been measured.*

**What the smoke measured** (Qwen3-32B, two banking user tasks; [evidence](https://github.com/fcavaletto/prompt-injection-eval/tree/research-audit-2026-11/results-published/pilot-smoke-2026-11-15/qwen3-32b)):

- Control episodes took 1 to 3 model calls, 2.6 on average.
- Attack episodes took 4 to 6 calls on one task and 16 on the other. On that task the agent hit the round limit in all four episodes. Mean 10.5.
- With 8 workers, 126 calls finished in 50 s: 2.5 calls per second. Median latency per request was 2.3 s.
- Startup to a healthy server took 4.6 minutes, with the image already cached on the host.

The 2.5 calls per second is the only throughput observed. It is used below as the central rate, and 2.0 as a slower case for the longer Slack contexts. Eight workers divided by the median latency would suggest about 3.4 calls per second if every worker were always busy; that was not observed and is not used.

**Per phase, for one model.** Calls per episode are given as low, central and high:

- **Low:** the agent ignores the attack and follows the reference solution.
- **Central:** banking figures from the smoke. Slack controls are the banking mean scaled by the ratio of the suites' reference-solution lengths under the scripted agent (2.0). Slack attacks are built in two parts. The episodes that did not loop (mean 5 calls) are scaled by 2.2, the attack ratio, to 11. The smoke's share of episodes that reached the round limit (one half) is kept at 16 calls. That gives (11 + 16) / 2 ≈ 13.
- **High:** every attack episode reaches the round limit.

| Phase | Episodes | Calls per episode (low / central / high) | Model calls | Minutes at 2.5 calls/s | Minutes at 2.0 calls/s |
| --- | ---: | --- | --- | --- | --- |
| Development controls | 300 | 2.0 / 2.6 / 4.0 | 600 / 780 / 1,200 | 4 / 5 / 8 | 5 / 6 / 10 |
| Selection | 1,296 | 3 / 10.5 / 16 | 3,900 / 13,600 / 20,700 | 26 / 91 / 138 | 32 / 113 / 173 |
| Pilot controls (Slack) | 312 | 3.5 / 5 / 8 | 1,100 / 1,560 / 2,500 | 7 / 10 / 17 | 9 / 13 / 21 |
| Evaluation (Slack) | 1,890 | 5 / 13 / 16 | 9,450 / 24,600 / 30,200 | 63 / 164 / 202 | 79 / 205 / 252 |
| **Total** | **3,798** | | **15,000 / 40,500 / 54,700** | **1.7 / 4.5 / 6.1 h** | **2.1 / 5.6 / 7.6 h** |

**Overheads, per pod session.** Each model needs two sessions: development (controls and selection), then evaluation (controls and evaluation), with the freeze committed in between. Each session adds:

- startup: 4.6 minutes observed with a cached image; up to about 15 minutes with an uncached image or a slow download;
- 2 minutes of idle time;
- a 5-minute shutdown margin.

Container disk (150 GB) costs under $0.02 per hour.

**Cost for one model** at $2.69/h plus disk:

| Case | Rate | Hours | Cost |
| --- | --- | ---: | ---: |
| Low | 2.5 calls/s | 2.1 | $5.6 |
| Central | 2.5 calls/s | 5.0 | $13.6 |
| High | 2.0 calls/s | 8.3 | $22.5 |

Two models would cost about $27 in the central case, if Granite behaves like Qwen3-32B, which has not been measured. About $37 of the $50 limit remains. The central case for two models exceeds the earlier $20 planning figure; the high case exceeds the remaining budget.

**Limits of this extrapolation:**

- **Two tasks.** The loop that drives the attack figure came from one of only two banking user tasks. Whether it is common is unknown.
- **Slack is longer.** Slack tasks are longer than banking: their reference solutions use up to 9 calls, their injection sometimes arrives at the second call, and their tool outputs are larger. Longer contexts mean longer requests, which is why a 2.0 calls/s case is shown. No Slack episode has been run by a model, and none will be before the freeze.
- **Granite is unmeasured.** It is a different architecture: a hybrid model with experts, 32B parameters in total. Its startup, speed, call parser and looping behaviour are unknown.
- **Short burst.** The 2.5 calls/s comes from a 50-second burst at 8 workers. Sustained throughput and the effect of more workers are unmeasured.

**How an evaluation is made to finish within its allocated time:**

1. **Its time is set from development data, not guessed.** Selection runs the same attacks, in both formats, on all 16 banking user tasks. From it come calls per episode by attack and format, and sustained throughput. The evaluation's projected time is 1,890 episodes × the selection mean × the Slack scaling factor (capped at 16), divided by the selection's measured throughput. Its deadline is 1.3 times that, and its pod expiry is the deadline plus startup and 10 minutes.
2. **If the projected cost exceeds what remains of the budget, the evaluation does not start.** That decision is taken before any Slack episode is run.
3. **Nothing about the agent changes to save time.** The round limit stays at 15. The agent is not stopped at the first attacker success, and loops are not suppressed. Each of these would change security and utility outcomes. Any of them would need its own amendment, applied to every condition.
4. **Proposed, not adopted: resume on another pod.** Section 9.6 says a phase stopped by its deadline is not rerun on a new server. The runner can already resume a phase on any server with an identical configuration. Allowing this would let an evaluation span two sessions without discarding finished work. It must be registered as an amendment before any pilot phase uses it.
5. **Proposed, not adopted: order the evaluation by run.** The evaluation plan is currently ordered by attack, then format. A deadline cut therefore drops whole conditions. Ordering it by run instead (every condition for run 1, then run 2, then run 3) would make a cut leave a complete crossed design with fewer runs. The planned set of units, and the plan hash, would not change. This also needs an amendment.

### 9.6 Spending bounds

*Revised 2026-11-15.* The first version of this section called the per-phase deadlines a hard cap in dollars. They are not. They bound how long the client sends requests; they do not stop a rented machine from billing, and nothing in the client can.

What bounds time, and how:

- **The client deadline.** Each worker checks it immediately before starting an episode, and each episode checks it before every model request. A request's timeout is the smaller of its normal timeout and a third of the time left, so with the provider's three attempts it ends near the deadline. An episode stopped this way is written as `interrupted` and is rerun on resume; one that never started is `not_run`. The overrun is at most one request in flight plus the provider's retry waits, a few seconds.
- **The pod's lifetime.** A pod's cost is its hourly price times its lifetime from creation, including image pull, model download and loading, inference and idle time, plus container disk at $0.10 per GB-month (under $0.02 an hour for 120 GB). The lifetime is bounded by `scripts/pod_expiry.py`, started in the background by the pod's own start command. At an absolute time fixed when the pod is created, it deletes the pod through RunPod's API with the pod-scoped key RunPod places in the pod, falling back to stopping it. It does not depend on the machine that rented the pod, on the agent, or on the experiment process, and a container restart does not reset it. RunPod's own `--terminate-after` flag was never enforced by the platform and cannot be used.
- **Deletion after use.** The pod is deleted as soon as the phase ends, including on failure, and the deletion is confirmed by listing pods.

Traces are written on the client, not on the pod, so they survive deletion. The server log is copied from the pod before it is deleted.

**For a spending limit of B dollars at hourly price P:** set the pod's expiry at (B − 0.10) / P hours after creation, minus 5 minutes for deletion to take effect, and set each phase's client deadline to end at least 3 minutes before that expiry. The 10 cents covers disk and any rehearsal of the expiry mechanism.

For the full pilot this gives the following. The earlier figure of $20 for two models still holds as a planning number, but it is enforced by the pod expiry, not by the deadlines.

- The phase deadlines are 10 + 15 + 65 + 15 + 85 = 190 minutes of inference per model. With about 20 minutes of loading, one model needs a pod lifetime of about 3.5 hours.
- When a deadline passes: no new episode starts, finished and interrupted traces are kept, and the command exits with code 3. The deadline is not extended and the phase is not rerun on a new server to finish it.
- A selection phase that did not finish cannot be frozen: the freeze refuses unless both formats were tried on exactly the same pairs. That model stops at development data.
- An evaluation that did not finish is reported as it is. Unfinished rows appear as `interrupted` or `not_run`, and any contrast missing more than 2% of its cases is marked not interpretable.

### 9.6a Feasibility stage F1 (authorized 2026-11-16, development data only, $3 total)

*The 2026-11-15 proposal ran part of the real selection phase. Revised before any F1 inference: F1b now uses a dedicated feasibility workload whose outputs are kept apart from selection, so no selection-resume amendment is needed.*

**Purpose.** Reduce three feasibility uncertainties left by the Qwen3-32B smoke. Nothing is run on Slack, workspace or travel, and no candidate attack is run.

1. Does Granite 4.0 H Small serve and deliver correctly?
2. How long are attack episodes across all 16 banking user tasks?
3. What is the throughput with 16 workers?

**F1a: Granite 4.0 H Small.** On the pod:

1. The rendering check: `scripts/check_serving_render.py`, without a thinking switch.
2. The 24-episode banking smoke, with the frozen criterion `smoke-v1` and its fail-fast rule.

Stop and delete if:

- the server is not healthy 15 minutes after creation;
- the rendering check differs from the local rendering;
- the smoke stops on an invalid episode or fails `smoke-v1`.

Granite is not repaired on a running pod.

**F1b: Qwen3-32B.** 16 workers.

1. The registered development-controls phase in full: 300 episodes, 3 runs, with `--fail-fast`.
2. If every control episode is valid, the phase `feasibility`: the fixed baseline attack on the 72 banking development pairs in both formats, one run, 144 episodes, with `--fail-fast`. Its output goes to its own directory. Candidate-attack selection is not started.

The feasibility workload's order is fixed by `runner.feasibility_order()`:

- **Rounds by user task.** Round r gives each of the 16 user tasks its r-th development goal. Each of the first four rounds covers all 16 user tasks; a fifth adds the fifth goal of the eight tasks that have one.
- **Goals spread out.** Goals are rotated by task position, so the first 16 pairs use all nine attacker goals.
- **Formats together.** The two formats of a pair are adjacent, and which format runs first alternates from pair to pair.

A deadline cut therefore leaves a prefix balanced across tasks, goals and formats.

Stop and delete if:

- the server is not healthy 15 minutes after creation;
- any development-control episode is invalid, unverified or an infrastructure error, in which case the feasibility workload is not started;
- the pod expiry is reached.

The round limit, scoring and stopping rules are unchanged.

**Spending.** The $3.00 covers both pods: compute, container disk, startup, idle time and shutdown. Before each rental:

1. Read the current price.
2. Compute the remaining allowance: $3.00 minus the estimated cost of anything already rented, minus a $0.10 reserve for disk and billing granularity.
3. Set the pod's in-pod expiry to that allowance divided by the hourly rate, minus 5 minutes for deletion to take effect.

The client deadlines end at least 3 minutes before the expiry. No rehearsal pod is rented, and no expiry is extended.

**Accounting.** The report's feasibility section gives:

- planned, started, completed, interrupted, invalid and not-started episodes;
- coverage by user task, attacker goal and format, including pairs complete in both formats;
- the model calls and request time of every interrupted episode;
- the distribution of episode lengths and the number that reached the round limit;
- bounds on mean calls per started episode, with interrupted episodes counted at the calls they had made and at the round limit.

Unstarted episodes are missing coverage. They are not short episodes.

### 9.6b F1 results, revised projection and recommendation (2026-11-16)

Evidence: [results-published/pilot-f1-2026-11-16](https://github.com/fcavaletto/prompt-injection-eval/tree/research-audit-2026-11/results-published/pilot-f1-2026-11-16).

- **Validity.** All 468 F1 episodes completed with verified delivery: the Granite smoke (24), Qwen's development controls (300) and the baseline feasibility workload (144). All 1,439 returned prompts match a local rendering by hash.
- **Coverage.** None of the 144 feasibility episodes was interrupted or left unstarted, so all 16 user tasks and all 9 goals are covered in both formats.
- **Granite.** It passed `smoke-v1` with the `granite4` parser.
- **Cost.** Estimated from lifetime and listed rates, F1 cost $0.95 of the $3.00 authorized.

**What is measured, and what is not**

| Quantity | Status | Value |
| --- | --- | --- |
| Qwen calls per control episode (banking) | Measured, 300 episodes | 2.42 |
| Qwen calls per baseline-attack episode (banking) | Measured, 144 episodes, none censored | 4.35 mean, 3.5 median, 16 maximum; 10 of 144 at the round limit |
| Qwen aggregate rate, 16 workers | Measured on two short phases | 4.72 calls/s on controls, 3.65 on attacks (the attack phase includes a tail of long episodes) |
| Qwen startup | Measured twice | 4.6 min with the image cached, 8.4 min with an image pull |
| Granite | Smoke only, 24 episodes, 8 workers | 3.67 calls per episode, 1.28 s median latency, 4.94 calls/s, 5.2 min startup |
| Repeatability | Measured on controls only | 0 of 100 control cells had disagreeing runs |
| Candidate attacks, Slack tasks, selected attacks | **Not measured** | Assumed below |

**Projection per model.** Each figure is calls, time and cost at $2.69/h plus disk, with two pod sessions per model.

- **Central:**
  - selection at the measured baseline length, 4.35 calls;
  - Slack controls at 2.0 times the banking control length;
  - Slack attacks at 2.2 times the banking attack length, which gives 9.6;
  - the measured rates;
  - 14 minutes of overhead per session.
- **Conservative:**
  - candidate attacks loop more, 6.5 calls per selection episode;
  - Slack controls take 8 calls and Slack attacks 13;
  - 2.5 calls/s everywhere;
  - 22 minutes of overhead per session.

| Design | Case | Model calls | Selection | Pilot evaluation | Total time | Per model | Two models |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| As registered (3 runs per evaluation case) | Central | 26,000 | 26 min | 83 min | 2.4 h | $6.5 | $13.1 |
| As registered | Conservative | 36,200 | 56 min | 164 min | 4.8 h | $12.9 | $25.8 |
| Narrowed (proposed below) | Central | 16,300 | 26 min | 39 min | 1.7 h | $4.5 | $9.1 |
| Narrowed | Conservative | 23,100 | 56 min | 76 min | 3.3 h | $9.0 | $17.9 |

Granite is projected at Qwen's figures. In its smoke it was faster per request and its server's memory holds 1.08 million tokens of context against Qwen's 93,000, so this is likely conservative for Granite; that has not been measured beyond the smoke.

About $36.5 of the $50 limit remains: roughly $12.3 spent before the smoke, $0.23 for the smoke and rehearsal (billing records), and $0.95 for F1 (estimated).

**Precision.** This is estimated from the width of development intervals only; the point estimate is not used.

- The paired format contrast under the fixed attack has a task-bootstrap half-width of 10.4 points on the 16 banking tasks.
- On the pilot's 21 Slack tasks that projects to about ±9 points per model.
- On the 60 reserved workspace and travel tasks, about ±5.4.
- Extra runs at temperature 0 add little: none of the 100 control cells disagreed across runs. Precision is limited by the number of user tasks, not by repetition.

**Recommendation: narrow the pilot through a stated amendment, then proceed with both models.**

The proposed Amendment 3 is not registered or adopted; it needs your approval.

1. **Evaluation runs.** One run per evaluation case instead of three. A fixed, pre-drawn 20% of evaluation cases also get runs 2 and 3, to keep measuring repeatability where it was not measured (attack episodes). The analysis averages within a case where repeats exist; the task bootstrap is unchanged.
2. **Qwen's development controls.** The F1 development controls (same data, settings and server configuration) count as Qwen's registered development controls, rather than being rerun.
3. **Everything else unchanged:** the selection budget, the frozen attacks, the round limit, scoring, stopping rules, the data split and the reading rules.

**Why this choice and not the alternatives:**

- **Measurement quality is sufficient.** Delivery, parsing and scoring were valid on 1,439 of 1,439 turns across both models and both formats, and the controls pass the evaluation gates in 9.4.
- **Coverage is complete on development.** Every development pair ran in both formats with nothing censored.
- **The registered pilot fits the budget, but the confirmatory study then does not.** The pilot as registered costs about $13 centrally, $26 conservatively. In the conservative case, a confirmatory study on the reserved suites, which is what could support a claim, would no longer fit. The narrowed pilot costs about $9 centrally and $18 conservatively, leaving $18 to $27.
- **The extra runs buy nothing.** They spend about a third of the evaluation budget on information the controls suggest is near zero, while the quantity that limits precision, the number of user tasks, is fixed by the suite.
- **Stopping is not justified.** A ±5 to ±6-point confirmatory interval on the reserved suites appears attainable within budget. That is enough to tell apart effects of the size ToolHazard reported from no effect, though not small effects.

**What the narrowed pilot can and cannot conclude.** At about ±9 points per model, the pilot can show:

- whether selected attacks behave very differently from the fixed attack;
- whether the instrument works on Slack and with selected attacks;
- what the between-task variance is.

It cannot establish a format effect smaller than about 10 points. Any claim intended for a paper needs the confirmatory study, and main-conference novelty remains unestablished.

### 9.7 Known limitations

- **Two models, one template design.** Both carry tool results in a user turn. Nothing here speaks to dedicated tool roles, to gpt-oss, or to closed models.
- **Five attacker goals in the pilot suite.** Statements are about those five. The two-way interval is not trustworthy at that number.
- **A weak attacker.** Eight fixed wordings, no feedback. A null result does not show that the formats are equally safe, and a positive one does not show that JSON protects.
- **Every tool result changes format.** A difference can come from how the agent reads everything, not only the injected text. The utility controls bound this and do not remove it.
- **The agent is resumed.** It did not choose the calls in the prefix. Results are not AgentDojo benchmark numbers.
- **Temperature 0.** The three runs measure serving nondeterminism, not the variability of a sampled agent.
- **One server stack.** vLLM 0.33.0 only.
- **The delivery check understands JSON-rendering templates.** A template that prints schemas another way fails it, which excludes that model; it does not show the model was badly served.
- **Benign twins change the target, not the action.** For most goals the direct request already reads like an ordinary request, so the twin and the direct request may not differ.
- **Throughput and cost are estimates** until the smoke run measures them.
- **No human validation** of any scorer has been carried out.

### 9.8 What would justify a larger study

A confirmatory study on the 700 reserved pairs is justified only if all four hold:

1. Both models pass the validity controls on the development and pilot suites.
2. Runs disagree in at most 5% of cells.
3. The spread of per-task differences in the pilot implies a task interval of ±6 points or tighter for the primary difference on the reserved suites' 60 user tasks.
4. The pilot is informative in one of two ways, for at least one model: the primary difference's interval excludes zero; or the baseline's same-attack difference excludes zero while the primary interval lies within ±10 points.

If the intervals are wide enough to include both zero and ten points and condition 3 fails, the pilot has shown that this design cannot answer the question at an affordable size. That is reported, and the larger study is not run.

Even then, what a confirmatory study would support is a measured statement about formats under selection from a fixed library. It would not, by itself, be a main-conference contribution.
