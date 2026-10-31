"""STT de Groq (Whisper) por HTTPS; el audio solo viaja en la petición."""

from __future__ import annotations

import asyncio

import httpx

from sirah.core.voice import VoiceError

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

_ATTEMPTS = 3
_WAITS = (1, 2)


class GroqSTT:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        language: str = "es",
        timeout_s: float = 30.0,
        url: str = GROQ_STT_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.language = language
        self.timeout_s = timeout_s
        self.url = url
        self.transport = transport

    async def transcribe(self, wav: bytes) -> str:
        last_status_error: VoiceError | None = None
        for attempt in range(_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_s, transport=self.transport
                ) as client:
                    response = await client.post(
                        self.url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files={"file": ("turno.wav", wav, "audio/wav")},
                        data={
                            "model": self.model,
                            "language": self.language,
                            "response_format": "text",
                            "temperature": "0",
                        },
                    )
            except httpx.HTTPError as exc:
                if attempt < _ATTEMPTS - 1:
                    await asyncio.sleep(_WAITS[min(attempt, len(_WAITS) - 1)])
                    continue
                raise VoiceError(
                    "No se pudo conectar con Groq para transcribir. Solución: revisa "
                    "la red y GROQ_API_KEY; SIRAH sigue escuchando."
                ) from exc

            if response.status_code in {401, 403}:
                raise VoiceError(
                    "Groq rechazó la clave del STT. Solución: revisa GROQ_API_KEY "
                    "o configura Groq como LLM para reutilizar LLM_API_KEY."
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < _ATTEMPTS - 1:
                    delay = self._retry_after(response.headers.get("retry-after"))
                    if delay is None:
                        delay = float(_WAITS[min(attempt, len(_WAITS) - 1)])
                    await asyncio.sleep(delay)
                    continue
                last_status_error = VoiceError(
                    f"Groq no pudo transcribir el audio (HTTP {response.status_code}). "
                    "Solución: reintenta en unos segundos; si sigue, revisa STT_MODEL."
                )
                raise last_status_error
            if response.status_code >= 400:
                raise VoiceError(
                    f"Groq no pudo transcribir el audio (HTTP {response.status_code}). "
                    "Solución: reintenta en unos segundos; si sigue, revisa STT_MODEL."
                )
            return response.text.strip()

        raise VoiceError(
            "No se pudo conectar con Groq para transcribir. Solución: revisa "
            "la red y GROQ_API_KEY; SIRAH sigue escuchando."
        )

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            return None
        return max(0.0, min(seconds, 60.0))
