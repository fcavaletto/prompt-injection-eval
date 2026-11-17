# Prompt Injection Eval

[![tests](https://github.com/fcavaletto/prompt-injection-eval/actions/workflows/tests.yml/badge.svg)](https://github.com/fcavaletto/prompt-injection-eval/actions/workflows/tests.yml)
[![docs](https://github.com/fcavaletto/prompt-injection-eval/actions/workflows/pages.yml/badge.svg)](https://fcavaletto.github.io/prompt-injection-eval/)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

A measurement harness for indirect prompt injection in tool-using agents. Every request is checked for what actually reaches the model.

**Status, 2026-11-17: a research checkpoint, not a release.**

- The report is a draft.
- Independent human review is pending.
- The next study is registered (Amendment 4) but not run, and spending awaits approval ([proposal](docs/spending-proposal-2026-11-17.md)).

The earlier history of the project is in the [historical overview](docs/history.md).

## Question

When an agent reads a tool result that an attacker can write into, does serializing tool results as JSON instead of labelled text reduce unauthorized actions at a fixed attacker budget? Or does it mainly suppress particular instruction attacks while forged-data attacks still work?

A second question comes first: do evaluation harnesses deliver the conversation to the model as intended at all?

## Method

- **Verified delivery.** Each server-returned prompt is checked against the conversation sent, under the pinned chat template's layout. The [measurement contract](docs/measurement-contract.md) defines it; it was validated on a mutation corpus before and after repair.
- **Controlled episodes on AgentDojo tasks.** The agent resumes at the injection point after a replayed prefix. Outcomes come from AgentDojo's own state checks. Every tool result is serialized from one canonical record.
- **Pre-registration.** Hypotheses and decision rules are fixed before data ([pre-registration](docs/preregistration.md), Amendments 2 and 3). Exploratory analyses are labelled and dated.
- **An offline audit** of what four public harnesses deliver to the model, at pinned revisions (WP7).

## Findings

Each row has a status and its evidence in the [claim–evidence table](docs/claim-evidence.md).

| Finding | Status |
| --- | --- |
| Registered pilot (Qwen3-32B, Granite 4.0 H Small; AgentDojo Slack; 105 pairs). Each format against the attack selected for it: text minus JSON +8.6 (Qwen) and +11.4 (Granite) points. The gate for a larger study was not met. | registered |
| For Qwen, most of that is attack wording (+7.1). The same-attack format component is +1.4 (−2.9 to +6.2). | exploratory |
| For Granite, JSON was attacked about 10 points less under the same attack (+10.5, +3.8 to +17.1). Both attacks were multiline. On Slack, 7 of the baseline's 10-success gap is in episodes that reached the round limit. | exploratory, conditional |
| With the same words on one line, the baseline's JSON advantage on banking disappears (Qwen, +1.4) or reverses (Granite, −11.1). Line structure interacts with format: +15.3 and +27.8. "Only multiline attacks benefit" does not hold for Qwen. | exploratory, development data |
| Free-text tool output is structurally ambiguous: a multi-line string can render exactly like nested fields. | confirmed |
| The pilot's original per-request check missed role, duplicate and type mutations. The pilot's delivery claim rests on reconstruction: all 21,321 scored turns re-render, by SHA-256, to the server's prompt under the pinned template. The repaired check caught every constructed defect in the tested fault classes (122 of 122; evidence for those classes, not completeness) and passes all 787 retained prompts. | confirmed |
| Replaying stored calls reproduces all 4,062 archived attack episodes' final states. In 3 Granite episodes AgentDojo's trace-based check counted calls that were never executed (C25). Goal predicates can also miss real unauthorized actions (a $1,100 payment to the attacker scored as "not attacked"). | confirmed; limitation |
| AgentDojo's `local` provider turns a failed request into an empty answer, scored normally. Its published Llama 3.3 / Meta-SecAlign-70B traces contain 59 such endings, all among the longest workspace requests. They imply conditional bounds (workspace `important_instructions` 6.8% to 12.0%). The SecAlign comparison survives except on workspace `direct`, where the bounds overlap. That context limits caused the endings is unproven. | confirmed; mechanism unresolved |
| Three other harness paths pass delivery as reconstructed components. That is not certification of their original pipelines. | conditional |

## Limitations

- **Scope.** Two models, one serving stack, development suites with five and nine goals, and a fixed attack library with no adaptive attacker. Temperature 0, so repeats measure serving nondeterminism.
- **The checkers.** They are validated on the mutation classes tested, for two templates. No claim of semantic fidelity is made.
- **WP7 provenance.** It is reconstructed: code revisions are inferred, and gated templates come from mirrors.
- **No human validation.** No person has validated any scorer. The earlier studies' text-based scorer supports no current claim.

## Reproduction

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev,pilot]"
pytest                                                    # all offline
python scripts/pilot_supplementary.py results-published/pilot-2026-11-16 \
  --f1 results-published/pilot-f1-2026-11-16 --output /tmp/supplementary
python scripts/validate_checkers.py --label check --output /tmp/checkers
python scripts/pilot_rescore.py results-published/pilot-2026-11-16 --output /tmp/rescoring
pie stage1 run --batch 0 --provider scripted --output-dir /tmp/s1/batch-0   # offline dry run
pie stage1 report --batch-dir /tmp/s1/batch-0 --output-dir /tmp/s1/report
```

No step needs a GPU or a model. The registered pilot reports, prompt-hash verification, WP7 and the earlier studies are covered in [docs/reproduce.md](docs/reproduce.md).

## Where to read

| | |
| --- | --- |
| [Report draft](docs/report-draft.md) | The methods and replication report |
| [Claim–evidence table](docs/claim-evidence.md) | Every headline, its status and its evidence; the response to review |
| [Corrections](docs/corrections.md) | C1 to C24, each with a dated note where the statement appears |
| [Evidence index](docs/evidence-index.md) | Where each body of evidence lives and what checks it |
| [Pre-registration](docs/preregistration.md) | Original hypotheses and amendments, unchanged |
| [Reproduction guide](docs/reproduce.md) | Commands for every result |
| **[Stage 1 protocol](docs/protocol-stage1.md)** | **The current plan**, registered as Amendment 4 (not run): why JSON resisted, and whether forged data is affected |
| [OpenRouter screen](docs/protocol-openrouter.md) | A small API feasibility screen (not run): 5 eligible cases, two models |
| [Spending proposal](docs/spending-proposal-2026-11-17.md) | Three separately gated caps: $8, $5, $18 |
| [Human-review packet](docs/human-review-packet.md) | Attack realism, authorization and scoring, with concealed expected verdicts |
| [Adaptive protocol](docs/protocol-adaptive.md) | The follow-up, costed separately |
| [Review package, 2026-11-17](docs/review-package-2026-11-17.md) | What changed, and the checklist for a human reviewer |
| [Historical overview](docs/history.md) | The earlier studies and this README's previous text |

Code is in `src/prompt_injection_eval/`: the serialization pilot and Stage 1 in `pilot/`, and the harness audit in `wp7.py`. Results are in `results-published/`, never edited after they are written.

## How this was built

Much of the code and prose was written with an AI coding assistant (Claude Code), directed and reviewed by the author. The research questions and the decisions about what to run and what to claim are the author's.

## License and citation

MIT ([LICENSE](LICENSE)). `CITATION.cff` describes the software. When citing, give the commit, the dataset or benchmark version, and the model and template revisions.
