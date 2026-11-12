# Paired statistics

Sources: `gpt-oss-20b`, `qwen3-14b`, `qwen3-4b`, `deepseek-r1-14b`

Each row pairs the same case under two conditions (or two models). `b` counts cases where only the first side succeeded, `c` where only the second did. McNemar's exact test uses only those discordant pairs. The difference is second minus first, with a 95% percentile bootstrap interval from 10,000 resamples of cases (seed 20261104). Holm-adjusted p-values control the chance of any false positive within each family of tests listed in the `family_size` column of the CSV.

With alpha 0.05, a McNemar test needs at least 6 discordant pairs, all in the same direction, before it can reject. Fewer than that cannot reach p <= 0.05 whatever the split.

## Conditions against each other, within each model

| Model | Contrast | Field | Uncertain counted as | Pairs | First | Second | b | c | p | Holm p | Difference [95% bootstrap] |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `deepseek-r1:14b` | baseline vs defended | attack_score | not success | 89 | 18 | 7 | 11 | 0 | <0.001 | 0.005 | -0.124 [-0.191, -0.056] |
| `deepseek-r1:14b` | baseline vs defended | attack_score | success | 89 | 21 | 10 | 12 | 1 | 0.003 | 0.014 | -0.124 [-0.202, -0.056] |
| `deepseek-r1:14b` | baseline vs defended | task_score | not success | 105 | 64 | 80 | 1 | 17 | <0.001 | <0.001 | +0.152 [+0.086, +0.229] |
| `deepseek-r1:14b` | baseline vs spotlight | attack_score | not success | 89 | 18 | 0 | 18 | 0 | <0.001 | <0.001 | -0.202 [-0.292, -0.124] |
| `deepseek-r1:14b` | baseline vs spotlight | attack_score | success | 89 | 21 | 1 | 21 | 1 | <0.001 | <0.001 | -0.225 [-0.315, -0.135] |
| `deepseek-r1:14b` | baseline vs spotlight | task_score | not success | 105 | 64 | 86 | 3 | 25 | <0.001 | <0.001 | +0.210 [+0.124, +0.295] |
| `deepseek-r1:14b` | defended vs spotlight | attack_score | not success | 89 | 7 | 0 | 7 | 0 | 0.016 | 0.047 | -0.079 [-0.135, -0.022] |
| `deepseek-r1:14b` | defended vs spotlight | attack_score | success | 89 | 10 | 1 | 9 | 0 | 0.004 | 0.014 | -0.101 [-0.169, -0.045] |
| `deepseek-r1:14b` | defended vs spotlight | task_score | not success | 105 | 80 | 86 | 4 | 10 | 0.180 | 0.718 | +0.057 [-0.010, +0.124] |
| `mlx-community/Qwen3-14B-4bit` | baseline vs defended | attack_score | not success | 89 | 26 | 7 | 19 | 0 | <0.001 | <0.001 | -0.213 [-0.303, -0.135] |
| `mlx-community/Qwen3-14B-4bit` | baseline vs defended | attack_score | success | 89 | 33 | 8 | 25 | 0 | <0.001 | <0.001 | -0.281 [-0.382, -0.191] |
| `mlx-community/Qwen3-14B-4bit` | baseline vs defended | task_score | not success | 105 | 72 | 92 | 1 | 21 | <0.001 | <0.001 | +0.190 [+0.114, +0.276] |
| `mlx-community/Qwen3-14B-4bit` | baseline vs spotlight | attack_score | not success | 89 | 26 | 2 | 24 | 0 | <0.001 | <0.001 | -0.270 [-0.360, -0.180] |
| `mlx-community/Qwen3-14B-4bit` | baseline vs spotlight | attack_score | success | 89 | 33 | 5 | 28 | 0 | <0.001 | <0.001 | -0.315 [-0.416, -0.225] |
| `mlx-community/Qwen3-14B-4bit` | baseline vs spotlight | task_score | not success | 105 | 72 | 92 | 2 | 22 | <0.001 | <0.001 | +0.190 [+0.105, +0.276] |
| `mlx-community/Qwen3-14B-4bit` | defended vs spotlight | attack_score | not success | 89 | 7 | 2 | 6 | 1 | 0.125 | 0.250 | -0.056 [-0.112, +0.000] |
| `mlx-community/Qwen3-14B-4bit` | defended vs spotlight | attack_score | success | 89 | 8 | 5 | 7 | 4 | 0.549 | 1.000 | -0.034 [-0.112, +0.034] |
| `mlx-community/Qwen3-14B-4bit` | defended vs spotlight | task_score | not success | 105 | 92 | 92 | 5 | 5 | 1.000 | 1.000 | +0.000 [-0.057, +0.057] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline vs defended | attack_score | not success | 89 | 24 | 12 | 12 | 0 | <0.001 | 0.003 | -0.135 [-0.213, -0.067] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline vs defended | attack_score | success | 89 | 31 | 16 | 15 | 0 | <0.001 | <0.001 | -0.169 [-0.247, -0.090] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline vs defended | task_score | not success | 105 | 73 | 89 | 1 | 17 | <0.001 | <0.001 | +0.152 [+0.086, +0.229] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline vs spotlight | attack_score | not success | 89 | 24 | 2 | 22 | 0 | <0.001 | <0.001 | -0.247 [-0.337, -0.157] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline vs spotlight | attack_score | success | 89 | 31 | 4 | 28 | 1 | <0.001 | <0.001 | -0.303 [-0.404, -0.202] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline vs spotlight | task_score | not success | 105 | 73 | 92 | 1 | 20 | <0.001 | <0.001 | +0.181 [+0.105, +0.257] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | defended vs spotlight | attack_score | not success | 89 | 12 | 2 | 10 | 0 | 0.002 | 0.008 | -0.112 [-0.180, -0.056] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | defended vs spotlight | attack_score | success | 89 | 16 | 4 | 13 | 1 | 0.002 | 0.009 | -0.135 [-0.213, -0.056] |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | defended vs spotlight | task_score | not success | 105 | 89 | 92 | 5 | 8 | 0.581 | 1.000 | +0.029 [-0.038, +0.095] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline vs defended | attack_score | not success | 89 | 35 | 3 | 32 | 0 | <0.001 | <0.001 | -0.360 [-0.461, -0.258] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline vs defended | attack_score | success | 89 | 39 | 6 | 33 | 0 | <0.001 | <0.001 | -0.371 [-0.472, -0.270] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline vs defended | task_score | not success | 105 | 53 | 84 | 3 | 34 | <0.001 | <0.001 | +0.295 [+0.200, +0.390] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline vs spotlight | attack_score | not success | 89 | 35 | 4 | 33 | 2 | <0.001 | <0.001 | -0.348 [-0.461, -0.236] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline vs spotlight | attack_score | success | 89 | 39 | 9 | 32 | 2 | <0.001 | <0.001 | -0.337 [-0.449, -0.236] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline vs spotlight | task_score | not success | 105 | 53 | 89 | 1 | 37 | <0.001 | <0.001 | +0.343 [+0.248, +0.438] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | defended vs spotlight | attack_score | not success | 89 | 3 | 4 | 2 | 3 | 1.000 | 1.000 | +0.011 [-0.034, +0.056] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | defended vs spotlight | attack_score | success | 89 | 6 | 9 | 3 | 6 | 0.508 | 1.000 | +0.034 [-0.034, +0.101] |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | defended vs spotlight | task_score | not success | 105 | 84 | 89 | 7 | 12 | 0.359 | 1.000 | +0.048 [-0.029, +0.124] |

## Models against each other, attack success on the same cases

| Condition | First model | Second model | Pairs | First | Second | b | c | p | Holm p | Difference [95% bootstrap] |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | `deepseek-r1:14b` | `mlx-community/Qwen3-14B-4bit` | 89 | 18 | 26 | 1 | 9 | 0.021 | 0.107 | +0.090 [+0.022, +0.157] |
| baseline | `deepseek-r1:14b` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 89 | 18 | 24 | 2 | 8 | 0.109 | 0.219 | +0.067 [+0.000, +0.135] |
| baseline | `deepseek-r1:14b` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 18 | 35 | 4 | 21 | <0.001 | 0.005 | +0.191 [+0.090, +0.292] |
| baseline | `mlx-community/Qwen3-14B-4bit` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 89 | 26 | 24 | 5 | 3 | 0.727 | 0.727 | -0.022 [-0.090, +0.034] |
| baseline | `mlx-community/Qwen3-14B-4bit` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 26 | 35 | 4 | 13 | 0.049 | 0.147 | +0.101 [+0.011, +0.191] |
| baseline | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 24 | 35 | 6 | 17 | 0.035 | 0.139 | +0.124 [+0.022, +0.225] |
| defended | `deepseek-r1:14b` | `mlx-community/Qwen3-14B-4bit` | 89 | 7 | 7 | 3 | 3 | 1.000 | 1.000 | +0.000 [-0.056, +0.056] |
| defended | `deepseek-r1:14b` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 89 | 7 | 12 | 0 | 5 | 0.062 | 0.312 | +0.056 [+0.011, +0.112] |
| defended | `deepseek-r1:14b` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 7 | 3 | 5 | 1 | 0.219 | 0.656 | -0.045 [-0.101, +0.000] |
| defended | `mlx-community/Qwen3-14B-4bit` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 89 | 7 | 12 | 1 | 6 | 0.125 | 0.500 | +0.056 [+0.000, +0.112] |
| defended | `mlx-community/Qwen3-14B-4bit` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 7 | 3 | 5 | 1 | 0.219 | 0.656 | -0.045 [-0.101, +0.011] |
| defended | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 12 | 3 | 10 | 1 | 0.012 | 0.070 | -0.101 [-0.169, -0.034] |
| spotlight | `deepseek-r1:14b` | `mlx-community/Qwen3-14B-4bit` | 89 | 0 | 2 | 0 | 2 | 0.500 | 1.000 | +0.022 [+0.000, +0.056] |
| spotlight | `deepseek-r1:14b` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 89 | 0 | 2 | 0 | 2 | 0.500 | 1.000 | +0.022 [+0.000, +0.056] |
| spotlight | `deepseek-r1:14b` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 0 | 4 | 0 | 4 | 0.125 | 0.750 | +0.045 [+0.011, +0.090] |
| spotlight | `mlx-community/Qwen3-14B-4bit` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | 89 | 2 | 2 | 1 | 1 | 1.000 | 1.000 | +0.000 [-0.034, +0.034] |
| spotlight | `mlx-community/Qwen3-14B-4bit` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 2 | 4 | 1 | 3 | 0.625 | 1.000 | +0.022 [-0.022, +0.067] |
| spotlight | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | `mlx-community/gpt-oss-20b-MXFP4-Q4` | 89 | 2 | 4 | 1 | 3 | 0.625 | 1.000 | +0.022 [-0.022, +0.067] |

## Power with 89 attack pairs

Chance that an exact McNemar test at alpha 0.05 rejects, if the defense removes the stated share of attack successes and newly causes successes on `p_c` of cases.

| Reduction | p_c | Power |
| ---: | ---: | ---: |
| 0.03 | 0.00 | 0.05 |
| 0.03 | 0.02 | 0.08 |
| 0.05 | 0.00 | 0.29 |
| 0.05 | 0.02 | 0.22 |
| 0.10 | 0.00 | 0.89 |
| 0.10 | 0.02 | 0.67 |
| 0.15 | 0.00 | 0.99 |
| 0.15 | 0.02 | 0.92 |
| 0.20 | 0.00 | 1.00 |
| 0.20 | 0.02 | 0.99 |
| 0.30 | 0.00 | 1.00 |
| 0.30 | 0.02 | 1.00 |

Wilson intervals at this denominator:

| Count | Interval |
| --- | --- |
| 0/89 | [0.000, 0.041] |
| 4/89 | [0.018, 0.110] |
| 9/89 | [0.054, 0.181] |
| 22/89 | [0.169, 0.346] |
| 44/89 | [0.393, 0.596] |

## Secondary readings

Lenient task reading `lenient-v1` and the tool-call text proxy. Neither replaces the strict headline.

| Model | Condition | Valid | Strict task | Lenient task | Tool cases | Tool attack success | Tool uncertain | Naive parser fired |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `deepseek-r1:14b` | baseline | 105 | 64 | 76 | 8 | 2 | 0 | 2 |
| `deepseek-r1:14b` | defended | 105 | 80 | 90 | 8 | 1 | 0 | 1 |
| `deepseek-r1:14b` | spotlight | 105 | 86 | 95 | 8 | 0 | 0 | 0 |
| `mlx-community/Qwen3-14B-4bit` | baseline | 105 | 72 | 82 | 8 | 2 | 0 | 2 |
| `mlx-community/Qwen3-14B-4bit` | defended | 105 | 92 | 96 | 8 | 1 | 0 | 1 |
| `mlx-community/Qwen3-14B-4bit` | spotlight | 105 | 92 | 96 | 8 | 0 | 0 | 0 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | baseline | 105 | 73 | 84 | 8 | 3 | 0 | 3 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | defended | 105 | 89 | 94 | 8 | 1 | 0 | 1 |
| `mlx-community/Qwen3-4B-Instruct-2507-4bit` | spotlight | 105 | 92 | 94 | 8 | 0 | 0 | 0 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | baseline | 105 | 53 | 64 | 8 | 4 | 0 | 4 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | defended | 105 | 84 | 92 | 8 | 2 | 0 | 2 |
| `mlx-community/gpt-oss-20b-MXFP4-Q4` | spotlight | 105 | 89 | 92 | 8 | 2 | 0 | 2 |
