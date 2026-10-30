from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from sirah.adapters.mic import ArecordMicrophone
from sirah.core.voice import FRAME_BYTES, VoiceError

_SCRIPT = """\
import os
import sys
import time
from pathlib import Path

log = Path(sys.argv[1])
pid = Path(sys.argv[2])
frames = int(sys.argv[3])
pid.write_text(str(os.getpid()))
with log.open("a", encoding="utf-8") as handle:
    handle.write("start\\n")
sys.stdout.buffer.write(b"\\x00\\x10" * (320 * frames))
sys.stdout.buffer.flush()
time.sleep(10)
"""


def _script(tmp_path: Path) -> tuple[str, Path, Path]:
    path = tmp_path / "fake_arecord.py"
    path.write_text(_SCRIPT, encoding="utf-8")
    log = tmp_path / "arecord.log"
    pidfile = tmp_path / "arecord.pid"
    return str(path), log, pidfile


def test_record_returns_frames_and_stops_the_process(tmp_path: Path) -> None:
    path, log, pidfile = _script(tmp_path)

    async def scenario() -> list[bytes]:
        mic = ArecordMicrophone(command=[sys.executable, path, str(log), str(pidfile), "150"])
        return await mic.record(3.0)

    frames = asyncio.run(scenario())
    assert len(frames) == 150
    assert all(len(frame) == FRAME_BYTES for frame in frames)
    assert log.read_text(encoding="utf-8").splitlines() == ["start"]

    pid = int(pidfile.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("arecord falso sigue vivo tras record()")


def test_close_kills_a_microphone_that_keeps_capturing(tmp_path: Path) -> None:
    path, log, pidfile = _script(tmp_path)

    async def scenario() -> None:
        mic = ArecordMicrophone(command=[sys.executable, path, str(log), str(pidfile), "1"])
        await mic.start()
        assert await mic.read_frame()
        await mic.close()

    asyncio.run(scenario())
    pid = int(pidfile.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    pytest.fail("arecord falso sigue vivo tras close()")


def test_read_frame_without_start_is_actionable() -> None:
    mic = ArecordMicrophone()
    with pytest.raises(VoiceError, match="Solución"):
        asyncio.run(mic.read_frame())


def test_close_is_not_blocked_by_unread_stderr(tmp_path: Path) -> None:
    """arecord puede llenar el pipe de stderr: cerrar debe seguir siendo rápido."""
    script = tmp_path / "noisy_arecord.py"
    script.write_text(
        "import sys, time\nsys.stderr.write('x' * 200000)\nsys.stderr.flush()\ntime.sleep(10)\n",
        encoding="utf-8",
    )

    async def scenario() -> float:
        mic = ArecordMicrophone(command=[sys.executable, str(script)])
        await mic.start()
        started = time.monotonic()
        await mic.close()
        return time.monotonic() - started

    assert asyncio.run(scenario()) < 2.0


def test_a_dead_capture_reports_what_arecord_said(tmp_path: Path) -> None:
    script = tmp_path / "dead_arecord.py"
    script.write_text(
        'import sys\nsys.stderr.write("arecord: main:1234: audio open error: Device busy\\n")\n',
        encoding="utf-8",
    )

    async def scenario() -> str:
        mic = ArecordMicrophone(command=[sys.executable, str(script)])
        await mic.start()
        try:
            await mic.read_frame()
        finally:
            await mic.stop()
        raise AssertionError("read_frame debía fallar")

    with pytest.raises(VoiceError) as info:
        asyncio.run(scenario())

    assert "Device busy" in str(info.value)
    assert "Solución" in str(info.value)
