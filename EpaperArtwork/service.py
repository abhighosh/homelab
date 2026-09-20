"""NAS-hosted image service for the E1001, with direct Open-Meteo forecasts."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from frame_codec import FRAME_BYTES, pack_gray4
from live_data import build_live_data
from open_meteo import fetch
from render_screens import ROOT, render_pages


LOG = logging.getLogger("e1001")
PAGES = ("portrait", "today", "map", "almanac", "constellations")
OUTPUT = ROOT / "output"
SNAPSHOT = OUTPUT / "live-weather.json"
PORT = int(os.environ.get("E1001_PORT", "8765"))
state_lock = threading.Lock()
state: dict = {"pages": {}, "rendered_at": None, "last_error": None}


def atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def render(snapshot: dict) -> None:
    data = build_live_data(snapshot)
    images = render_pages(data)
    pages = {}
    for name, image in images.items():
        raw = pack_gray4(image)
        if len(raw) != FRAME_BYTES:
            raise ValueError("Bad Gray4 frame size")
        png = io.BytesIO()
        image.save(png, format="PNG", optimize=True)
        pages[name] = {
            "g4": raw, "png": png.getvalue(),
            "etag": hashlib.sha256(raw).hexdigest()[:16],
        }
    for name, entry in pages.items():
        atomic_write(OUTPUT / f"live-{name}.g4", entry["g4"])
        atomic_write(OUTPUT / f"live-{name}.png", entry["png"])
    with state_lock:
        state.update(pages=pages, rendered_at=datetime.now(timezone.utc).isoformat(), last_error=None)
    LOG.info("Rendered %d pages from fresh Open-Meteo weather", len(pages))


def worker() -> None:
    while True:
        try:
            snapshot = fetch()
            atomic_write(SNAPSHOT, json.dumps(snapshot, separators=(",", ":")).encode())
            render(snapshot)
        except Exception as exc:  # keep last good frames during API/network trouble
            LOG.exception("Weather/render failed; retaining last good frames")
            with state_lock:
                state["last_error"] = str(exc)
        threading.Event().wait(30 * 60)


def restore_cached_frames() -> None:
    pages = {}
    for name in PAGES:
        raw_path = OUTPUT / f"live-{name}.g4"
        png_path = OUTPUT / f"live-{name}.png"
        if not raw_path.is_file() or not png_path.is_file():
            return
        raw = raw_path.read_bytes()
        if len(raw) != FRAME_BYTES:
            return
        pages[name] = {
            "g4": raw, "png": png_path.read_bytes(),
            "etag": hashlib.sha256(raw).hexdigest()[:16],
        }
    with state_lock:
        state.update(pages=pages, rendered_at=datetime.fromtimestamp(
            max((OUTPUT / f"live-{name}.g4").stat().st_mtime for name in PAGES), timezone.utc).isoformat())
    LOG.info("Restored %d last-good screens from disk", len(pages))


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status: int, payload: bytes, mime: str, etag: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            with state_lock:
                payload = json.dumps({
                    "ready": len(state["pages"]) == len(PAGES),
                    "rendered_at": state["rendered_at"],
                    "last_error": state["last_error"],
                    "pages": list(state["pages"]),
                }).encode()
            self.send_bytes(200, payload, "application/json")
            return
        if path == "/manifest":
            with state_lock:
                payload = json.dumps({name: entry["etag"] for name, entry in state["pages"].items()}).encode()
            self.send_bytes(200 if payload != b"{}" else 503, payload, "application/json")
            return
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] in {"frame", "preview"}:
            stem, _, extension = parts[1].rpartition(".")
            expected = "g4" if parts[0] == "frame" else "png"
            if stem in PAGES and extension == expected:
                with state_lock:
                    entry = state["pages"].get(stem)
                if entry:
                    self.send_bytes(200, entry[expected],
                                    "application/octet-stream" if expected == "g4" else "image/png",
                                    entry["etag"])
                    return
                self.send_error(503, "Waiting for first weather forecast")
                return
        self.send_error(404)

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    restore_cached_frames()
    threading.Thread(target=worker, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    LOG.info("Listening on port %d; weather fetched directly on NAS", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
