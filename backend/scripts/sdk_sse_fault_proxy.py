"""Loopback-only SSE fault proxy for SDK end-to-end verification.

For each run-event URL the first two successful SSE responses are truncated
after one complete event frame.  All other traffic is forwarded unchanged.
The proxy is an explicit development fixture; it is never imported by the API.
"""
from __future__ import annotations

import argparse
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlsplit

import httpx


class FaultProxyHandler(BaseHTTPRequestHandler):
    upstreams: list[str] = []
    disconnects_per_run: int = 2
    _counts: dict[str, int] = {}
    _upstream_index = 0
    _lock = threading.Lock()

    def log_message(self, _format: str, *args: object) -> None:
        # Query strings contain signed trace tokens; never emit request logs.
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path == "/__health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"healthy"}')
            return
        self._forward()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._forward()

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None
        with self._lock:
            upstream = self.upstreams[self._upstream_index % len(self.upstreams)]
            self.__class__._upstream_index += 1
        target = urljoin(upstream.rstrip("/") + "/", self.path.lstrip("/"))
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        with httpx.Client(timeout=None) as client:
            with client.stream(self.command, target, headers=headers, content=body) as response:
                self.send_response(response.status_code)
                for key, value in response.headers.items():
                    if key.lower() in {
                        "connection", "content-length", "content-encoding", "transfer-encoding"
                    }:
                        continue
                    self.send_header(key, value)
                self.end_headers()

                is_events = (
                    self.command == "GET"
                    and urlsplit(self.path).path.endswith("/events")
                    and response.status_code == 200
                    and response.headers.get("content-type", "").startswith("text/event-stream")
                )
                should_disconnect = False
                if is_events:
                    key = urlsplit(self.path).path
                    with self._lock:
                        count = self._counts.get(key, 0)
                        if count < self.disconnects_per_run:
                            self._counts[key] = count + 1
                            should_disconnect = True

                if should_disconnect:
                    buffer = b""
                    for chunk in response.iter_raw():
                        buffer += chunk.replace(b"\r\n", b"\n")
                        boundary = buffer.find(b"\n\n")
                        if boundary >= 0:
                            self.wfile.write(buffer[: boundary + 2])
                            self.wfile.flush()
                            self.close_connection = True
                            return
                    return

                for chunk in response.iter_raw():
                    self.wfile.write(chunk)
                    self.wfile.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True, action="append")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--disconnects-per-run", type=int, default=2)
    args = parser.parse_args()
    FaultProxyHandler.upstreams = args.upstream
    FaultProxyHandler.disconnects_per_run = args.disconnects_per_run
    server = ThreadingHTTPServer(("127.0.0.1", args.port), FaultProxyHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
