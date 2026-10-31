from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from sirah.adapters.tts import PiperTTS, player_arguments
from sirah.core.voice import VoiceError

PCM = b"\x00\x10" * 400

_APLAY = """\
import os
import sys
import time
from pathlib import Path

log = Path(sys.argv[1])
pidfile = Path(sys.argv[2])
dump = Path(sys.argv[3])
pidfile.write_text(str(os.getpid()))
audio = sys.stdin.buffer.read()
dump.write_bytes(audio)
with log.open("a", encoding="utf-8") as handle:
    handle.write(f"aplay-start {time.time()}\\n")
time.sleep(0.3)
with log.open("a", encoding="utf-8") as handle:
    handle.write(f"aplay-end {time.time()}\\n")
"""


class FakeVoice:
    """Imita `PiperVoice.synthesize`: tarda y devuelve chunks con PCM."""

    def __init__(self, pcm: bytes = PCM, delay: float = 0.0, fail: bool = False) -> None:
        self.pcm = pcm
        self.delay = delay
        self.fail = fail
        self.events: list[tuple[str, str, float]] = []

    def synthesize(self, text: str):
        self.events.append(("start", text, time.monotonic()))
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("modelo roto")
        if self.pcm:
            self.events.append(("end", text, time.monotonic()))
            yield SimpleNamespace(sample_rate=22050, audio_int16_bytes=self.pcm)


def _tts(tmp_path: Path, voice: FakeVoice | None) -> tuple[PiperTTS, Path, Path, Path]:
    aplay = tmp_path / "fake_aplay.py"
    aplay.write_text(_APLAY, encoding="utf-8")
    log = tmp_path / "tts.log"
    pidfile = tmp_path / "aplay.pid"
    dump = tmp_path / "played.wav"
    tts = PiperTTS(
        str(tmp_path / "modelo.onnx"),
        voice=voice,
        aplay=[sys.executable, str(aplay), str(log), str(pidfile), str(dump)],
    )
    return tts, log, pidfile, dump


def test_says_each_phrase_and_prepares_the_next_while_playing(tmp_path: Path) -> None:
    voice = FakeVoice(delay=0.1)
    tts, log, _, _ = _tts(tmp_path, voice)
    asyncio.run(tts.say("Uno. Dos."))

    end_second = next(at for kind, text, at in voice.events if kind == "end" and text == "Dos.")
    lines = log.read_text(encoding="utf-8").splitlines()
    aplay_ends = [float(line.split()[-1]) for line in lines if line.startswith("aplay-end")]
    first_aplay_end = aplay_ends[0]
    assert end_second < first_aplay_end
    assert sum(line.startswith("aplay-start") for line in lines) == 2


def test_aplay_receives_a_valid_wav_at_the_model_rate(tmp_path: Path) -> None:
    tts, _, _, dump = _tts(tmp_path, FakeVoice(pcm=PCM))
    asyncio.run(tts.say("Hola."))

    with wave.open(io.BytesIO(dump.read_bytes()), "rb") as wav:
        assert wav.getframerate() == 22050
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.readframes(wav.getnframes()) == PCM


def test_silence_is_not_synthesized(tmp_path: Path) -> None:
    voice = FakeVoice()
    tts, log, _, _ = _tts(tmp_path, voice)
    asyncio.run(tts.say("   "))
    assert voice.events == []
    assert not log.exists()


def test_phrases_without_words_are_not_synthesized(tmp_path: Path) -> None:
    voice = FakeVoice()
    tts, log, _, _ = _tts(tmp_path, voice)
    asyncio.run(tts.say("Hola. ... Adiós."))

    assert [text for kind, text, _ in voice.events if kind == "start"] == ["Hola.", "Adiós."]
    assert log.read_text(encoding="utf-8").count("aplay-start") == 2


def test_missing_model_is_actionable(tmp_path: Path) -> None:
    tts, _, _, _ = _tts(tmp_path, None)
    with pytest.raises(VoiceError, match="sirah setup"):
        asyncio.run(tts.say("Hola."))


def test_synthesis_failure_is_actionable(tmp_path: Path) -> None:
    tts, _, _, _ = _tts(tmp_path, FakeVoice(fail=True))
    with pytest.raises(VoiceError, match="Solución"):
        asyncio.run(tts.say("Hola."))


def test_empty_synthesis_is_actionable(tmp_path: Path) -> None:
    tts, _, _, _ = _tts(tmp_path, FakeVoice(pcm=b""))
    with pytest.raises(VoiceError, match="no devolvió audio"):
        asyncio.run(tts.say("Hola."))


def test_missing_aplay_is_actionable(tmp_path: Path) -> None:
    tts = PiperTTS(
        str(tmp_path / "modelo.onnx"),
        voice=FakeVoice(),
        aplay=[str(tmp_path / "no-existe")],
    )
    with pytest.raises(VoiceError, match="alsa-utils"):
        asyncio.run(tts.say("Hola."))


def test_close_kills_aplay_that_keeps_playing(tmp_path: Path) -> None:
    tts, log, pidfile, _ = _tts(tmp_path, FakeVoice())
    deadline = time.monotonic() + 5

    async def scenario() -> None:
        task = asyncio.create_task(tts.say("Hola."))
        while not pidfile.exists():
            if time.monotonic() > deadline:
                pytest.fail("aplay falso no arrancó")
            await asyncio.sleep(0.01)
        await tts.close()
        task.cancel()
        with contextlib.suppress(BaseException):
            await task

    asyncio.run(scenario())
    pid = int(pidfile.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


_APLAY_HANG = """\
import os
import sys
import time
from pathlib import Path

Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(60)
"""


def test_aplay_that_never_exits_is_killed_and_reported(tmp_path: Path, monkeypatch) -> None:
    aplay = tmp_path / "hang.py"
    aplay.write_text(_APLAY_HANG, encoding="utf-8")
    pidfile = tmp_path / "hang.pid"
    monkeypatch.setattr("sirah.adapters.tts._PLAY_TIMEOUT_MARGIN_S", 0.2)
    tts = PiperTTS(
        str(tmp_path / "modelo.onnx"),
        voice=FakeVoice(),
        aplay=[sys.executable, str(aplay), str(pidfile)],
    )

    start = time.monotonic()
    with pytest.raises(VoiceError, match="no terminó"):
        asyncio.run(tts.say("Hola."))
    assert time.monotonic() - start < 5

    pid = int(pidfile.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


_STRICT = """\
#!{python}
import os
import sys
from pathlib import Path

allowed = set(os.environ["STRICT_ALLOWED"].split(","))
args = sys.argv[1:]
bad = [arg for arg in args if arg.startswith("--") and arg.split("=")[0] not in allowed]
if bad:
    print(f"opcion no soportada: {{bad[0]}}", file=sys.stderr)
    sys.exit(2)
Path(os.environ["STRICT_LOG"]).write_text(" ".join(args), encoding="utf-8")
Path(os.environ["STRICT_DUMP"]).write_bytes(sys.stdin.buffer.read())
"""


def _strict_player(tmp_path: Path, name: str, allowed: str, monkeypatch):
    script = tmp_path / name
    script.write_text(_STRICT.format(python=sys.executable), encoding="utf-8")
    script.chmod(0o755)
    log = tmp_path / f"{name}.log"
    dump = tmp_path / f"{name}.wav"
    monkeypatch.setenv("STRICT_ALLOWED", allowed)
    monkeypatch.setenv("STRICT_LOG", str(log))
    monkeypatch.setenv("STRICT_DUMP", str(dump))
    return script, log, dump


def test_player_arguments_are_specific_to_each_player() -> None:
    assert player_arguments(["aplay"]) == ["aplay", "-q"]
    assert player_arguments(["/usr/bin/aplay"], "plughw:0") == [
        "/usr/bin/aplay",
        "-q",
        "-D",
        "plughw:0",
    ]
    assert player_arguments(["paplay", "--volume=30000"], "sink") == [
        "paplay",
        "--volume=30000",
        "--device=sink",
    ]
    assert player_arguments(["pw-play"], "sink") == ["pw-play", "--target=sink", "-"]
    assert player_arguments(["mpv"], "sink") == ["mpv"]


def test_aplay_receives_only_its_own_options(tmp_path: Path, monkeypatch) -> None:
    script, log, dump = _strict_player(tmp_path, "aplay", "-q,-D", monkeypatch)
    tts = PiperTTS(
        str(tmp_path / "modelo.onnx"),
        voice=FakeVoice(),
        aplay=[str(script)],
        output_device="sink",
    )

    asyncio.run(tts.say("Hola."))

    assert log.read_text(encoding="utf-8") == "-q -D sink"
    assert dump.read_bytes().startswith(b"RIFF")


def test_paplay_receives_the_device_option_without_dash(tmp_path: Path, monkeypatch) -> None:
    script, log, dump = _strict_player(tmp_path, "paplay", "--device", monkeypatch)
    tts = PiperTTS(
        str(tmp_path / "modelo.onnx"),
        voice=FakeVoice(),
        aplay=[str(script)],
        output_device="sink",
    )

    asyncio.run(tts.say("Hola."))

    assert log.read_text(encoding="utf-8") == "--device=sink"
    assert dump.read_bytes().startswith(b"RIFF")


def test_pw_play_receives_the_target_option_and_stdin_marker(tmp_path: Path, monkeypatch) -> None:
    script, log, dump = _strict_player(tmp_path, "pw-play", "--target", monkeypatch)
    tts = PiperTTS(
        str(tmp_path / "modelo.onnx"),
        voice=FakeVoice(),
        aplay=[str(script)],
        output_device="sink",
    )

    asyncio.run(tts.say("Hola."))

    assert log.read_text(encoding="utf-8") == "--target=sink -"
    assert dump.read_bytes().startswith(b"RIFF")


def test_unknown_player_gets_no_extra_options(tmp_path: Path, monkeypatch) -> None:
    script, log, dump = _strict_player(tmp_path, "mpv", "", monkeypatch)
    tts = PiperTTS(
        str(tmp_path / "modelo.onnx"),
        voice=FakeVoice(),
        aplay=[str(script)],
        output_device="sink",
    )

    asyncio.run(tts.say("Hola."))

    assert log.read_text(encoding="utf-8") == ""
    assert dump.read_bytes().startswith(b"RIFF")
