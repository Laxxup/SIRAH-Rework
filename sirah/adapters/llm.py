"""Adaptador LLM compatible con OpenAI, con streaming SSE."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence

import httpx

from sirah.core.memory import Message

logger = logging.getLogger("sirah.llm")


def _cause(exc: BaseException) -> str:
    parts: list[str] = []
    cause = exc.__cause__
    while cause is not None and len(parts) < 3:
        detail = str(cause).strip()
        text = f"{type(cause).__name__}: {detail}" if detail else type(cause).__name__
        if text not in parts:
            parts.append(text)
        cause = cause.__cause__
    return " <- ".join(parts)


def _cause_suffix(exc: BaseException) -> str:
    cause = _cause(exc)
    return f" (causa: {cause})" if cause else ""


class LLMError(Exception):
    """Fallo del LLM con un mensaje en español que el usuario puede accionar."""


class _RetryableLLM(Exception):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        timeout_s: float = 60.0,
        max_tokens: int = 1024,
        temperature: float = 0.6,
        reasoning_effort: str = "low",
        retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.retries = max(0, retries)
        self.last_finish_reason: str | None = None

    async def stream(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        if not self.api_key:
            raise LLMError(
                "Falta LLM_API_KEY. Ejecuta `sirah setup` o edita .env para configurarla."
            )

        last_error: _RetryableLLM | None = None
        for attempt in range(self.retries + 1):
            started = False
            try:
                async for chunk in self._stream_once(messages):
                    started = True
                    yield chunk
                return
            except _RetryableLLM as exc:
                last_error = exc
                if started or attempt >= self.retries:
                    logger.warning("El LLM falló: %s%s", exc.message, _cause_suffix(exc))
                    raise LLMError(exc.message) from exc
                delay = exc.retry_after
                if delay is None:
                    delay = float(2**attempt)
                logger.info(
                    "Reintentando el LLM en %.1f s: %s%s",
                    delay,
                    exc.message,
                    _cause_suffix(exc),
                )
                await asyncio.sleep(delay)

        raise LLMError(last_error.message if last_error else "El LLM no respondió.")

    async def _stream_once(self, messages: Sequence[Message]) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": True,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self.timeout_s, connect=min(10.0, self.timeout_s))

        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response,
            ):
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    logger.warning(
                        "El LLM rechazó la petición HTTP %s: %s",
                        response.status_code,
                        body.strip()[:300] or "sin cuerpo",
                    )
                    raise self._status_error(
                        response.status_code,
                        response.headers.get("retry-after"),
                    )

                saw_data = False
                saw_content = False
                finish_reason: str | None = None
                usage: dict[str, object] = {}
                self.last_finish_reason = None
                async for line in response.aiter_lines():
                    stripped = line.strip()
                    if not stripped.startswith("data:"):
                        continue
                    data = stripped[5:].strip()
                    if not data:
                        continue
                    saw_data = True
                    if data == "[DONE]":
                        self._log_turn(saw_content, finish_reason, usage)
                        return
                    event = self._event_from_data(data)
                    if event is None:
                        continue
                    choices = event.get("choices")
                    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                        reason = choices[0].get("finish_reason")
                        if isinstance(reason, str) and reason:
                            finish_reason = reason
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                    content = self._content_from_event(event)
                    if content:
                        saw_content = True
                        yield content
                if not saw_data:
                    raise LLMError(
                        "El LLM devolvió una respuesta inesperada (no es un stream SSE). "
                        "Comprueba que LLM_BASE_URL apunte a un endpoint compatible con OpenAI "
                        "y que LLM_MODEL exista."
                    )
                if finish_reason is None:
                    raise LLMError(
                        "La respuesta del LLM se cortó antes de terminar. "
                        "Comprueba tu conexión e inténtalo de nuevo."
                    )
                self._log_turn(saw_content, finish_reason, usage)
        except httpx.TimeoutException as exc:
            raise _RetryableLLM(
                f"El LLM no respondió en {self.timeout_s:g} s. "
                "Comprueba tu conexión o aumenta LLM_TIMEOUT_S."
            ) from exc
        except httpx.ConnectError as exc:
            raise _RetryableLLM(
                "No se pudo conectar con el LLM (sin red o LLM_BASE_URL incorrecta). "
                "Comprueba tu conexión a internet y la URL."
            ) from exc
        except httpx.HTTPError as exc:
            raise _RetryableLLM(
                "Se perdió la conexión con el LLM durante la respuesta. "
                "Comprueba tu conexión e inténtalo de nuevo."
            ) from exc

    def _log_turn(
        self,
        saw_content: bool,
        finish_reason: str | None,
        usage: dict[str, object],
    ) -> None:
        self.last_finish_reason = finish_reason
        details = usage.get("completion_tokens_details")
        reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
        empty = "" if saw_content else " sin texto"
        logger.log(
            logging.INFO if saw_content else logging.WARNING,
            "El LLM terminó%s (finish_reason=%s, completion_tokens=%s, reasoning_tokens=%s)",
            empty,
            finish_reason or "desconocido",
            usage.get("completion_tokens", "?"),
            reasoning if reasoning is not None else "?",
        )

    @staticmethod
    def _event_from_data(data: str) -> dict[str, object] | None:
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            logger.debug("Evento SSE inválido descartado: %s", data[:120])
            return None
        if not isinstance(event, dict):
            return None
        if "error" in event:
            detail = json.dumps(event["error"], ensure_ascii=False)[:300]
            logger.warning("El LLM devolvió un error en el stream: %s", detail)
            raise LLMError(
                "El LLM devolvió un error inesperado. Inténtalo de nuevo; si persiste, "
                "revisa LLM_MODEL y LLM_BASE_URL (detalle en el log)."
            )
        return event

    @staticmethod
    def _content_from_event(event: dict[str, object]) -> str | None:
        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        choice = choices[0]
        if not isinstance(choice, dict):
            return None
        delta = choice.get("delta") or choice.get("message") or {}
        if not isinstance(delta, dict):
            return None
        content = delta.get("content")
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            return "".join(parts) or None
        return None

    def _status_error(self, status: int, retry_after: str | None) -> Exception:
        if status in {401, 403}:
            return LLMError(
                f"El proveedor rechazó LLM_API_KEY (HTTP {status}). "
                "Revisa la clave con `sirah setup`."
            )
        if status == 404:
            return LLMError(
                "El LLM no encontró el modelo o la URL (HTTP 404). Revisa LLM_MODEL y LLM_BASE_URL."
            )
        if status == 429:
            return _RetryableLLM(
                "El proveedor del LLM está limitando las peticiones (HTTP 429). "
                "Espera unos segundos o revisa la cuota de tu plan.",
                self._retry_after(retry_after),
            )
        if status >= 500:
            return _RetryableLLM(
                f"El servicio del LLM falló (HTTP {status}). "
                "Espera unos segundos y vuelve a intentarlo; si persiste, "
                "consulta el estado del proveedor."
            )
        return LLMError(
            f"El LLM rechazó la petición (HTTP {status}). Revisa LLM_MODEL y LLM_BASE_URL."
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
