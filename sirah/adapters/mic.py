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
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail = b""

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
                # Se drena en segundo plano para no bloquear la captura si
                # arecord llena el pipe de 64 KB con avisos.
                stderr=asyncio.subprocess.PIPE,
            )
            self._stderr_tail = b""
            self._stderr_task = asyncio.create_task(self._drain_stderr(self._process))
        except OSError as exc:
            raise VoiceError(
                "No se pudo abrir el micrófono. Solución: instala alsa-utils "
                "(`sudo apt install alsa-utils`) y revisa `arecord -l` y "
                "AUDIO_INPUT_DEVICE."
            ) from exc

    async def _stderr_hint(self, process: asyncio.subprocess.Process) -> str:
        """Última línea que dijo `arecord`, para no perder la causa real."""
        # El drenado corre en paralelo y mantiene las últimas líneas.
        raw = self._stderr_tail
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
        task = self._stderr_task
        self._stderr_task = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except TimeoutError:
                process.kill()
                with contextlib.suppress(ProcessLookupError):
                    await process.wait()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> None:
        if process.stderr is None:
            return
        try:
            while True:
                chunk = await process.stderr.read(4096)
                if not chunk:
                    break
                self._stderr_tail = (self._stderr_tail + chunk)[-4096:]
        except asyncio.CancelledError:
            raise
        except OSError:
            pass

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
