"""Loopback-only HTTP status server for the teleop demo harness.

The server exposes exactly one read-only route, `GET /v1/status`. It binds
`127.0.0.1` only, accepts no request body and has no stop, lease or motion
endpoint. Stop authority stays in `jcheng-system`.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any, Callable


class StatusServer:
    def __init__(
        self,
        snapshot: Callable[[], dict[str, Any]],
        *,
        port: int = 0,
        host: str = "127.0.0.1",
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("the teleop status server must bind loopback only")
        if port < 0 or port > 65535:
            raise ValueError("port must be in 0..65535")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib naming
                if self.path.split("?", 1)[0] != "/v1/status":
                    self.send_error(404)
                    return
                try:
                    body = json.dumps(snapshot(), sort_keys=True).encode("utf-8")
                except Exception as exc:  # a status failure is a 500, not a crash
                    self.send_error(500, str(exc))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                self.send_error(405)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self.host = host
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="jcheng-teleop-status", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2.0)
