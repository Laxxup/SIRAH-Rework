from __future__ import annotations

import asyncio

import httpx
import pytest

from sirah.adapters.stt import GroqSTT
from sirah.core.voice import VoiceError


def _stt(handler) -> GroqSTT:
    return GroqSTT(
        "clave",
        "whisper-large-v3-turbo",
        language="es",
        url="https://api.groq.test/v1/audio/transcriptions",
        transport=httpx.MockTransport(handler),
    )


def test_sends_wav_and_returns_the_transcription() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(200, text="  hola, SIRAH  ")

    text = asyncio.run(_stt(handler).transcribe(b"RIFF-audio"))
    assert text == "hola, SIRAH"
    assert seen["auth"] == "Bearer clave"
    assert seen["path"] == "/v1/audio/transcriptions"
    body = seen["body"]
    assert isinstance(body, bytes)
    assert b'name="model"' in body and b"whisper-large-v3-turbo" in body
    assert b'name="language"' in body and b"es" in body
    assert b"RIFF-audio" in body


def test_empty_or_noisy_audio_returns_empty_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="\n")

    assert asyncio.run(_stt(handler).transcribe(b"ruido")) == ""


def test_network_failure_is_actionable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    with pytest.raises(VoiceError, match="Solución"):
        asyncio.run(_stt(handler).transcribe(b"audio"))


def test_rejected_key_is_actionable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="no")

    with pytest.raises(VoiceError, match="GROQ_API_KEY"):
        asyncio.run(_stt(handler).transcribe(b"audio"))


def test_retries_429_then_returns_text(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("sirah.adapters.stt.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, text="hola")

    text = asyncio.run(_stt(handler).transcribe(b"audio"))
    assert text == "hola"
    assert calls["n"] == 2


def test_does_not_retry_401(monkeypatch) -> None:
    async def fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("sirah.adapters.stt.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="no")

    with pytest.raises(VoiceError):
        asyncio.run(_stt(handler).transcribe(b"audio"))
    assert calls["n"] == 1
