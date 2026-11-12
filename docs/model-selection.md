# Model selection

## Why open-weight models, run locally

The harness is meant to run on a laptop without a paid API or an API key. Open-weight models served by a local runtime make the experiment inspectable: the prompt, the weights, and the runtime are all recorded with the result. Local execution reduces cost. It does not by itself provide privacy or security, and the documents here are synthetic for that reason.

## The machine

An Apple M4 MacBook Air with 24 GB of unified memory, 10 CPU cores, and about 30 GB of free disk at the time of the 0.3.0 runs. On Apple Silicon the GPU shares that memory, and the operating system lets the GPU use roughly three quarters of it (Ollama reported 17.8 GiB available). A 4-bit model needs a little over half a gigabyte per billion parameters, plus room for the attention cache. That puts dense models up to about 14B comfortably in range, a 20B mixture-of-experts model in range with care, and anything around 30B dense out of range.

## What was run in 0.3.0, and why

| Model | Runtime and weights | Parameters | Why it is in the study |
| --- | --- | --- | --- |
| `gpt-oss-20b` | MLX, `mlx-community/gpt-oss-20b-MXFP4-Q4`, snapshot `f356f274` | 21B total, about 3.6B active per token (mixture of experts) | The most capable model that fits. Peak memory measured during generation: 11.4 GB. |
| `Qwen3-14B` | MLX, `mlx-community/Qwen3-14B-4bit`, snapshot `a4d9b2df` | 14.8B dense | The largest dense instruct model on the machine. Run with thinking off so it answers directly. |
| `Qwen3-4B-Instruct-2507` | MLX, `mlx-community/Qwen3-4B-Instruct-2507-4bit`, snapshot `50d42775` | 4.0B dense | The size control. Same family and runtime as Qwen3-14B, no thinking block in either, so 4B against 14B differs mainly in size (and in the 2507 instruct tuning, which is newer). |
| `deepseek-r1:14b` | Ollama 0.34.4, Q4_K_M | 14.8B dense (a Qwen2.5 distill of DeepSeek-R1) | The reasoning-model comparison, and continuity with the 0.2.0 study. It writes a visible `<think>` block before every answer. |

All four were already on disk. Nothing was downloaded for the 0.3.0 runs.

The parameter counts above are from each model's own configuration and published model card. A parameter count does not determine injection robustness, and four models cannot show a size trend. The study can show whether these four differ on these cases.

### Settings that are part of each model's condition

- **gpt-oss-20b**: Harmony chat format, `reasoning_effort=low`, 4096-token budget. Only the `final` channel is scored. Low effort is used because greedy decoding at the default medium effort loops; see [methodology](methodology.md#why-gpt-oss-runs-with-low-reasoning-effort).
- **Qwen3-14B**: `enable_thinking=False` in the chat template, 256-token budget. Qwen3-14B is a hybrid model that thinks by default. With thinking on it would be a second reasoning model, and at about 15 tokens per second on this machine the full grid would take many hours.
- **Qwen3-4B-Instruct-2507**: default template (this model has no thinking mode), 256 tokens.
- **deepseek-r1:14b**: thinking on (the model default), 4096 tokens, `num_ctx` 8192.

## What was considered and not run

- **`qwen2.5:7b`, `llama3.1:8b`, `llama3.2:3b` (Ollama), `Meta-Llama-3.1-8B-Instruct-4bit` (MLX).** Installed, but older and smaller than the models above. `qwen2.5:7b` stays in the 0.2.0 results. A pilot of `llama3.2:3b` on the new cases was run to check the harness before the study and is not a result.
- **`gemma4:12b` and `qwen3.5:9b` (Ollama library).** A pull of `gemma4:12b` was started and then abandoned, and its incomplete download was deleted. Both are smaller than the models that were already on disk, and disk space was tight.
- **Anything near 30B dense** (`qwen3.6:27b`, `gemma4:31b` at 4 bits are 17 to 20 GB). They would not leave room for the attention cache and the operating system in 24 GB.
- **Qwen3-14B with thinking on.** Feasible but slow. It would be the cleanest test of whether reasoning changes injection behavior within one set of weights, and is the most useful next run.

## Why two runtimes

Ollama serves GGUF files over a local HTTP API and is what the 0.2.0 study used. The stronger weights on this machine are MLX safetensors snapshots, which Ollama does not load. The MLX provider (`--provider mlx`) loads them in-process with `mlx-lm`. It is an optional install (`pip install -e ".[mlx]"`), imported only when used.

Runtime is therefore one more thing that differs between DeepSeek and the other three models. A difference between `deepseek-r1:14b` and `Qwen3-14B` mixes the effect of the weights, the reasoning style, the quantization format, and the runtime. The two Qwen3 models share a runtime and quantization format, which is why that is the cleanest contrast in the study.

## What can change the result

Treat each of these as part of the condition, not as a footnote:

- model identifier, snapshot, and tag
- quantization
- runtime and its version (Ollama 0.34.4, mlx 0.32.4 with mlx-lm 0.32.2)
- chat template settings (`reasoning_effort`, `enable_thinking`)
- prompt-template version (`baseline-v1`, `defended-v1`, `defended-v2`)
- temperature, seed, maximum output tokens, and context window
- dataset SHA-256

## Hardware defaults

The defaults assume a fanless laptop: sequential requests, concurrency fixed at 1, 256 output tokens unless `--profile reasoning` is set, and a configurable timeout. One model is resident at a time. The study script unloads DeepSeek from Ollama after each step so an MLX model does not share memory with it. The full 105-case file under three conditions is 315 generations per model. The harness never starts that run by itself; run the six-case smoke file first.
