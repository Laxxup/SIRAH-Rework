from __future__ import annotations

import asyncio

import pytest

from sirah.adapters.llm import LLMClient, LLMError
from sirah.core.memory import Message
from tests.fake_llm import FakeLLM, FakeResponse

MESSAGES = [Message("user", "hola")]


def _collect(llm: LLMClient) -> list[str]:
    async def run() -> list[str]:
        return [chunk async for chunk in llm.stream(MESSAGES)]

    return asyncio.run(run())


def test_streams_content_and_sends_openai_payload() -> None:
    with FakeLLM([FakeResponse(["Hola", " mundo"])]) as server:
        llm = LLMClient(
            api_key="clave",
            base_url=server.base_url + "/",
            model="modelo",
            max_tokens=64,
            temperature=0.2,
        )
        assert _collect(llm) == ["Hola", " mundo"]

        request = server.requests[0]
        assert request["model"] == "modelo"
        assert request["stream"] is True
        assert request["max_tokens"] == 64
        assert request["temperature"] == 0.2
        assert request["messages"] == [{"role": "user", "content": "hola"}]
        assert server.paths[0] == "/v1/chat/completions"
        headers = {key.lower(): value for key, value in server.headers[0].items()}
        assert headers["authorization"] == "Bearer clave"
        assert headers["accept"] == "text/event-stream"


def test_reasoning_effort_defaults_to_low_and_can_be_omitted() -> None:
    with FakeLLM([FakeResponse(["Hola"])]) as server:
        _collect(LLMClient("clave", server.base_url, "modelo"))
        assert server.requests[0]["reasoning_effort"] == "low"
        assert server.requests[0]["max_tokens"] == 1024

    with FakeLLM([FakeResponse(["Hola"])]) as server:
        _collect(LLMClient("clave", server.base_url, "modelo", reasoning_effort=""))
        assert "reasoning_effort" not in server.requests[0]


def test_every_turn_logs_finish_reason_and_usage(caplog) -> None:
    caplog.set_level("INFO", logger="sirah.llm")
    response = FakeResponse(
        ["Hola"],
        finish_reason="stop",
        usage={
            "completion_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 7},
        },
    )
    with FakeLLM([response]) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        assert _collect(llm) == ["Hola"]

    assert "finish_reason=stop" in caplog.text
    assert "completion_tokens=20" in caplog.text
    assert "reasoning_tokens=7" in caplog.text
    assert llm.last_finish_reason == "stop"


def test_long_response_exposes_length_finish_reason() -> None:
    response = FakeResponse(
        ["Hola"],
        finish_reason="length",
        usage={"completion_tokens": 512},
    )
    with FakeLLM([response]) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        assert _collect(llm) == ["Hola"]

    assert llm.last_finish_reason == "length"


def test_retries_429_before_content() -> None:
    responses = [
        FakeResponse(status=429, headers={"Retry-After": "0"}),
        FakeResponse(["Vale"]),
    ]
    with FakeLLM(responses) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        assert _collect(llm) == ["Vale"]
        assert len(server.requests) == 2


def test_gives_up_after_retries() -> None:
    responses = [FakeResponse(status=429, headers={"Retry-After": "0"})] * 3
    with FakeLLM(responses) as server:
        llm = LLMClient("clave", server.base_url, "modelo", retries=2)
        with pytest.raises(LLMError, match="limitando"):
            _collect(llm)
        assert len(server.requests) == 3


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_is_not_retried(status: int) -> None:
    with FakeLLM([FakeResponse(status=status)]) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        with pytest.raises(LLMError, match="LLM_API_KEY"):
            _collect(llm)
        assert len(server.requests) == 1


def test_server_error_has_actionable_message() -> None:
    with FakeLLM([FakeResponse(status=503)]) as server:
        llm = LLMClient("clave", server.base_url, "modelo", retries=0)
        with pytest.raises(LLMError, match="HTTP 503"):
            _collect(llm)


def test_unexpected_non_sse_response_is_reported() -> None:
    with FakeLLM([FakeResponse(body="<html>esto no es SSE</html>")]) as server:
        llm = LLMClient("clave", server.base_url, "modelo", retries=0)
        with pytest.raises(LLMError, match="respuesta inesperada"):
            _collect(llm)


def test_stream_error_event_is_reported() -> None:
    body = 'data: {"error": {"message": "modelo no disponible"}}\n\n'
    with FakeLLM([FakeResponse(body=body)]) as server:
        llm = LLMClient("clave", server.base_url, "modelo", retries=0)
        with pytest.raises(LLMError, match="error inesperado"):
            _collect(llm)


def test_missing_key_fails_before_network() -> None:
    llm = LLMClient("", "http://127.0.0.1:1/v1", "modelo")
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        _collect(llm)


def test_connection_error_has_actionable_message_and_logs_cause(caplog) -> None:
    caplog.set_level("INFO", logger="sirah.llm")
    llm = LLMClient("clave", "http://127.0.0.1:1/v1", "modelo", retries=0)
    with pytest.raises(LLMError, match="No se pudo conectar"):
        _collect(llm)
    assert "ConnectError" in caplog.text


def test_empty_response_logs_finish_reason_and_usage(caplog) -> None:
    caplog.set_level("WARNING", logger="sirah.llm")
    response = FakeResponse(
        finish_reason="length",
        usage={
            "completion_tokens": 256,
            "completion_tokens_details": {"reasoning_tokens": 250},
        },
    )
    with FakeLLM([response]) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        assert _collect(llm) == []

    assert "finish_reason=length" in caplog.text
    assert "completion_tokens=256" in caplog.text
    assert "reasoning_tokens=250" in caplog.text


def test_truncated_stream_without_finish_reason_raises() -> None:
    with (
        FakeLLM([FakeResponse(["Hola"], done=False, finish_reason=None)]) as server,
        pytest.raises(LLMError, match="se cortó"),
    ):
        _collect(LLMClient("clave", server.base_url, "modelo"))


def test_stream_with_finish_reason_stop_does_not_raise() -> None:
    with FakeLLM([FakeResponse(["Hola"], done=False, finish_reason="stop")]) as server:
        assert _collect(LLMClient("clave", server.base_url, "modelo")) == ["Hola"]


def test_timeout_after_content_is_not_retried() -> None:
    response = FakeResponse(["Hola"], delay=0.4)
    with FakeLLM([response]) as server:
        llm = LLMClient("clave", server.base_url, "modelo", timeout_s=0.15, retries=2)
        received: list[str] = []

        async def run() -> None:
            async for chunk in llm.stream(MESSAGES):
                received.append(chunk)

        with pytest.raises(LLMError, match="no respondió"):
            asyncio.run(run())
        assert received == ["Hola"]
        assert len(server.requests) == 1


def test_retry_after_is_capped_at_60_seconds(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("sirah.adapters.llm.asyncio.sleep", fake_sleep)
    responses = [
        FakeResponse(status=429, headers={"Retry-After": "30"}),
        FakeResponse(["Hola"]),
    ]
    with FakeLLM(responses) as server:
        llm = LLMClient("clave", server.base_url, "modelo")
        assert _collect(llm) == ["Hola"]
        assert len(server.requests) == 2
    assert sleeps == [30.0]


def test_stream_truncated_message_is_actionable() -> None:
    with (
        FakeLLM([FakeResponse(["Hola"], done=False, finish_reason=None)]) as server,
        pytest.raises(LLMError, match="Comprueba tu conexión"),
    ):
        _collect(LLMClient("clave", server.base_url, "modelo"))
