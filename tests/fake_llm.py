from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class FakeResponse:
    chunks: list[str] = field(default_factory=list)
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    delay: float = 0.0
    done: bool = True
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


class FakeLLM:
    """Servidor HTTP local que imita SSE de un endpoint OpenAI-compatible."""

    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.responses = responses or [FakeResponse(["Hola"])]
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.paths: list[str] = []
        self._index = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self) -> FakeLLM:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                owner.requests.append(payload)
                owner.headers.append(dict(self.headers))
                owner.paths.append(self.path)

                response = owner.responses[min(owner._index, len(owner.responses) - 1)]
                owner._index += 1

                if response.status != 200 or response.body:
                    data = response.body.encode("utf-8")
                    self.send_response(response.status)
                    for key, value in response.headers.items():
                        self.send_header(key, value)
                    if response.status == 200:
                        self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    for chunk in response.chunks:
                        event = json.dumps(
                            {"choices": [{"delta": {"content": chunk}}]},
                            ensure_ascii=False,
                        )
                        self.wfile.write(f"data: {event}\n\n".encode())
                        self.wfile.flush()
                        if response.delay:
                            time.sleep(response.delay)
                    if response.finish_reason or response.usage:
                        final: dict[str, Any] = {
                            "choices": [{"delta": {}, "finish_reason": response.finish_reason}]
                        }
                        if response.usage:
                            final["usage"] = response.usage
                        self.wfile.write(
                            f"data: {json.dumps(final, ensure_ascii=False)}\n\n".encode()
                        )
                        self.wfile.flush()
                    if response.done:
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
