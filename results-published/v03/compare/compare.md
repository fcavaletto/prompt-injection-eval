# Cross-run comparison

> These rows are empirical results for the recorded model identifier, runtime, prompt templates, sampling configuration, and dataset hash. They do not generalize to every version or quantization of the model.

Sources: `gpt-oss-20b`, `qwen3-14b`, `qwen3-4b`, `deepseek-r1-14b`

Models: `deepseek-r1:14b`, `mlx-community/Qwen3-14B-4bit`, `mlx-community/Qwen3-4B-Instruct-2507-4bit`, `mlx-community/gpt-oss-20b-MXFP4-Q4`. Units: 1260. Dataset SHA-256: 8b79034bb6549532b47a4f9fd00d1eafc554f261c8b637d9754f26b51c6d15e6.

## Attack success by model and condition

| Model | Condition | Attack success | 95% Wilson | Secure and useful | Task success | Benign task success | Errors |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| `deepseek-r1:14b` | baseline | 0.202 (18/89) | [0.132, 0.297] | 0.494 | 0.610 (64/105) | 0.750 | 0 |
| `deepseek-r1:14b` | defended | 0.079 (7/89) | [0.039, 0.154] | 0.697 | 0.762 (80/105) | 0.812 | 0 |
| `deepseek-r1:14b` | spotlight | 0.000 (0/89) | [0.000, 0.041] | 0.798 | 0.819 (86/105) | 0.875 | 0 |
| `mlx-community/Qwen3-14B-4bit` | baseline | 0.292 (26/89) | [0.208, 0.394] | 0.506 | 0.686 (72/105) | 1.000 | 0 |
| `mlx-community/Qwen3-14B-4bit` | defended | 0.079 (7/89) | [0.039, 0.154] | 0.809 | 0.876 (92/105) | 1.000 | 0 |
| `mlx-community/Qwen3-14B-4bit` | spotlight | 0.022 (2/89) | [0.006, 0.078] | 0.798 | 0.876 (92/105) | 1.000 | 0 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline | 0.270 (24/89) | [0.188, 0.370] | 0.528 | 0.695 (73/105) | 1.000 | 0 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | defended | 0.135 (12/89) | [0.079, 0.221] | 0.730 | 0.848 (89/105) | 0.938 | 0 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | spotlight | 0.022 (2/89) | [0.006, 0.078] | 0.831 | 0.876 (92/105) | 1.000 | 0 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline | 0.393 (35/89) | [0.298, 0.497] | 0.371 | 0.505 (53/105) | 0.938 | 0 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | defended | 0.034 (3/89) | [0.012, 0.094] | 0.730 | 0.800 (84/105) | 1.000 | 0 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | spotlight | 0.045 (4/89) | [0.018, 0.110] | 0.775 | 0.848 (89/105) | 1.000 | 0 |

Rates use valid (non-error) responses. Attack rates exclude benign controls. Intervals are 95 percent Wilson intervals and are not a significance test.

## Paired defense effect per model

| Model | Defense | Pairs | Improved | Worsened | Unchanged | Incomparable | Attack rate baseline -> defended | Task rate baseline -> defended | Security up, utility down |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| `deepseek-r1:14b` | defended | 105 | 19 | 1 | 78 | 7 | 0.183 -> 0.073 | 0.622 -> 0.765 | 0 |
| `deepseek-r1:14b` | spotlight | 105 | 29 | 3 | 67 | 6 | 0.193 -> 0.000 | 0.616 -> 0.808 | 0 |
| `mlx-community/Qwen3-14B-4bit` | defended | 105 | 21 | 1 | 74 | 9 | 0.300 -> 0.087 | 0.698 -> 0.865 | 0 |
| `mlx-community/Qwen3-14B-4bit` | spotlight | 105 | 23 | 2 | 70 | 10 | 0.291 -> 0.025 | 0.705 -> 0.863 | 0 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | defended | 105 | 16 | 1 | 78 | 10 | 0.266 -> 0.127 | 0.726 -> 0.853 | 0 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | spotlight | 105 | 25 | 0 | 70 | 10 | 0.278 -> 0.025 | 0.726 -> 0.905 | 0 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | defended | 105 | 39 | 2 | 57 | 7 | 0.390 -> 0.037 | 0.531 -> 0.806 | 1 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | spotlight | 105 | 43 | 2 | 52 | 8 | 0.383 -> 0.049 | 0.536 -> 0.887 | 0 |

Paired rates use cases where both conditions produced a non-error, non-ambiguous outcome for the same model. Improved and worsened count attack cases and benign controls together; see each model's own report for the split.

## Reasoning budget

3 units ended inside the reasoning block and were scored as failures on both dimensions:

- `mlx-community/gpt-oss-20b-MXFP4-Q4` / baseline: 1 of 105
- `mlx-community/gpt-oss-20b-MXFP4-Q4` / defended: 1 of 105
- `mlx-community/gpt-oss-20b-MXFP4-Q4` / spotlight: 1 of 105

## Scorer agreement with human review

No human labels are attached to this analysis. Pass a completed review CSV with `--reviews` to measure how often the deterministic scorers agree with a person.

## Limitations

- The dataset is small and synthetic.
- The attacks are not adaptive.
- The case files are small: 40 cases in data/cases.jsonl and 105 in data/cases_v2.jsonl.
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

- `data/cases_v2.jsonl`: `8b79034bb6549532b47a4f9fd00d1eafc554f261c8b637d9754f26b51c6d15e6`
- Prompt templates: `baseline-v1`, `defended-v1`, `defended-v2`
- Scorer bundle: `attack-v2+task-v2+outcome-v1`
- Package version: `0.3.0`
- Git commit: `f8058ebe5081e625663fb8a1e54c1c0b3b8f6004`
