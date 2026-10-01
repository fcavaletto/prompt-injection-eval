"""Provider tests. No test contacts a live Ollama server."""

import httpx

from prompt_injection_eval.providers.base import GenerationRequest
from prompt_injection_eval.providers.mock import MockProvider
from prompt_injection_eval.providers.ollama import OllamaProvider


def _request(**metadata: object) -> GenerationRequest:
    return GenerationRequest(
        model="synthetic-mock",
        system_message="system",
        user_message="user",
        temperature=0.0,
        seed=None,
        max_output_tokens=256,
        timeout_seconds=5,
        metadata=dict(metadata),
    )


def test_mock_is_deterministic_and_labeled() -> None:
    provider = MockProvider()
    request = _request(case_id="direct_override_001", condition="baseline")
    first = provider.generate(request)
    second = provider.generate(request)
    assert first.text == second.text == "CANARY_D01"
    assert first.provider_metadata is not None
    assert first.provider_metadata["synthetic_mock"] is True
    assert provider.result_origin == "synthetic_mock"


def test_mock_error_fixtures() -> None:
    provider = MockProvider()
    timeout = provider.generate(_request(force_error="timeout"))
    assert timeout.error_type == "timeout"
    assert timeout.text is None
    connection = provider.generate(
        _request(case_id="encoded_instruction_004", condition="baseline")
    )
    assert connection.error_type == "connection"


def test_ollama_parses_content_and_ignores_thinking() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = request.read()
        assert b"thinking" not in body
        return httpx.Response(
            200,
            json={
                "model": "qwen3:4b",
                "message": {"role": "assistant", "content": "denied", "thinking": "hidden"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 3,
                "total_duration": 10,
                "load_duration": 4,
                "prompt_eval_duration": 3,
                "eval_duration": 2,
            },
        )

    provider = OllamaProvider(
        client=httpx.Client(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(handler),
        )
    )
    response = provider.generate(_request())
    assert response.text == "denied"
    assert response.prompt_token_count == 12
    assert response.completion_token_count == 3
    assert response.provider_metadata is not None
    assert "thinking" not in response.provider_metadata
    assert "hidden" not in str(response.provider_metadata)
    assert response.error_type is None


def test_ollama_connection_and_timeout_are_structured() -> None:
    def connect_error(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = OllamaProvider(
        client=httpx.Client(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(connect_error),
        )
    )
    response = provider.generate(_request())
    assert response.error_type == "connection"
    assert response.text is None

    def timeout_error(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    provider = OllamaProvider(
        client=httpx.Client(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(timeout_error),
        )
    )
    timed = provider.generate(_request())
    assert timed.error_type == "timeout"


def test_ollama_health_messages() -> None:
    def missing(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

    provider = OllamaProvider(
        client=httpx.Client(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(missing),
        )
    )
    issues = provider.health("qwen3:4b")
    assert any("not installed" in issue for issue in issues)
    assert any("ollama pull qwen3:4b" in issue for issue in issues)

    def present(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})

    ready = OllamaProvider(
        client=httpx.Client(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(present),
        )
    )
    assert ready.health("qwen3:4b") == []

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    offline = OllamaProvider(
        client=httpx.Client(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(down),
        )
    )
    messages = offline.health("qwen3:4b")
    assert any("not responding" in message for message in messages)
    assert any("ollama serve" in message for message in messages)
