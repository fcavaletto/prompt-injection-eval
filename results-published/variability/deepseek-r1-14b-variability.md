# Repeated-run variability

> These rows are empirical results for the recorded model identifier, runtime, prompt templates, sampling configuration, and dataset hash. They do not generalize to every version or quantization of the model.

Sources: `deepseek-r1-14b-smoke`, `deepseek-r1-14b-smoke-r2`, `deepseek-r1-14b-smoke-r3`

- Runs compared: 3
- Units present in every run: 12
- Units missing from at least one run: 0
- Units with byte-identical response text across runs: 12 (1.000)
- Units whose outcome changed: 0 (0.000)
- Units whose attack score changed: 0
- Units whose task score changed: 0

Variability is measured on the final labels and on byte-identical response text across repeats with the same configuration. It answers whether a fixed seed made this local runtime deterministic. It is not a confidence interval.
