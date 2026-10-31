"""Sesión de voz: micrófono → VAD → Groq STT → agente → Piper, half-duplex."""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Callable

from sirah.adapters.history_file import HistoryFile
from sirah.adapters.llm import LLMError
from sirah.adapters.mic import ArecordMicrophone
from sirah.adapters.stt import GroqSTT
from sirah.adapters.tts import PiperTTS
from sirah.config import Config
from sirah.core.agent import Agent
from sirah.core.persona import Persona
from sirah.core.voice import (
    FRAME_MS,
    AdaptiveSpeechDetector,
    PhraseBuffer,
    SpeechDetector,
    State,
    Supervisor,
    VoiceError,
    VoiceSegmenter,
    rms,
)
from sirah.doctor import alsa_cards, find_piper, resolve_player
from sirah.session import build_agent, opening_greeting
from sirah.terminal import _stdout, run_terminal

logger = logging.getLogger("sirah.voice")

# Tras 5 fallos seguidos del micrófono se vuelve al chat por texto.
_MIC_ATTEMPTS = 5
# Tope de la calibración previa al saludo: 1,5 s si el suelo no queda listo.
_CALIBRATION_MAX_FRAMES = 75


class VoiceLoop:
    """Un turno a la vez: escucha, transcribe, responde y habla."""

    def __init__(
        self,
        agent: Agent,
        persona: Persona,
        *,
        mic: ArecordMicrophone,
        stt: GroqSTT,
        tts: PiperTTS,
        history: HistoryFile | None = None,
        segmenter: VoiceSegmenter | None = None,
        supervisor: Supervisor | None = None,
        write: Callable[[str], None] = _stdout,
    ) -> None:
        self.agent = agent
        self.persona = persona
        self.mic = mic
        self.stt = stt
        self.tts = tts
        self.history = history
        self.segmenter = segmenter or VoiceSegmenter(SpeechDetector())
        self.supervisor = supervisor or Supervisor()
        self.write = write

    async def run(self) -> None:
        failures = 0
        while True:
            try:
                await self._turn()
                failures = 0
            except VoiceError as exc:
                failures += 1
                if failures >= _MIC_ATTEMPTS:
                    raise
                self.write(f"[FALLA] {exc}\n")
                await asyncio.sleep(min(2 ** (failures - 1), 30))

    async def calibrate(self) -> None:
        """Deja el suelo de ruido calibrado antes de que el robot hable."""
        detector = getattr(self.segmenter, "detector", None)
        if not hasattr(detector, "noise_floor"):
            return
        self.segmenter.start_session()
        await self.mic.start()
        try:
            for _ in range(_CALIBRATION_MAX_FRAMES):
                self.segmenter.feed(await self.mic.read_frame())
                if detector.noise_floor is not None:
                    return
        finally:
            await self.mic.stop()

    async def speak_greeting(self, text: str) -> None:
        if not text.strip():
            return
        self.supervisor.set(State.SPEAKING)
        self.write(f"{self.persona.display_name}> {text}\n\n")
        try:
            await self.tts.say(text)
        except VoiceError as exc:
            self.write(f"[AVISO] {exc}\n")
        finally:
            self.supervisor.set(State.IDLE)

    async def _turn(self) -> None:
        self.supervisor.set(State.LISTENING)
        self.segmenter.reset()
        # Un micrófono roto sube a run(), que reintenta con espera creciente.
        audio = await self._listen()
        if audio is None:
            return

        self.supervisor.set(State.THINKING)
        try:
            text = await self.stt.transcribe(audio)
        except VoiceError as exc:
            self.write(f"[AVISO] {exc}\n")
            self.supervisor.set(State.IDLE)
            return
        text = text.strip()
        if sum(ch.isalnum() for ch in text) < 2:
            self.write("[AVISO] No te entendí; sigo escuchando.\n")
            self.supervisor.set(State.IDLE)
            return
        self.write(f"tú> {text}\n")

        self.supervisor.set(State.SPEAKING)
        await self._respond(text)
        self.supervisor.set(State.IDLE)

    async def _listen(self) -> bytes | None:
        self.segmenter.start_session()
        await self.mic.start()
        try:
            while True:
                frame = await self.mic.read_frame()
                audio = self.segmenter.feed(frame)
                self._report_audio_problem()
                if audio is not None:
                    return audio
        finally:
            await self.mic.stop()

    def _report_audio_problem(self) -> None:
        discard = getattr(self.segmenter, "last_discard", None)
        if discard:
            self.segmenter.last_discard = None  # type: ignore[union-attr]
            if discard == "noise":
                self.write(
                    "[AVISO] ruido constante: baja la ganancia de captura "
                    "(alsamixer/pavucontrol).\n"
                )
            else:
                self.write("[AVISO] Te oí muy poco; acércate al micrófono.\n")
        detector = getattr(self.segmenter, "detector", None)
        warning = getattr(detector, "pending_warning", None)
        if warning:
            detector.pending_warning = None
            self.write(f"[AVISO] {warning}\n")

    async def _respond(self, text: str) -> None:
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def speak() -> None:
            while (phrase := await queue.get()) is not None:
                try:
                    await self.tts.say(phrase)
                except VoiceError as exc:
                    # Una frase impronunciable no debe callar el resto.
                    self.write(f"[AVISO] {exc}\n")

        speaker = asyncio.create_task(speak())
        buffer = PhraseBuffer()
        pieces: list[str] = []
        self.write(f"{self.persona.display_name}> ")
        try:
            async for chunk in self.agent.respond(text, on_actions=self.supervisor.actions):
                pieces.append(chunk)
                self.write(chunk)
                for phrase in buffer.feed(chunk):
                    queue.put_nowait(phrase)
        except LLMError as exc:
            self.write(f"\n[FALLA] {exc}\n")
        except Exception:
            logger.exception("Fallo inesperado durante el turno de voz")
            self.write("\n[FALLA] Algo falló al procesar el turno. Revisa el log.\n")
        finally:
            for phrase in buffer.finish():
                queue.put_nowait(phrase)
            queue.put_nowait(None)
        self.write("\n")
        await speaker

        answer = "".join(pieces).strip()
        if answer and self.history is not None:
            self.history.append("user", text)
            self.history.append("assistant", answer)

    async def close(self) -> None:
        await self.mic.close()
        await self.tts.close()
        self.supervisor.close()


def _prerequisites(config: Config) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    if not config.stt_api_key:
        problems.append(
            (
                "falta GROQ_API_KEY para transcribir",
                "añádela a .env o configura Groq como LLM para reutilizar su clave.",
            )
        )
    if shutil.which("arecord") is None:
        problems.append(("falta arecord", "instala alsa-utils: `sudo apt install alsa-utils`."))
    if not any(shutil.which(tool) for tool in ("aplay", "paplay", "pw-play")):
        problems.append(
            (
                "falta un reproductor de audio",
                "instala alsa-utils: `sudo apt install alsa-utils`.",
            )
        )
    if shutil.which("arecord") is not None and alsa_cards("arecord") == 0:
        problems.append(("no hay micrófono de captura", "conecta uno y revisa `arecord -l`."))
    piper = find_piper()
    model = config.tts_model
    if piper is None:
        problems.append(("falta la librería piper", "ejecuta `uv sync --all-extras`."))
    if not model.exists() or not model.with_name(f"{model.name}.json").exists():
        problems.append(
            (
                "falta el modelo de voz",
                f"ejecuta `sirah setup` para descargar {model.name}.",
            )
        )
    return problems


def _segmenter_factory(config: Config) -> Callable[[], VoiceSegmenter]:
    detector = AdaptiveSpeechDetector(
        noise_calibration_ms=config.vad_noise_calibration_ms,
        start_multiple=config.vad_start_multiple,
        end_multiple=config.vad_end_multiple,
        min_start_rms=config.vad_min_start_rms,
        min_end_rms=config.vad_min_end_rms,
    )

    def segmenter() -> VoiceSegmenter:
        return VoiceSegmenter(
            detector,
            start_frames=config.vad_start_frames,
            silence_ms=config.vad_silence_ms,
            prebuffer_ms=config.vad_prebuffer_ms,
            max_turn_ms=config.vad_max_turn_ms,
        )

    return segmenter


async def run_voice(
    config: Config,
    persona: Persona,
    *,
    identity: str = "card",
    language: str = "es",
    write: Callable[[str], None] = _stdout,
) -> int:
    problems = _prerequisites(config)
    if problems:
        for problem, fix in problems:
            write(f"[FALLA] Voz: {problem}\n        Solución: {fix}\n")
        write("[AVISO] La voz no está disponible; sigo por texto.\n\n")
        return await run_terminal(config, persona, identity=identity, language=language)

    choice = resolve_player(config)
    if choice.command is None:
        write(f"[FALLA] Audio: {choice.message}\n")
        write(
            "        Solución: fija AUDIO_PLAYER_COMMAND (por ejemplo paplay) "
            "o revisa `sirah doctor`.\n"
        )
        write("[AVISO] La voz no está disponible; sigo por texto.\n\n")
        return await run_terminal(config, persona, identity=identity, language=language)
    if choice.message:
        write(f"[AVISO] {choice.message}\n")

    agent, history = build_agent(config, persona, identity=identity, language=language)
    mic = ArecordMicrophone(device=config.audio_input_device)
    stt = GroqSTT(
        config.stt_api_key,
        config.stt_model,
        language=config.stt_language,
        timeout_s=config.stt_timeout_s,
    )
    tts = PiperTTS(
        str(config.tts_model),
        aplay=list(choice.command),
        output_device=config.audio_output_device,
    )
    loop = VoiceLoop(
        agent,
        persona,
        mic=mic,
        stt=stt,
        tts=tts,
        history=history,
        segmenter=_segmenter_factory(config)(),
        write=write,
    )

    write(f"{persona.display_name} — voz.\n")
    if identity == "robot":
        write("Modo robot estricto\n")
    for warning in persona.warnings:
        write(f"[AVISO] {warning}\n")
    try:
        await loop.calibrate()
    except VoiceError as exc:
        write(f"[AVISO] {exc}\n")
    greeting = await opening_greeting(agent, persona, config)
    try:
        await loop.speak_greeting(greeting)
        write("Micrófono activo. Ctrl-C para salir\n")
        write("El audio se envía a Groq para transcribirse; no se guarda en disco.\n\n")
        try:
            await loop.run()
        except VoiceError as exc:
            write(f"[FALLA] Voz: {exc}\n")
            write(
                "[AVISO] Sigo por texto. La conversación en memoria no se traslada: "
                "solo se conserva el historial guardado.\n\n"
            )
            return await run_terminal(config, persona, identity=identity, language=language)
    finally:
        await loop.close()
    return 0


async def run_check(
    config: Config,
    *,
    write: Callable[[str], None] = _stdout,
    mic: ArecordMicrophone | None = None,
) -> int:
    mic = mic or ArecordMicrophone(device=config.audio_input_device)
    write("Grabando 3 segundos...\n")
    try:
        frames = await mic.record(3.0)
    except VoiceError as exc:
        write(f"[FALLA] {exc}\n")
        return 1
    finally:
        await mic.close()

    levels = [rms(frame) for frame in frames]
    average = sum(levels) / len(levels) if levels else 0.0
    peak = max(levels, default=0.0)
    detector = AdaptiveSpeechDetector(
        noise_calibration_ms=config.vad_noise_calibration_ms,
        start_multiple=config.vad_start_multiple,
        end_multiple=config.vad_end_multiple,
        min_start_rms=config.vad_min_start_rms,
        min_end_rms=config.vad_min_end_rms,
    )
    voiced = sum(1 for frame in frames if detector(frame))
    seconds = len(frames) * FRAME_MS / 1000

    write(
        f"Nivel RMS: medio {average:.0f}, máximo {peak:.0f} "
        f"(VAD_MIN_START_RMS={config.vad_min_start_rms})\n"
    )
    floor = detector.noise_floor or 0.0
    write(
        f"Suelo de ruido: {floor:.0f} RMS; umbrales inicio "
        f"{detector.start_threshold:.0f}, fin {detector.end_threshold:.0f}\n"
    )
    if detector.pending_warning:
        write(f"[AVISO] {detector.pending_warning}\n")
    write(
        f"VAD: {'voz detectada' if voiced else 'sin voz'} en {voiced} de "
        f"{len(frames)} frames ({seconds:.1f} s)\n"
    )
    if average > 8000:
        write(
            "Aviso: el micrófono satura (nivel de ruido casi al máximo), así que no "
            "hay silencio que el VAD pueda distinguir. Baja la ganancia de captura "
            "(`alsamixer -c 0`) o elige otro dispositivo con AUDIO_INPUT_DEVICE.\n"
        )
    elif floor > 2000:
        pass  # El aviso del suelo ya dice qué hacer.
    elif voiced:
        write("Ajuste: si la conversación no arranca, sube VAD_MIN_START_RMS.\n")
    else:
        write("Ajuste: acércate al micrófono o baja VAD_MIN_START_RMS.\n")
    return 0
