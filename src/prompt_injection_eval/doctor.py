"""Environment checks for the local evaluation workflow."""

from __future__ import annotations

import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from prompt_injection_eval.dataset import validate_dataset
from prompt_injection_eval.privacy import display_path
from prompt_injection_eval.providers.ollama import OllamaProvider


def run_doctor(
    *,
    provider: str,
    model: str,
    dataset: Path,
    output_dir: Path,
    base_url: str,
) -> tuple[bool, list[str]]:
    messages: list[str] = []
    ok = True

    if sys.version_info < (3, 11):  # noqa: UP036 - doctor still reports an unpacked older interpreter
        ok = False
        messages.append(f"Python {sys.version.split()[0]} is below the required 3.11.")
    else:
        messages.append(f"Python {sys.version.split()[0]} meets the 3.11+ requirement.")

    try:
        installed = version("prompt-injection-eval")
        messages.append(f"Package prompt-injection-eval {installed} is installed.")
    except PackageNotFoundError:
        ok = False
        messages.append(
            "Package prompt-injection-eval is not installed. "
            'Install it with `python -m pip install -e ".[dev]"`.'
        )

    if not dataset.is_file():
        ok = False
        messages.append(f"Dataset file was not found: {dataset.name}.")
        messages.append("Expected data/cases.jsonl when commands are run from the repository root.")
    else:
        _cases, result = validate_dataset(dataset)
        if result.valid:
            messages.append(
                f"Dataset valid: {result.path} ({result.cases} cases, SHA-256 {result.sha256})."
            )
        else:
            ok = False
            messages.append(f"Dataset validation failed for {result.path}.")
            messages.extend(result.errors)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".doctor-", delete=True):
            pass
        messages.append(f"Output directory is writable: {display_path(output_dir)}.")
    except OSError:
        ok = False
        messages.append("Output directory is not writable.")

    if provider == "mock":
        messages.append("Provider mock is configured. Ollama is not required.")
    elif provider == "ollama":
        messages.append(f"Provider ollama is configured for model {model} at {base_url}.")
        client_provider = OllamaProvider(base_url=base_url)
        try:
            issues = client_provider.health(model)
        finally:
            client_provider.close()
        if issues:
            ok = False
            messages.extend(issues)
        else:
            messages.append(f"Ollama is reachable and model {model} is installed.")
    else:
        ok = False
        messages.append(f"Unknown provider: {provider}. Use mock or ollama.")

    if ok:
        messages.append("Doctor checks passed.")
    return ok, messages
