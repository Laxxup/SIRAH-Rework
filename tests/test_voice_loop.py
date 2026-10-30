from __future__ import annotations

import asyncio
import contextlib
from array import array
from pathlib import Path
from types import SimpleNamespace

import pytest

from sirah.config import load_config
from sirah.core.persona import Persona
from sirah.core.voice import (
    FRAME_BYTES,
    AdaptiveSpeechDetector,
    State,
    VoiceError,
    VoiceSegmenter,
)
from sirah.voice import VoiceLoop, _prerequisites, run_check, run_voice

SILENCE = b"\x00" * FRAME_BYTES
TONE = b"\x00\x10" * (FRAME_BYTES // 2)


def _level(value: int) -> bytes:
    return array("h", [value] * (FRAME_BYTES // 2)).tobytes()


def _persona() -> Persona:
    return Persona(path=Path("/tmp/sirah.json"), name="SIRAH")


class FakeMic:
    def __init__(self, turns: list[list[bytes]] | None = None) -> None:
        self.turns = list(turns or [])
        self.calls: list[str] = []
        self.active = False
        self.closed = False
        self._frames: list[bytes] = []

    async def start(self) -> None:
        assert not self.active
        self.active = True
        self.calls.append("start")
        self._frames = list(self.turns.pop(0)) if self.turns else []

    async def read_frame(self) -> bytes:
        await asyncio.sleep(0)
        return self._frames.pop(0) if self._frames else SILENCE

    async def record(self, seconds: float = 3.0) -> list[bytes]:
        await self.start()
        try:
            return [await self.read_frame() for _ in range(int(seconds * 1000 / 20))]
        finally:
            await self.stop()

    async def stop(self) -> None:
        self.active = False
        self.calls.append("stop")

    async def close(self) -> None:
        self.closed = True


class FakeSTT:
    def __init__(self, texts: list[str | Exception]) -> None:
        self.texts = list(texts)
        self.audios: list[bytes] = []

    async def transcribe(self, audio: bytes) -> str:
        self.audios.append(audio)
        item = self.texts.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeTTS:
    def __init__(self, mic: FakeMic) -> None:
        self.mic = mic
        self.phrases: list[str] = []
        self.closed = False
        self.heard_itself = False

    async def say(self, text: str) -> None:
        if self.mic.active:
            self.heard_itself = True
        self.phrases.append(text)

    async def close(self) -> None:
        self.closed = True


class FakeAgent:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.texts: list[str] = []
        self.actions: object = None

    async def respond(self, text: str, on_actions=None):
        self.texts.append(text)
        if on_actions is not None:
            on_actions(("blink",))
        for chunk in self.chunks:
            yield chunk


class FlakyTTS(FakeTTS):
    """Falla al decir ciertas frases, como Piper con un texto sin voz."""

    def __init__(self, mic: FakeMic, fail: set[str]) -> None:
        super().__init__(mic)
        self.fail = fail

    async def say(self, text: str) -> None:
        self.phrases.append(text)
        if text in self.fail:
            raise VoiceError("Piper no devolvió audio. Solución: revisa TTS_MODEL.")


def _loop(
    mic: FakeMic,
    stt: FakeSTT,
    tts: FakeTTS,
    agent: FakeAgent,
    output: list[str],
) -> VoiceLoop:
    segmenter = VoiceSegmenter(
        lambda frame: frame == TONE,
        start_frames=1,
        silence_ms=20,
        prebuffer_ms=20,
        max_turn_ms=1000,
    )
    return VoiceLoop(
        agent,
        _persona(),
        mic=mic,
        stt=stt,
        tts=tts,
        segmenter=segmenter,
        write=output.append,
    )


def test_one_turn_keeps_the_mic_off_while_speaking() -> None:
    mic = FakeMic([[TONE] * 20 + [SILENCE]])
    stt = FakeSTT(["hola"])
    tts = FakeTTS(mic)
    output: list[str] = []
    loop = _loop(mic, stt, tts, FakeAgent(["Hola. ", "¿Qué tal?"]), output)

    asyncio.run(loop._turn())

    assert mic.calls == ["start", "stop"]
    assert tts.heard_itself is False
    assert tts.phrases == ["Hola.", "¿Qué tal?"]
    assert stt.audios and stt.audios[0].startswith(b"RIFF")
    assert "tú> hola" in "".join(output)
    assert loop.supervisor.state is State.IDLE


def test_empty_transcriptions_are_ignored() -> None:
    mic = FakeMic([[TONE] * 20 + [SILENCE]])
    stt = FakeSTT([""])
    tts = FakeTTS(mic)
    output: list[str] = []
    loop = _loop(mic, stt, tts, FakeAgent(["Vale."]), output)

    asyncio.run(loop._turn())

    assert stt.audios
    assert tts.phrases == []
    assert "No te entendí" in "".join(output)
    assert "Vale." not in "".join(output)


def test_trivial_transcriptions_are_ignored() -> None:
    mic = FakeMic([[TONE] * 20 + [SILENCE]])
    stt = FakeSTT(["..."])
    tts = FakeTTS(mic)
    output: list[str] = []
    loop = _loop(mic, stt, tts, FakeAgent(["Vale."]), output)

    asyncio.run(loop._turn())

    assert stt.audios
    assert tts.phrases == []
    assert "No te entendí" in "".join(output)
    assert "tú>" not in "".join(output)
    assert loop.supervisor.state is State.IDLE
    mic = FakeMic([[TONE] * 20 + [SILENCE]])
    stt = FakeSTT([VoiceError("sin red. Solución: revisa la red")])
    tts = FakeTTS(mic)
    output: list[str] = []
    loop = _loop(mic, stt, tts, FakeAgent(["Vale."]), output)

    asyncio.run(loop._turn())

    assert "[AVISO] sin red" in "".join(output)
    assert tts.phrases == []
    assert loop.supervisor.state is State.IDLE


def test_cancelling_the_loop_closes_mic_and_tts() -> None:
    mic = FakeMic()
    tts = FakeTTS(mic)
    loop = _loop(mic, FakeSTT([]), tts, FakeAgent(["Vale."]), [])

    async def scenario() -> None:
        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.01)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await loop.close()

    asyncio.run(scenario())
    assert mic.closed is True
    assert tts.closed is True


def test_voice_without_prerequisites_falls_back_to_text(tmp_path: Path, monkeypatch) -> None:
    called: list[object] = []

    async def fake_terminal(config, persona, **kwargs):
        called.append((config, persona, kwargs))
        return 7

    monkeypatch.setattr("sirah.voice._prerequisites", lambda config: [("falta x", "haz y")])
    monkeypatch.setattr("sirah.voice.run_terminal", fake_terminal)
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})
    output: list[str] = []

    result = asyncio.run(run_voice(config, _persona(), write=output.append))

    assert result == 7
    assert called
    assert "[FALLA] Voz: falta x" in "".join(output)
    assert "Solución: haz y" in "".join(output)
    assert "sigo por texto" in "".join(output)


def test_one_unspeakable_phrase_does_not_silence_the_rest() -> None:
    mic = FakeMic([[TONE] * 20 + [SILENCE]])
    tts = FlakyTTS(mic, {"..."})
    output: list[str] = []
    loop = _loop(mic, FakeSTT(["hola"]), tts, FakeAgent(["Claro. ", "... ", "Sigo aquí."]), output)

    asyncio.run(loop._turn())

    assert tts.phrases == ["Claro.", "...", "Sigo aquí."]
    assert "[AVISO] Piper no devolvió audio" in "".join(output)


def test_mic_failures_back_off_and_eventually_give_up(monkeypatch) -> None:
    mic = FakeMic()

    async def broken_start() -> None:
        raise VoiceError("El micrófono dejó de entregar audio. Solución: revisa el cable.")

    mic.start = broken_start
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) > 10:
            raise AssertionError("run() no se rindió nunca")

    monkeypatch.setattr("sirah.voice.asyncio.sleep", fake_sleep)
    loop = _loop(mic, FakeSTT([]), FakeTTS(mic), FakeAgent([]), [])

    with pytest.raises(VoiceError):
        asyncio.run(loop.run())

    assert delays == [1, 2, 4, 8]


def test_voice_falls_back_to_text_after_five_mic_failures(monkeypatch) -> None:
    mic = FakeMic()

    async def broken_start() -> None:
        raise VoiceError("El micrófono dejó de entregar audio. Solución: revisa el cable.")

    mic.start = broken_start
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) > 10:
            raise AssertionError("run() no se rindió nunca")

    async def fake_greeting(agent, persona, config) -> str:
        return ""

    called: list[dict[str, object]] = []

    async def fake_terminal(config, persona, **kwargs) -> int:
        called.append(kwargs)
        return 7

    monkeypatch.setattr("sirah.voice.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("sirah.voice._prerequisites", lambda config: [])
    monkeypatch.setattr("sirah.voice.ArecordMicrophone", lambda **kwargs: mic)
    monkeypatch.setattr("sirah.voice.build_agent", lambda *a, **k: (FakeAgent(["Vale."]), None))
    monkeypatch.setattr("sirah.voice.opening_greeting", fake_greeting)
    monkeypatch.setattr("sirah.voice.run_terminal", fake_terminal)
    config = load_config(
        env_file=Path("/tmp/sirah-missing.env"),
        environ={"LLM_API_KEY": "k", "STT_API_KEY": "k"},
    )
    output: list[str] = []

    result = asyncio.run(run_voice(config, _persona(), write=output.append))

    text = "".join(output)
    assert result == 7
    assert called
    assert delays == [1, 2, 4, 8]
    assert "Sigo por texto" in text
    assert "memoria" in text and "historial" in text
    assert mic.closed is True


def test_check_reports_rms_and_vad(tmp_path: Path, monkeypatch) -> None:
    mic = FakeMic()
    mic.turns = [[_level(3000)] * 50 + [_level(12000)] * 100]
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})
    output: list[str] = []

    result = asyncio.run(run_check(config, write=output.append, mic=mic))

    assert result == 0
    text = "".join(output)
    assert "Nivel RMS" in text
    assert "voz detectada" in text
    assert "Grabando 3 segundos" in text
    assert mic.closed is True


def test_prerequisites_name_the_piper_library(tmp_path: Path, monkeypatch) -> None:
    config = load_config(env_file=tmp_path / "missing.env", environ={})
    monkeypatch.setattr("sirah.voice.find_piper", lambda: None)

    problems = [problem for problem, _ in _prerequisites(config)]

    assert "falta la librería piper" in problems


def test_run_voice_uses_the_configured_player(tmp_path: Path, monkeypatch) -> None:
    seen: list[list[str]] = []

    class Boom(Exception):
        pass

    def fake_tts(model: str, **kwargs) -> None:
        seen.append(kwargs["aplay"])
        raise Boom

    monkeypatch.setattr("sirah.voice.PiperTTS", fake_tts)
    monkeypatch.setattr("sirah.voice._prerequisites", lambda config: [])
    config = load_config(
        env_file=tmp_path / "missing.env",
        environ={"LLM_API_KEY": "k", "AUDIO_PLAYER_COMMAND": "paplay --volume=30000"},
    )

    with pytest.raises(Boom):
        asyncio.run(run_voice(config, _persona(), write=[].append))

    assert seen == [["paplay", "--volume=30000"]]


def test_mic_banner_is_printed_after_the_greeting(tmp_path: Path, monkeypatch) -> None:
    async def fake_greeting(agent, persona, config) -> str:
        return "Hola."

    async def fake_run(self) -> None:
        return None

    async def fake_terminal(config, persona, **kwargs) -> int:
        return 0

    output: list[str] = []
    monkeypatch.setattr("sirah.voice._prerequisites", lambda config: [])
    monkeypatch.setattr("sirah.voice.ArecordMicrophone", lambda **kwargs: FakeMic())
    monkeypatch.setattr("sirah.voice.PiperTTS", lambda *a, **k: FakeTTS(FakeMic()))
    monkeypatch.setattr("sirah.voice.build_agent", lambda *a, **k: (FakeAgent([]), None))
    monkeypatch.setattr("sirah.voice.opening_greeting", fake_greeting)
    monkeypatch.setattr("sirah.voice.VoiceLoop.run", fake_run)
    monkeypatch.setattr("sirah.voice.run_terminal", fake_terminal)
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})

    asyncio.run(run_voice(config, _persona(), write=output.append))

    text = "".join(output)
    assert text.index("SIRAH> Hola.") < text.index("Micrófono activo")


class ScriptedSegmenter:
    """Devuelve descartes y un audio prefijados, sin depender del RMS."""

    def __init__(self, results: list[str | None]) -> None:
        self.results = list(results)
        self.last_discard: str | None = None
        self.detector = None

    def start_session(self) -> None:
        return None

    def reset(self) -> None:
        return None

    def feed(self, frame: bytes) -> bytes | None:
        if not self.results:
            return None
        result = self.results.pop(0)
        if result is None:
            return b"audio"
        self.last_discard = result
        return None


def _scripted_loop(results: list[str | None], output: list[str]) -> VoiceLoop:
    mic = FakeMic()
    return VoiceLoop(
        FakeAgent([]),
        _persona(),
        mic=mic,
        stt=FakeSTT([]),
        tts=FakeTTS(mic),
        segmenter=ScriptedSegmenter(results),  # type: ignore[arg-type]
        write=output.append,
    )


def test_discarded_short_turn_warns_the_user() -> None:
    output: list[str] = []
    loop = _scripted_loop(["short", None], output)

    assert asyncio.run(loop._listen()) == b"audio"
    assert "Te oí muy poco" in "".join(output)


def test_constant_noise_turn_warns_about_gain() -> None:
    output: list[str] = []
    loop = _scripted_loop(["noise", None], output)

    assert asyncio.run(loop._listen()) == b"audio"
    assert "ruido constante" in "".join(output)
    assert "ganancia" in "".join(output)


def test_high_noise_floor_warns_only_once() -> None:
    output: list[str] = []
    loop = _scripted_loop([None], output)
    loop.segmenter.detector = type(  # type: ignore[assignment]
        "Detector",
        (),
        {"pending_warning": "Baja la ganancia de captura."},
    )()

    asyncio.run(loop._listen())

    assert "".join(output).count("Baja la ganancia") == 1
    assert loop.segmenter.detector.pending_warning is None


def test_check_reports_the_adaptive_floor_and_thresholds(tmp_path: Path) -> None:
    mic = FakeMic()
    mic.turns = [[_level(3000)] * 50 + [_level(12000)] * 100]
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})
    output: list[str] = []

    assert asyncio.run(run_check(config, write=output.append, mic=mic)) == 0

    text = "".join(output)
    assert "Suelo de ruido: 3000" in text
    assert "umbrales inicio 4800" in text and "fin 3600" in text
    assert "voz detectada" in text


def test_check_high_floor_does_not_ask_to_raise_the_minimum(tmp_path: Path) -> None:
    mic = FakeMic()
    mic.turns = [[_level(3000)] * 50 + [_level(9000)] * 100]
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})
    output: list[str] = []

    asyncio.run(run_check(config, write=output.append, mic=mic))

    assert "sube VAD_MIN_START_RMS" not in "".join(output)


def _real_loop(mic: FakeMic, output: list[str]) -> VoiceLoop:
    segmenter = VoiceSegmenter(
        AdaptiveSpeechDetector(),
        start_frames=3,
        silence_ms=400,
        prebuffer_ms=300,
        max_turn_ms=10000,
    )
    return VoiceLoop(
        FakeAgent([]),
        _persona(),
        mic=mic,
        stt=FakeSTT([]),
        tts=FakeTTS(mic),
        segmenter=segmenter,
        write=output.append,
    )


def test_calibration_before_greeting_keeps_the_floor() -> None:
    mic = FakeMic(
        [
            [_level(3000)] * 35,
            [_level(12000)] * 40 + [SILENCE] * 25,
        ]
    )
    loop = _real_loop(mic, [])
    detector = loop.segmenter.detector

    asyncio.run(loop.calibrate())
    assert detector.noise_floor == 3000

    audio = asyncio.run(loop._listen())

    assert audio is not None
    # La voz posterior no sube el suelo; el silencio lo sigue bajando despacio.
    assert detector.noise_floor <= 3000


def test_run_voice_uses_the_autoselected_player(tmp_path: Path, monkeypatch) -> None:
    seen: list[list[str]] = []
    output: list[str] = []

    class Boom(Exception):
        pass

    def fake_tts(model: str, **kwargs) -> None:
        seen.append(kwargs["aplay"])
        raise Boom

    monkeypatch.setattr("sirah.voice.PiperTTS", fake_tts)
    monkeypatch.setattr("sirah.voice._prerequisites", lambda config: [])
    monkeypatch.setattr(
        "sirah.voice.resolve_player",
        lambda config: SimpleNamespace(
            command=("paplay",),
            message="aplay no responde con PipeWire; uso paplay. Fíjalo con AUDIO_PLAYER_COMMAND.",
        ),
    )
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})

    with pytest.raises(Boom):
        asyncio.run(run_voice(config, _persona(), write=output.append))

    assert seen == [["paplay"]]
    assert "[AVISO] aplay no responde con PipeWire; uso paplay." in "".join(output)


def test_run_voice_without_any_player_falls_back_to_text(tmp_path: Path, monkeypatch) -> None:
    output: list[str] = []

    async def fake_terminal(config, persona, **kwargs) -> int:
        return 4

    monkeypatch.setattr("sirah.voice._prerequisites", lambda config: [])
    monkeypatch.setattr(
        "sirah.voice.resolve_player",
        lambda config: SimpleNamespace(command=None, message="aplay se colgó"),
    )
    monkeypatch.setattr("sirah.voice.run_terminal", fake_terminal)
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})

    result = asyncio.run(run_voice(config, _persona(), write=output.append))

    assert result == 4
    text = "".join(output)
    assert "[FALLA] Audio: aplay se colgó" in text
    assert "sigo por texto" in text.lower()


def test_voice_calibrates_before_the_greeting(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    async def fake_calibrate(self) -> None:
        calls.append("calibrate")

    async def fake_greeting(agent, persona, config) -> str:
        calls.append("greeting")
        return "Hola."

    async def fake_speak(self, text: str) -> None:
        calls.append("speak")

    async def fake_run(self) -> None:
        calls.append("run")

    monkeypatch.setattr("sirah.voice._prerequisites", lambda config: [])
    monkeypatch.setattr(
        "sirah.voice.resolve_player", lambda config: SimpleNamespace(command=("aplay",), message="")
    )
    monkeypatch.setattr("sirah.voice.ArecordMicrophone", lambda **kwargs: FakeMic())
    monkeypatch.setattr("sirah.voice.PiperTTS", lambda *a, **k: FakeTTS(FakeMic()))
    monkeypatch.setattr("sirah.voice.build_agent", lambda *a, **k: (FakeAgent([]), None))
    monkeypatch.setattr("sirah.voice.VoiceLoop.calibrate", fake_calibrate)
    monkeypatch.setattr("sirah.voice.opening_greeting", fake_greeting)
    monkeypatch.setattr("sirah.voice.VoiceLoop.speak_greeting", fake_speak)
    monkeypatch.setattr("sirah.voice.VoiceLoop.run", fake_run)
    config = load_config(env_file=tmp_path / "missing.env", environ={"LLM_API_KEY": "k"})

    asyncio.run(run_voice(config, _persona(), write=[].append))

    assert calls[:3] == ["calibrate", "greeting", "speak"]
