"""MLX provider for local safetensors snapshots on Apple Silicon.

`mlx` and `mlx-lm` are optional. They are imported the first time a request is made,
so the rest of the harness works without them. Install with
``pip install -e ".[mlx]"``.

The model is referenced by Hugging Face repo id (for example
``mlx-community/Qwen3-14B-4bit``) and resolved from the local Hugging Face cache. Set
``HF_HUB_CACHE`` to the cache directory and ``HF_HUB_OFFLINE=1`` so nothing is
downloaded. A filesystem path also works, but then the path is what gets recorded as the
model name, so a repo id is preferred.

Decoding is greedy when the temperature is 0, which makes the seed irrelevant; the seed is
still passed to ``mx.random.seed`` before each request so sampled runs are repeatable.
No tools are offered and the output is never executed.

gpt-oss models answer in the Harmony format: an ``analysis`` channel (visible reasoning)
followed by a ``final`` channel. Only the ``final`` channel is the scored answer.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

from prompt_injection_eval.providers.base import GenerationRequest, GenerationResponse
from prompt_injection_eval.reasoning import split_reasoning

_HARMONY_SEGMENT = re.compile(
    r"<\|channel\|>(?P<channel>[a-z]+)(?:(?!<\|channel\|>).)*?<\|message\|>(?P<body>.*?)"
    r"(?=<\|end\|>|<\|return\|>|<\|call\|>|<\|start\|>|$)",
    re.DOTALL,
)
_SPECIAL = re.compile(r"<\|[a-z_]+\|>")


class MlxUnavailableError(RuntimeError):
    """mlx or mlx-lm is not installed in this environment."""


@dataclass(frozen=True)
class HarmonySplit:
    answer: str
    reasoning: str | None
    truncated: bool


def split_harmony(raw: str, *, finished: bool) -> HarmonySplit:
    """Split a Harmony completion into the final answer and the analysis text.

    If no ``final`` channel was written, the answer is empty. ``truncated`` is True when
    generation stopped on the token budget before reaching the final channel.
    """
    analysis: list[str] = []
    final: list[str] = []
    for match in _HARMONY_SEGMENT.finditer(raw):
        body = match.group("body").strip()
        if match.group("channel") == "final":
            final.append(body)
        else:
            analysis.append(body)
    reasoning = "\n\n".join(part for part in analysis if part) or None
    if final:
        return HarmonySplit(answer=final[-1], reasoning=reasoning, truncated=False)
    return HarmonySplit(answer="", reasoning=reasoning, truncated=not finished)


def is_harmony(raw: str) -> bool:
    return "<|channel|>" in raw


@dataclass
class BackendOutput:
    raw_text: str
    prompt_tokens: int
    generation_tokens: int
    finish_reason: str | None
    timed_out: bool = False


class MlxBackend(Protocol):
    def render(self, messages: list[dict[str, str]], template_kwargs: dict[str, Any]) -> str: ...

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        seed: int | None,
        timeout_seconds: float,
    ) -> BackendOutput: ...

    def describe(self) -> dict[str, Any]: ...


class _MlxLmBackend:
    """Thin wrapper over mlx-lm. Loaded lazily, once per process."""

    def __init__(self, model_ref: str) -> None:
        try:
            import mlx.core as mx
            from mlx_lm import load
            from mlx_lm.generate import stream_generate
            from mlx_lm.sample_utils import make_sampler
        except ImportError as exc:
            raise MlxUnavailableError(
                "The mlx provider needs the optional packages mlx and mlx-lm. "
                'Install them with `pip install -e ".[mlx]"` on Apple Silicon.'
            ) from exc
        self._mx = mx
        self._stream_generate = stream_generate
        self._make_sampler = make_sampler
        self.model_ref = model_ref
        self._model_dir = _resolve_model_dir(model_ref)
        # Load from the resolved local snapshot so a cache entry without refs/main still
        # works offline. The recorded model name stays the repo id.
        loaded = load(str(self._model_dir) if self._model_dir is not None else model_ref)
        self.model, self.tokenizer = loaded[0], loaded[1]

    def render(self, messages: list[dict[str, str]], template_kwargs: dict[str, Any]) -> str:
        rendered = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False, **template_kwargs
        )
        return str(rendered)

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        seed: int | None,
        timeout_seconds: float,
    ) -> BackendOutput:
        if seed is not None:
            self._mx.random.seed(seed)
        sampler = self._make_sampler(temp=temperature)
        tokens: list[int] = []
        started = time.perf_counter()
        last: Any = None
        timed_out = False
        for step in self._stream_generate(
            self.model, self.tokenizer, prompt, max_tokens=max_tokens, sampler=sampler
        ):
            tokens.append(int(step.token))
            last = step
            if time.perf_counter() - started > timeout_seconds:
                timed_out = True
                break
        raw = self.tokenizer.decode(tokens) if tokens else ""
        return BackendOutput(
            raw_text=str(raw),
            prompt_tokens=int(getattr(last, "prompt_tokens", 0) or 0),
            generation_tokens=len(tokens),
            finish_reason=None if timed_out else getattr(last, "finish_reason", None),
            timed_out=timed_out,
        )

    def describe(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if self._model_dir is not None:
            config_path = self._model_dir / "config.json"
            if config_path.is_file():
                config = json.loads(config_path.read_text(encoding="utf-8"))
        quant = config.get("quantization") or config.get("quantization_config") or {}
        return {
            "runtime": "mlx-lm",
            "runtime_version": _package_version("mlx-lm"),
            "mlx_version": _package_version("mlx"),
            "model_ref": self.model_ref,
            "snapshot": self._model_dir.name if self._model_dir is not None else None,
            "model_type": config.get("model_type"),
            "architectures": config.get("architectures"),
            "quantization_bits": quant.get("bits") if isinstance(quant, dict) else None,
            "quantization_group_size": quant.get("group_size") if isinstance(quant, dict) else None,
            "quantization_mode": quant.get("mode") if isinstance(quant, dict) else None,
            "num_hidden_layers": config.get("num_hidden_layers"),
            "max_position_embeddings": config.get("max_position_embeddings"),
        }


class MlxProvider:
    name = "mlx"
    result_origin = "empirical_model_run"

    def __init__(
        self,
        *,
        model: str,
        reasoning_effort: str | None = None,
        backend: MlxBackend | None = None,
    ) -> None:
        self.model_ref = model
        self.reasoning_effort = reasoning_effort
        self._backend = backend

    def _ensure(self) -> MlxBackend:
        if self._backend is None:
            self._backend = _MlxLmBackend(self.model_ref)
        return self._backend

    def close(self) -> None:
        self._backend = None

    def template_kwargs(self, think: bool | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if think is not None:
            # Qwen3 hybrid models read this flag. Templates that do not use it ignore it.
            kwargs["enable_thinking"] = bool(think)
        if self.reasoning_effort is not None:
            # gpt-oss reads this in its chat template; the template default is "medium".
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    def load(self) -> None:
        """Load the weights now. Raises if the model cannot be loaded."""
        self._ensure()

    def runtime_info(self, model: str) -> dict[str, Any]:
        info = dict(self._ensure().describe())
        info["reasoning_effort"] = self.reasoning_effort
        return info

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        started = time.perf_counter()
        try:
            backend = self._ensure()
            messages = [
                {"role": "system", "content": request.system_message},
                {"role": "user", "content": request.user_message},
            ]
            think = request.provider_settings.get("think")
            prompt = backend.render(messages, self.template_kwargs(think))
            output = backend.generate(
                prompt,
                max_tokens=request.max_output_tokens,
                temperature=request.temperature,
                seed=request.seed,
                timeout_seconds=request.timeout_seconds,
            )
        except MlxUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - one failed call must not abort the run
            return GenerationResponse(
                text=None,
                provider=self.name,
                model=request.model,
                latency_seconds=time.perf_counter() - started,
                error_type="mlx_exception",
                error_message=f"{type(exc).__name__}: {exc}",
                provider_metadata={"synthetic_mock": False},
            )
        latency = time.perf_counter() - started
        if output.timed_out:
            return GenerationResponse(
                text=None,
                raw_text=output.raw_text,
                provider=self.name,
                model=request.model,
                latency_seconds=latency,
                error_type="timeout",
                error_message=f"Generation exceeded {request.timeout_seconds} seconds.",
                provider_metadata={"synthetic_mock": False},
            )
        finished = output.finish_reason == "stop"
        if is_harmony(output.raw_text):
            harmony = split_harmony(output.raw_text, finished=finished)
            answer, reasoning, truncated = harmony.answer, harmony.reasoning, harmony.truncated
            fmt = "harmony"
        else:
            split = split_reasoning(_SPECIAL.sub("", output.raw_text))
            answer, reasoning, truncated = split.answer.strip(), split.reasoning, split.truncated
            fmt = "think_tags" if (reasoning is not None or truncated) else "plain"
        return GenerationResponse(
            text=_SPECIAL.sub("", answer).strip(),
            raw_text=output.raw_text,
            reasoning_text=reasoning,
            reasoning_truncated=truncated,
            provider=self.name,
            model=request.model,
            latency_seconds=latency,
            prompt_token_count=output.prompt_tokens,
            completion_token_count=output.generation_tokens,
            provider_metadata={
                "done_reason": output.finish_reason,
                "output_format": fmt,
                "chat_template_kwargs": self.template_kwargs(
                    request.provider_settings.get("think")
                ),
            },
        )


def _resolve_model_dir(model_ref: str) -> Path | None:
    path = Path(model_ref)
    if path.is_dir():
        return path
    try:
        from huggingface_hub import constants
    except ImportError:
        return None
    repo = Path(constants.HF_HUB_CACHE) / ("models--" + model_ref.replace("/", "--"))
    ref = repo / "refs" / "main"
    if ref.is_file():
        snapshot = repo / "snapshots" / ref.read_text(encoding="utf-8").strip()
        return snapshot if snapshot.is_dir() else None
    snapshots = sorted(path for path in (repo / "snapshots").glob("*") if path.is_dir())
    # Without a ref, only an unambiguous single snapshot is used.
    return snapshots[0] if len(snapshots) == 1 else None


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None
