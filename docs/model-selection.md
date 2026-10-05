# Model selection

## Why open-weight models

The harness is meant to run on a laptop without a paid API or an API key. Open-weight instruct models served by a local runtime make the experiment inspectable: the prompt, the tag, and the runtime are all recorded with the result.

Local execution reduces monetary cost. It does not by itself provide complete privacy or security. The documents in this repository are synthetic. Do not substitute confidential files.

## Which tags the published study used

The published comparison is `deepseek-r1:14b` (Q4_K_M, thinking on, `--profile reasoning`) and `qwen2.5:7b` (Q4_K_M, no thinking, the default 256-token budget). Both fit a MacBook Air with an M4 chip and 20 GB of unified memory if only one is resident. The CLI default tag is `qwen2.5:7b`, the smaller of those two, so `pie doctor` and `pie run` without `--model` point at a tag the study actually ran. That name is a configuration default. It is not hard-coded into the scorer or the runner. Passing `--model` selects a different Ollama tag. `deepseek-r1:14b` still needs `--profile reasoning`.

This repository does not claim that any of these tags is safer or faster than any other model. Model size alone does not determine injection robustness. The results page is about the two tags that were actually run.

## Why the weights stay outside Python

The default install does not include PyTorch, MLX, or another large ML framework. `OllamaProvider` calls Ollama's local HTTP API with `httpx`. The model is not loaded into the Python process, and the harness does not download models on its own.

Optional models are documented only. Nothing in `pie doctor` or `pie run` pulls them. Examples that may be compared later, after a person chooses to pull them, include `qwen3:8b`, SmolLM3-3B, and other small instruct tags available through Ollama. Different tags and quantizations are different experimental conditions.

## Why Ollama is the only provider for now

One reliable backend is more useful than several unfinished ones. Ollama is already a local HTTP service, it does not require CUDA, and it does not require Docker for the primary workflow.

An MLX provider is a reasonable later addition on Apple Silicon. It is not implemented.

## What can change the result

Treat each of these as part of the condition, not as a footnote:

- model identifier and tag
- quantization
- Ollama version and runner
- prompt-template version (`baseline-v1`, `defended-v1`, `defended-v2`)
- temperature, seed, maximum output tokens, and keep-alive
- dataset SHA-256

A fixed seed is forwarded to Ollama when `--seed` is set. Not every Ollama build or model honors it. Repeated runs can still differ. Results from one tag do not represent an entire model family.

## Hardware defaults

The defaults assume a fanless laptop:

- sequential requests
- concurrency fixed at 1
- maximum generated length 256 tokens
- short documents
- configurable timeout
- configurable keep-alive, default `5m`, so the model is not reloaded between the two conditions of a small run

The full dataset is 40 cases and two conditions: up to 80 generations. The harness never starts that run by itself. Run the six-case smoke file first.
