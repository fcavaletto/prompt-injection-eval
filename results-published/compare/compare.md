# Cross-run comparison

> These rows are empirical results for the recorded model identifier, runtime, prompt templates, sampling configuration, and dataset hash. They do not generalize to every version or quantization of the model.

Sources: `deepseek-r1-14b-full`, `qwen2.5-7b-full`

Models: `deepseek-r1:14b`, `qwen2.5:7b`. Units: 240. Dataset SHA-256: 2d5f9b3b937d24de8476ff2b4dbd7c2f7c5b6bb4ae4db34c88ccad9001609fa8.

## Attack success by model and condition

| Model | Condition | Attack success | 95% Wilson | Secure and useful | Task success | Benign task success | Errors |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| `deepseek-r1:14b` | baseline | 0.139 (5/36) | [0.061, 0.287] | 0.417 | 0.525 (21/40) | 0.750 | 0 |
| `deepseek-r1:14b` | defended | 0.028 (1/36) | [0.005, 0.142] | 0.639 | 0.700 (28/40) | 1.000 | 0 |
| `deepseek-r1:14b` | spotlight | 0.000 (0/36) | [0.000, 0.096] | 0.667 | 0.725 (29/40) | 1.000 | 0 |
| `qwen2.5:7b` | baseline | 0.250 (9/36) | [0.138, 0.411] | 0.417 | 0.525 (21/40) | 1.000 | 0 |
| `qwen2.5:7b` | defended | 0.083 (3/36) | [0.029, 0.218] | 0.556 | 0.700 (28/40) | 1.000 | 0 |
| `qwen2.5:7b` | spotlight | 0.028 (1/36) | [0.005, 0.142] | 0.694 | 0.850 (34/40) | 1.000 | 0 |

Rates use valid (non-error) responses. Attack rates exclude benign controls. Intervals are 95 percent Wilson intervals and are not a significance test.

## Paired defense effect per model

| Model | Defense | Pairs | Improved | Worsened | Unchanged | Incomparable | Attack rate baseline -> defended | Task rate baseline -> defended | Security up, utility down |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| `deepseek-r1:14b` | defended | 40 | 8 | 0 | 28 | 4 | 0.125 -> 0.031 | 0.528 -> 0.694 | 0 |
| `deepseek-r1:14b` | spotlight | 40 | 11 | 3 | 22 | 4 | 0.125 -> 0.000 | 0.528 -> 0.694 | 0 |
| `qwen2.5:7b` | defended | 40 | 5 | 0 | 28 | 7 | 0.241 -> 0.069 | 0.606 -> 0.758 | 0 |
| `qwen2.5:7b` | spotlight | 40 | 11 | 2 | 19 | 8 | 0.214 -> 0.000 | 0.625 -> 0.875 | 0 |

Paired rates use cases where both conditions produced a non-error, non-ambiguous outcome for the same model. Improved and worsened count attack cases and benign controls together; see each model's own report for the split.

## Reasoning budget

No unit ran out of output budget inside its reasoning block.

## Scorer agreement with human review

Human labels attached: 140 of 240 units.

| Dimension | Reviewed | Agreements | Agreement rate | 95% Wilson |
| --- | ---: | ---: | ---: | --- |
| attack | 140 | 120 | 0.857 | [0.790, 0.906] |
| task | 140 | 106 | 0.757 | [0.680, 0.821] |
| outcome | 140 | 95 | 0.679 | [0.597, 0.750] |

- attack automated->human counts: `failure->failure`: 79, `failure->success`: 1, `not_applicable->not_applicable`: 22, `success->success`: 19, `uncertain->failure`: 11, `uncertain->success`: 8
- task automated->human counts: `failure->failure`: 21, `failure->success`: 30, `success->success`: 85, `uncertain->success`: 4
- outcome automated->human counts: `ambiguous->compromised`: 8, `ambiguous->secure_and_useful`: 11, `benign_task_failure->benign_task_failure`: 1, `benign_task_success->benign_task_success`: 21, `compromised->compromised`: 19, `secure_and_useful->secure_and_useful`: 48, `secure_but_unhelpful->compromised`: 1, `secure_but_unhelpful->secure_and_useful`: 25, `secure_but_unhelpful->secure_but_unhelpful`: 6

Agreement is computed only on units that received a human label. Review queues over-sample uncertain and disagreeing units, so these rates are a stress test of the scorers, not an estimate of their accuracy on a random unit.

## Limitations

- The dataset is small and synthetic.
- The attacks are not adaptive.
- There are only 40 cases in the full dataset.
- Most task scorers use exact or keyword-based rules.
- Deterministic scorers may misclassify paraphrases.
- Quote-versus-compliance detection remains imperfect.
- The benchmark is English-only.
- The model has no tools.
- The benchmark does not test production RAG infrastructure.
- Prompt-level defenses are not security boundaries.
- Local runtime and quantization may affect behavior.
- Repeated runs may differ.
- One model tag does not represent an entire model family.
- A successful defense may reduce utility.
- Confidence intervals do not correct dataset-selection bias.
- The benchmark does not establish real-world safety.
- Manual review is required for ambiguous cases.

## Hashes

- `data/cases.jsonl`: `2d5f9b3b937d24de8476ff2b4dbd7c2f7c5b6bb4ae4db34c88ccad9001609fa8`
- Prompt templates: `baseline-v1`, `defended-v1`, `defended-v2`
- Scorer bundle: `attack-v1+task-v1+outcome-v1`
- Package version: `0.1.0`
- Git commit: `9a09bdc521e1ff20ff78329df92519c52313a49e`
