from __future__ import annotations

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.vision.speciesnet_client import speciesnet_client


def _configure_client(url: str, timeout: float) -> dict:
    settings = speciesnet_client.settings
    old = {
        "speciesnet_enabled": settings.speciesnet_enabled,
        "speciesnet_api_url": settings.speciesnet_api_url,
        "speciesnet_timeout_seconds": settings.speciesnet_timeout_seconds,
        "speciesnet_connect_timeout_seconds": settings.speciesnet_connect_timeout_seconds,
        "speciesnet_read_timeout_seconds": settings.speciesnet_read_timeout_seconds,
        "speciesnet_write_timeout_seconds": settings.speciesnet_write_timeout_seconds,
        "speciesnet_pool_timeout_seconds": settings.speciesnet_pool_timeout_seconds,
    }
    settings.speciesnet_enabled = True
    settings.speciesnet_api_url = url
    settings.speciesnet_timeout_seconds = timeout
    settings.speciesnet_connect_timeout_seconds = timeout
    settings.speciesnet_read_timeout_seconds = timeout
    settings.speciesnet_write_timeout_seconds = timeout
    settings.speciesnet_pool_timeout_seconds = timeout
    return old


def _restore_client(old: dict) -> None:
    for key, value in old.items():
        setattr(speciesnet_client.settings, key, value)


def test_speciesnet_unreachable_falls_back():
    old = _configure_client("http://127.0.0.1:9", 0.2)
    try:
        payload, warning = asyncio.run(
            speciesnet_client.safe_predict_image_bytes(
                b"not-a-real-image",
                filename="x.jpg",
                mime_type="image/jpeg",
            )
        )
    finally:
        _restore_client(old)
    assert payload is None
    assert warning


class SlowHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        time.sleep(0.4)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true, "result": {}}')

    def log_message(self, format, *args):  # noqa: A002, ANN001
        return


def test_speciesnet_timeout_falls_back():
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    old = _configure_client(f"http://127.0.0.1:{server.server_port}", 0.05)
    try:
        payload, warning = asyncio.run(
            speciesnet_client.safe_predict_image_bytes(
                b"small-image-bytes",
                filename="x.jpg",
                mime_type="image/jpeg",
            )
        )
    finally:
        _restore_client(old)
        server.shutdown()
        server.server_close()
    assert payload is None
    assert warning

