"""Voz local con Piper en el proceso y reproducción con `aplay`, sin archivos."""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import signal
import wave
from collections.abc import Sequence
from pathlib import Path

from sirah.core.voice import PhraseBuffer, VoiceError, wav_bytes

_MODEL_HINT = "Solución: revisa TTS_MODEL y su .onnx.json; `sirah setup` puede descargarlos."

# Margen sobre la duración del audio antes de dar el reproductor por colgado.
_PLAY_TIMEOUT_MARGIN_S = 5.0


def load_voice(model: str):
    """Carga el modelo una sola vez: arrancar Piper cuesta ~1,5 s."""
    if not Path(model).exists():
        raise VoiceError(f"No se encontró el modelo de voz {Path(model).name}. {_MODEL_HINT}")
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise VoiceError("Falta Piper. Solución: ejecuta `uv sync --all-extras`.") from exc
    try:
        return PiperVoice.load(model)
    except Exception as exc:
        raise VoiceError(f"Piper no pudo cargar {Path(model).name}. {_MODEL_HINT}") from exc


def render_wav(voice, phrase: str) -> bytes:
    """Sintetiza una frase y la envuelve en WAV con la frecuencia del modelo."""
    pcm = b""
    rate = 0
    try:
        for chunk in voice.synthesize(phrase):
            rate = chunk.sample_rate
            pcm += chunk.audio_int16_bytes
    except Exception as exc:
        raise VoiceError(f"Piper no pudo sintetizar la voz. {_MODEL_HINT}") from exc
    if not pcm:
        raise VoiceError(f"Piper no devolvió audio. {_MODEL_HINT}")
    return wav_bytes(pcm, rate=rate)


def player_arguments(command: Sequence[str], device: str = "") -> list[str]:
    """Traduce dispositivo y stdin a las opciones de cada reproductor."""
    name = Path(command[0]).name
    args = list(command)
    if name == "aplay":
        args.append("-q")
        if device:
            args += ["-D", device]
    elif name == "paplay":
        if device:
            args.append(f"--device={device}")
        # paplay lee stdin si no recibe archivo; "-" lo trata como ruta.
    elif name == "pw-play":
        if device:
            args.append(f"--target={device}")
        args.append("-")
    return args


def _wav_duration_s(audio: bytes) -> float:
    """Duración real del WAV para dimensionar el timeout de reproducción."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            return wav.getnframes() / wav.getframerate()
    except (wave.Error, EOFError, ZeroDivisionError):
        return 0.0


def _kill_group(process: asyncio.subprocess.Process) -> None:
    """Mata al reproductor y a sus hijos; corre en sesión propia."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)


class PiperTTS:
    """Sintetiza una frase mientras suena la anterior; todo en memoria."""

    def __init__(
        self,
        model: str,
        *,
        voice=None,
        aplay: Sequence[str] | None = None,
        output_device: str = "",
    ) -> None:
        self.model = model
        self._voice = voice
        self._aplay = list(aplay or ["aplay"])
        self.output_device = output_device
        self._synth_lock = asyncio.Lock()
        self._processes: set[asyncio.subprocess.Process] = set()

    async def _synthesize(self, phrase: str) -> bytes:
        async with self._synth_lock:
            if self._voice is None:
                self._voice = await asyncio.to_thread(load_voice, self.model)
            return await asyncio.to_thread(render_wav, self._voice, phrase)

    async def _play(self, audio: bytes) -> None:
        args = player_arguments(self._aplay, self.output_device)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise VoiceError(
                f"No se pudo ejecutar {self._aplay[0]}. Solución: instala alsa-utils "
                "(`sudo apt install alsa-utils`) y revisa AUDIO_OUTPUT_DEVICE."
            ) from exc
        self._processes.add(process)
        timeout = _wav_duration_s(audio) + _PLAY_TIMEOUT_MARGIN_S
        try:
            await asyncio.wait_for(process.communicate(audio), timeout)
        except TimeoutError as exc:
            _kill_group(process)
            with contextlib.suppress(BaseException):
                await process.wait()
            raise VoiceError(
                f"{self._aplay[0]} no terminó de reproducir en {timeout:.0f} s. "
                "Solución: reinicia el audio (`systemctl --user restart pipewire "
                "wireplumber`) o cambia AUDIO_OUTPUT_DEVICE y AUDIO_PLAYER_COMMAND."
            ) from exc
        finally:
            self._processes.discard(process)
        if process.returncode != 0:
            raise VoiceError(
                f"{self._aplay[0]} no pudo reproducir el audio. Solución: revisa "
                "AUDIO_OUTPUT_DEVICE y `aplay -l`."
            )

    async def say(self, text: str) -> None:
        buffer = PhraseBuffer()
        # «...» no tiene palabras: Piper no devolvería audio y rompería el turno.
        phrases = [
            phrase
            for phrase in buffer.feed(text) + buffer.finish()
            if any(char.isalnum() for char in phrase)
        ]
        if not phrases:
            return
        pending = asyncio.create_task(self._synthesize(phrases[0]))
        try:
            for index in range(len(phrases)):
                audio = await pending
                if index + 1 < len(phrases):
                    pending = asyncio.create_task(self._synthesize(phrases[index + 1]))
                await self._play(audio)
        finally:
            if not pending.done():
                pending.cancel()
            with contextlib.suppress(BaseException):
                await pending

    async def close(self) -> None:
        processes = list(self._processes)
        self._processes.clear()
        for process in processes:
            if process.returncode is None:
                _kill_group(process)
        for process in processes:
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except TimeoutError:
                process.kill()
                with contextlib.suppress(ProcessLookupError):
                    await process.wait()
