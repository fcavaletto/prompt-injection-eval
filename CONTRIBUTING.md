# Contributing

This repository is a small research artifact. Changes should stay easy to review in one sitting.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Checks

```bash
make check
```

That runs Ruff, mypy, and pytest. Tests must pass without Ollama, model downloads, network access, API keys, or Docker.

## Dataset changes

Do not rewrite supplied cases in place to make a model look better. If a case changes, revalidate it, accept the new SHA-256, and do not reuse results recorded under the old hash. Prompt wording that can change behavior needs a new template version such as `baseline-v2`.

Keep new attacks synthetic. Do not add real credentials, local paths, exploit payloads, or instructions the harness would execute.

## Pull requests

- Explain the methodological reason for the change.
- Add tests for scoring, resume, or metric behavior you touch.
- Do not commit virtual environments, model weights, API keys, or large empirical result directories.
- Small synthetic examples belong in `examples/mock_report/` and must be labeled synthetic.

## Code of conduct

Be precise about what an experiment shows. Do not describe mock output as a model result, and do not describe a prompt template as a security boundary.
