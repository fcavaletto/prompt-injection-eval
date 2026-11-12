# Paired statistics

Sources: `deepseek-r1-14b`, `qwen2.5-7b`

Each row pairs the same case under two conditions (or two models). `b` counts cases where only the first side succeeded, `c` where only the second did. McNemar's exact test uses only those discordant pairs. The difference is second minus first, with a 95% percentile bootstrap interval from 10,000 resamples of cases (seed 20261104). Holm-adjusted p-values control the chance of any false positive within each family of tests listed in the `family_size` column of the CSV.

With alpha 0.05, a McNemar test needs at least 6 discordant pairs, all in the same direction, before it can reject. Fewer than that cannot reach p <= 0.05 whatever the split.

## Conditions against each other, within each model

| Model | Contrast | Field | Uncertain counted as | Pairs | First | Second | b | c | p | Holm p | Difference [95% bootstrap] |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `deepseek-r1:14b` | baseline vs defended | attack_score | not success | 36 | 5 | 1 | 4 | 0 | 0.125 | 0.375 | -0.111 [-0.222, -0.028] |
| `deepseek-r1:14b` | baseline vs defended | attack_score | success | 36 | 7 | 3 | 5 | 1 | 0.219 | 0.656 | -0.111 [-0.250, +0.028] |
| `deepseek-r1:14b` | baseline vs defended | task_score | not success | 40 | 21 | 28 | 0 | 7 | 0.016 | 0.078 | +0.175 [+0.075, +0.300] |
| `deepseek-r1:14b` | baseline vs spotlight | attack_score | not success | 36 | 5 | 0 | 5 | 0 | 0.062 | 0.250 | -0.139 [-0.250, -0.028] |
| `deepseek-r1:14b` | baseline vs spotlight | attack_score | success | 36 | 7 | 1 | 7 | 1 | 0.070 | 0.281 | -0.167 [-0.306, -0.028] |
| `deepseek-r1:14b` | baseline vs spotlight | task_score | not success | 40 | 21 | 29 | 3 | 11 | 0.057 | 0.172 | +0.200 [+0.025, +0.375] |
| `deepseek-r1:14b` | defended vs spotlight | attack_score | not success | 36 | 1 | 0 | 1 | 0 | 1.000 | 1.000 | -0.028 [-0.083, +0.000] |
| `deepseek-r1:14b` | defended vs spotlight | attack_score | success | 36 | 3 | 1 | 2 | 0 | 0.500 | 1.000 | -0.056 [-0.139, +0.000] |
| `deepseek-r1:14b` | defended vs spotlight | task_score | not success | 40 | 28 | 29 | 3 | 4 | 1.000 | 1.000 | +0.025 [-0.100, +0.150] |
| `qwen2.5:7b` | baseline vs defended | attack_score | not success | 36 | 9 | 3 | 6 | 0 | 0.031 | 0.156 | -0.167 [-0.306, -0.056] |
| `qwen2.5:7b` | baseline vs defended | attack_score | success | 36 | 14 | 7 | 7 | 0 | 0.016 | 0.078 | -0.194 [-0.333, -0.083] |
| `qwen2.5:7b` | baseline vs defended | task_score | not success | 40 | 21 | 28 | 1 | 8 | 0.039 | 0.156 | +0.175 [+0.050, +0.325] |
| `qwen2.5:7b` | baseline vs spotlight | attack_score | not success | 36 | 9 | 1 | 8 | 0 | 0.008 | 0.047 | -0.222 [-0.361, -0.111] |
| `qwen2.5:7b` | baseline vs spotlight | attack_score | success | 36 | 14 | 6 | 8 | 0 | 0.008 | 0.047 | -0.222 [-0.361, -0.111] |
| `qwen2.5:7b` | baseline vs spotlight | task_score | not success | 40 | 21 | 34 | 2 | 15 | 0.002 | 0.014 | +0.325 [+0.150, +0.500] |
| `qwen2.5:7b` | defended vs spotlight | attack_score | not success | 36 | 3 | 1 | 2 | 0 | 0.500 | 1.000 | -0.056 [-0.139, +0.000] |
| `qwen2.5:7b` | defended vs spotlight | attack_score | success | 36 | 7 | 6 | 3 | 2 | 1.000 | 1.000 | -0.028 [-0.139, +0.083] |
| `qwen2.5:7b` | defended vs spotlight | task_score | not success | 40 | 28 | 34 | 2 | 8 | 0.109 | 0.219 | +0.150 [+0.000, +0.300] |

## Models against each other, attack success on the same cases

| Condition | First model | Second model | Pairs | First | Second | b | c | p | Holm p | Difference [95% bootstrap] |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | `deepseek-r1:14b` | `qwen2.5:7b` | 36 | 5 | 9 | 0 | 4 | 0.125 | 0.125 | +0.111 [+0.028, +0.222] |
| defended | `deepseek-r1:14b` | `qwen2.5:7b` | 36 | 1 | 3 | 0 | 2 | 0.500 | 0.500 | +0.056 [+0.000, +0.139] |
| spotlight | `deepseek-r1:14b` | `qwen2.5:7b` | 36 | 0 | 1 | 0 | 1 | 1.000 | 1.000 | +0.028 [+0.000, +0.083] |

## Power with 36 attack pairs

Chance that an exact McNemar test at alpha 0.05 rejects, if the defense removes the stated share of attack successes and newly causes successes on `p_c` of cases.

| Reduction | p_c | Power |
| ---: | ---: | ---: |
| 0.03 | 0.00 | 0.00 |
| 0.03 | 0.02 | 0.00 |
| 0.05 | 0.00 | 0.01 |
| 0.05 | 0.02 | 0.02 |
| 0.10 | 0.00 | 0.15 |
| 0.10 | 0.02 | 0.15 |
| 0.15 | 0.00 | 0.46 |
| 0.15 | 0.02 | 0.39 |
| 0.20 | 0.00 | 0.75 |
| 0.20 | 0.02 | 0.63 |
| 0.30 | 0.00 | 0.98 |
| 0.30 | 0.02 | 0.91 |

Wilson intervals at this denominator:

| Count | Interval |
| --- | --- |
| 0/36 | [0.000, 0.096] |
| 2/36 | [0.015, 0.181] |
| 4/36 | [0.044, 0.253] |
| 9/36 | [0.138, 0.411] |
| 18/36 | [0.345, 0.655] |

## Secondary readings

Lenient task reading `lenient-v1` and the tool-call text proxy. Neither replaces the strict headline.

| Model | Condition | Valid | Strict task | Lenient task | Tool cases | Tool attack success | Tool uncertain | Naive parser fired |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `deepseek-r1:14b` | baseline | 40 | 21 | 30 | 0 | 0 | 0 | 0 |
| `deepseek-r1:14b` | defended | 40 | 28 | 36 | 0 | 0 | 0 | 0 |
| `deepseek-r1:14b` | spotlight | 40 | 29 | 37 | 0 | 0 | 0 | 0 |
| `qwen2.5:7b` | baseline | 40 | 21 | 30 | 0 | 0 | 0 | 0 |
| `qwen2.5:7b` | defended | 40 | 28 | 36 | 0 | 0 | 0 | 0 |
| `qwen2.5:7b` | spotlight | 40 | 34 | 37 | 0 | 0 | 0 | 0 |

## Lenient reading against human task labels

| Model | Reviewed | Strict agrees | Lenient agrees |
| --- | ---: | --- | --- |
| `deepseek-r1:14b` | 67 | 54 [0.696, 0.883] | 61 [0.818, 0.958] |
| `qwen2.5:7b` | 73 | 52 [0.600, 0.803] | 69 [0.867, 0.978] |

10 lenient disagreements are listed in `lenient_disagreements.csv`.
