"""Piezas sin I/O de la voz: estados, VAD por frames, frases y errores."""

from __future__ import annotations

import logging
import math
import re
import wave
from array import array
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from io import BytesIO

FRAME_MS = 20
SAMPLE_RATE = 16000
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2

logger = logging.getLogger(__name__)

# Un turno necesita al menos esta duración de voz real para no ser un chasquido.
_MIN_VOICE_MS = 300
# Tras reabrir el micrófono se descartan 200 ms de cola del altavoz.
_WARMUP_FRAMES = 10
# Solo se sigue el suelo tras este silencio estable.
_STABLE_SILENCE_FRAMES = 20
# Tras 5 s de silencio continuo se vuelve a calibrar el suelo.
_LONG_SILENCE_FRAMES = 250

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡«\"(….]|$)")


class VoiceError(Exception):
    """Fallo de voz con un mensaje accionable en español."""


class State(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class NullEyes:
    """Puerto de ojos apagado; el hito 2 implementará esta misma interfaz."""

    def on_state(self, state: State) -> None:
        return None

    def on_actions(self, actions: object) -> None:
        return None

    def close(self) -> None:
        return None


class Supervisor:
    """Máquina de estados mínima que avisa a los ojos."""

    def __init__(self, eyes: NullEyes | None = None) -> None:
        self.eyes = eyes or NullEyes()
        self.state = State.IDLE

    def set(self, state: State) -> None:
        self.state = state
        self.eyes.on_state(state)

    def actions(self, actions: object) -> None:
        self.eyes.on_actions(actions)

    def close(self) -> None:
        self.eyes.close()


def rms(frame: bytes) -> float:
    samples = array("h")
    samples.frombytes(frame[: len(frame) // 2 * 2])
    if not samples:
        return 0.0
    total = sum(sample * sample for sample in samples)
    return math.sqrt(total / len(samples))


class SpeechDetector:
    """RMS configurable; usa webrtcvad si está instalado."""

    def __init__(self, min_rms: int = 350, aggressiveness: int = 2) -> None:
        self.min_rms = min_rms
        self._vad = None
        try:
            import webrtcvad

            self._vad = webrtcvad.Vad(aggressiveness)
        except (ImportError, ValueError):
            pass

    def is_speech(self, frame: bytes) -> bool:
        if rms(frame) < self.min_rms:
            return False
        if self._vad is None:
            return True
        try:
            return bool(self._vad.is_speech(frame, SAMPLE_RATE))
        except Exception:
            return True

    def __call__(self, frame: bytes) -> bool:
        return self.is_speech(frame)


class AdaptiveSpeechDetector:
    """Suelo de ruido adaptativo con histéresis y seguimiento lento."""

    def __init__(
        self,
        *,
        noise_calibration_ms: int = 500,
        start_multiple: float = 1.6,
        end_multiple: float = 1.2,
        min_start_rms: int = 1200,
        min_end_rms: int = 600,
    ) -> None:
        self.start_multiple = start_multiple
        self.end_multiple = end_multiple
        self.min_start_rms = min_start_rms
        self.min_end_rms = min_end_rms
        self._calibration_frames = max(1, noise_calibration_ms // FRAME_MS)
        self._samples: list[float] = []
        self._warmup = _WARMUP_FRAMES
        self._quiet_run = 0
        self._speaking = False
        self._pending_calibration = True
        self.noise_floor: float | None = None
        self.pending_warning: str | None = None

    @property
    def start_threshold(self) -> float:
        return max((self.noise_floor or 0.0) * self.start_multiple, self.min_start_rms)

    @property
    def end_threshold(self) -> float:
        start = self.start_threshold
        end = max((self.noise_floor or 0.0) * self.end_multiple, self.min_end_rms)
        return min(end, start * 0.7) if end >= start else end

    def start_session(self) -> None:
        """Descarta la cola del altavoz; solo calibra la primera vez."""
        self._warmup = _WARMUP_FRAMES
        self._quiet_run = 0
        self._speaking = False
        if self.noise_floor is None:
            self._pending_calibration = True
            self._samples = []

    def _calibrate(self) -> None:
        ranked = sorted(self._samples)
        self._samples = []
        self._pending_calibration = False
        self.noise_floor = ranked[int(0.9 * (len(ranked) - 1))]
        if self.noise_floor > 2000 and self.pending_warning is None:
            self.pending_warning = (
                "El ruido de fondo del micrófono es alto. Baja la ganancia con "
                "`alsamixer -c 0` (F4) o en pavucontrol → Grabación, y repite "
                "`sirah voice --check` en silencio hasta ver un suelo < 1500."
            )

    def _track_floor(self, level: float) -> None:
        floor = self.noise_floor or 0.0
        step = floor * 0.02
        self.noise_floor = max(0.0, floor + max(-step, min(step, level - floor)))

    def __call__(self, frame: bytes) -> bool:
        if self._warmup:
            self._warmup -= 1
            return False
        level = rms(frame)
        if self._pending_calibration:
            self._samples.append(level)
            if len(self._samples) < self._calibration_frames:
                return False
            self._calibrate()
        start, end = self.start_threshold, self.end_threshold
        if self._speaking:
            if level < end:
                self._speaking = False
        elif level >= start:
            self._speaking = True
        if self._speaking:
            self._quiet_run = 0
            return True
        self._quiet_run += 1
        if self._quiet_run >= _LONG_SILENCE_FRAMES:
            self._pending_calibration = True
            self._samples = []
            self._quiet_run = 0
        elif self._quiet_run >= _STABLE_SILENCE_FRAMES and level <= start:
            self._track_floor(level)
        return False


def wav_bytes(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm)
    return buffer.getvalue()


class VoiceSegmenter:
    """Une frames en un turno: pre-roll, inicio por voz y fin por silencio."""

    def __init__(
        self,
        detector: Callable[[bytes], bool] | SpeechDetector,
        *,
        start_frames: int = 3,
        silence_ms: int = 400,
        prebuffer_ms: int = 300,
        max_turn_ms: int = 10000,
    ) -> None:
        self.detector = detector
        self.start_frames = max(1, start_frames)
        self.silence_frames = max(1, silence_ms // FRAME_MS)
        self.prebuffer_frames = max(0, prebuffer_ms // FRAME_MS)
        self.max_frames = max(1, max_turn_ms // FRAME_MS)
        self.reset()

    def reset(self) -> None:
        self._pre: deque[bytes] = deque(maxlen=self.prebuffer_frames)
        self._frames: list[bytes] = []
        self._speech_run = 0
        self._silence_run = 0
        self._in_turn = False
        self._voiced_frames = 0
        self.last_discard: str | None = None

    def start_session(self) -> None:
        """Avisa al detector de que el micrófono se acaba de reabrir."""
        if hasattr(self.detector, "start_session"):
            self.detector.start_session()  # type: ignore[union-attr]

    def feed(self, frame: bytes) -> bytes | None:
        speech = bool(self.detector(frame))
        if not self._in_turn:
            if self.prebuffer_frames:
                self._pre.append(frame)
            self._speech_run = self._speech_run + 1 if speech else 0
            if self._speech_run < self.start_frames:
                return None
            self._in_turn = True
            self._frames = list(self._pre)
            self._speech_run = 0
            # Los frames que abren el turno también son voz real.
            self._voiced_frames = self.start_frames
            return None

        self._frames.append(frame)
        if speech:
            self._voiced_frames += 1
        self._silence_run = 0 if speech else self._silence_run + 1
        if self._silence_run < self.silence_frames and len(self._frames) < self.max_frames:
            return None
        return self._finish()

    def _finish(self) -> bytes | None:
        frames = self._frames
        if self._silence_run:
            frames = frames[: len(frames) - self._silence_run]
        voiced_frames = self._voiced_frames
        reached_max = len(self._frames) >= self.max_frames
        constant_noise = (
            reached_max and not self._silence_run and voiced_frames >= 0.9 * len(frames)
        )
        self.reset()
        if constant_noise:
            self.last_discard = "noise"
            return None
        if voiced_frames * FRAME_MS < _MIN_VOICE_MS:
            logger.debug(
                "Turno corto descartado: %s ms de voz (mínimo %s ms)",
                voiced_frames * FRAME_MS,
                _MIN_VOICE_MS,
            )
            self.last_discard = "short"
            return None
        return wav_bytes(b"".join(frames)) if frames else None


class PhraseBuffer:
    """Corta el stream en frases para sintetizar mientras llega el resto."""

    def __init__(self, max_chars: int = 200) -> None:
        self.max_chars = max_chars
        self._buffer = ""

    def feed(self, chunk: str) -> list[str]:
        self._buffer += chunk
        phrases: list[str] = []
        while match := _SENTENCE_END.search(self._buffer):
            phrase = self._buffer[: match.start()].strip()
            self._buffer = self._buffer[match.end() :]
            if phrase:
                phrases.append(phrase)
        while len(self._buffer) > self.max_chars:
            cut = self._buffer.rfind(" ", 0, self.max_chars)
            cut = cut if cut > 0 else self.max_chars
            phrase = self._buffer[:cut].strip()
            self._buffer = self._buffer[cut:]
            if phrase:
                phrases.append(phrase)
        return phrases

    def finish(self) -> list[str]:
        phrase = self._buffer.strip()
        self._buffer = ""
        return [phrase] if phrase else []
