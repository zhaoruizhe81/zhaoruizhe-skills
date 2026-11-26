#!/usr/bin/env python3
"""接收 Windows 侧回传的文件（HTTP PUT）。

用法:
    python3 recv_server.py            # 默认 :8778 -> out/recv/
    PORT=9000 DEST=/tmp/x python3 recv_server.py

Windows 侧:
    Invoke-WebRequest -Uri 'http://<MAC_IP>:8778/up?name=shot.png' -Method Put `
      -InFile "$env:USERPROFILE\\Desktop\\shot.png" -UseBasicParsing
"""
from __future__ import annotations

import http.server
import os
import pathlib
import socketserver
import urllib.parse

PORT = int(os.environ.get("PORT", "8778"))
DEST = pathlib.Path(os.environ.get("DEST", "out/recv"))


class Handler(http.server.BaseHTTPRequestHandler):
    def do_PUT(self) -> None:
        q = urllib.parse.urlparse(self.path)
        name = urllib.parse.parse_qs(q.query).get("name", ["upload.bin"])[0]
        name = os.path.basename(name) or "upload.bin"
        size = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(size)
        DEST.mkdir(parents=True, exist_ok=True)
        (DEST / name).write_bytes(data)
        print(f"saved {DEST / name} ({len(data)} bytes)", flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as srv:
        print(f"listening :{PORT} -> {DEST.resolve()}", flush=True)
        srv.serve_forever()
