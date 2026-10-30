"""Micrófono ALSA por `arecord`: frames PCM crudos de 20 ms."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence

from sirah.core.voice import FRAME_BYTES, FRAME_MS, SAMPLE_RATE, VoiceError


class ArecordMicrophone:
    """Un proceso `arecord` por turno; pararlo vacía el buffer de la pausa."""

    def __init__(
        self,
        *,
        device: str = "",
        command: Sequence[str] | None = None,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self.device = device
        self.sample_rate = sample_rate
        self._command = list(command or ["arecord"])
        self._process: asyncio.subprocess.Process | None = None

    def _args(self) -> list[str]:
        args = [
            *self._command,
            "-q",
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-r",
            str(self.sample_rate),
            "-c",
            "1",
        ]
        if self.device:
            args += ["-D", self.device]
        return args

    async def start(self) -> None:
        await self.stop()
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._args(),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                # Los avisos de arecord son pocos; si llenaran el pipe de 64 KB,
                # el proceso se bloquearía (shortcut: drenar stderr si algún día pasa).
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise VoiceError(
                "No se pudo abrir el micrófono. Solución: instala alsa-utils "
                "(`sudo apt install alsa-utils`) y revisa `arecord -l` y "
                "AUDIO_INPUT_DEVICE."
            ) from exc

    async def _stderr_hint(self, process: asyncio.subprocess.Process) -> str:
        """Última línea que dijo `arecord`, para no perder la causa real."""
        if process.stderr is None:
            return ""
        try:
            raw = await asyncio.wait_for(process.stderr.read(), timeout=0.5)
        except (TimeoutError, OSError):
            return ""
        lines = [line.strip() for line in raw.decode(errors="replace").splitlines() if line.strip()]
        return f" ({lines[-1]})" if lines else ""

    async def read_frame(self) -> bytes:
        process = self._process
        if process is None or process.stdout is None:
            raise VoiceError("El micrófono no está activo. Solución: reinicia `sirah voice`.")
        try:
            return await process.stdout.readexactly(FRAME_BYTES)
        except asyncio.IncompleteReadError as exc:
            hint = await self._stderr_hint(process)
            raise VoiceError(
                f"El micrófono dejó de entregar audio{hint}. Solución: revisa el cable, "
                "`arecord -l` y AUDIO_INPUT_DEVICE."
            ) from exc

    async def stop(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            process.kill()
            with contextlib.suppress(ProcessLookupError):
                await process.wait()

    async def record(self, seconds: float = 3.0) -> list[bytes]:
        await self.start()
        frames: list[bytes] = []
        try:
            for _ in range(int(seconds * 1000 / FRAME_MS)):
                frames.append(await self.read_frame())
        finally:
            await self.stop()
        return frames

    async def close(self) -> None:
        await self.stop()
