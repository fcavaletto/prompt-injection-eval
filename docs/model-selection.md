# Model selection

## Why open-weight models

The harness is meant to run on a laptop without a paid API or an API key. Open-weight instruct models served by a local runtime make the experiment inspectable: the prompt, the tag, and the runtime are all recorded with the result.

Local execution reduces monetary cost. It does not by itself provide complete privacy or security. The documents in this repository are synthetic. Do not substitute confidential files.

## Why the default model is `qwen3:4b`

`qwen3:4b` is the default starting tag because a 4B-class instruct model is a realistic fit for an Apple MacBook Air with an M4 chip and 20 GB of unified memory. The name is a configuration default. It is not hard-coded into the scorer or the runner. Passing `--model` selects a different Ollama tag.

This repository does not claim that `qwen3:4b` is safer or faster than any other model. Model size alone does not determine injection robustness.

## Why the weights stay outside Python

The default install does not include PyTorch, MLX, or another large ML framework. `OllamaProvider` calls Ollama's local HTTP API with `httpx`. The model is not loaded into the Python process, and the harness does not download models on its own.

Optional models are documented only. Nothing in `pie doctor` or `pie run` pulls them. Examples that may be compared later, after a person chooses to pull them, include `qwen3:8b`, SmolLM3-3B, and other small instruct tags available through Ollama. Different tags and quantizations are different experimental conditions.

## Why Ollama is the only provider for now

One reliable backend is more useful than several unfinished ones. Ollama is already a local HTTP service, it does not require CUDA, and it does not require Docker for the primary workflow.

An MLX provider is a reasonable later addition on Apple Silicon. It is not implemented in version 0.1.0.

## What can change the result

Treat each of these as part of the condition, not as a footnote:

- model identifier and tag
- quantization
- Ollama version and runner
- prompt-template version (`baseline-v1`, `defended-v1`)
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
