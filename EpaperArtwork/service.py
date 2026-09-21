"""NAS-hosted image service for the E1001, with direct Open-Meteo forecasts."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from frame_codec import FRAME_BYTES, pack_gray4
from live_data import ZONE, build_live_data, next_artwork_change
from open_meteo import fetch
from render_screens import ROOT, render_pages


LOG = logging.getLogger("e1001")
PAGES = ("portrait", "today", "map", "almanac", "constellations")
OUTPUT = ROOT / "output"
SNAPSHOT = OUTPUT / "live-weather.json"
PORT = int(os.environ.get("E1001_PORT", "8765"))
WEATHER_INTERVAL = timedelta(minutes=30)
FAILURE_RETRY = timedelta(minutes=5)
DISPLAY_GRACE_SECONDS = 30
state_lock = threading.Lock()
state: dict = {"pages": {}, "rendered_at": None, "last_error": None,
               "next_update_at": None}


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
    snapshot = None
    next_weather_at = datetime.now(ZONE)
    while True:
        now = datetime.now(ZONE)
        try:
            if snapshot is None or now >= next_weather_at:
                snapshot = fetch()
                atomic_write(SNAPSHOT, json.dumps(snapshot, separators=(",", ":")).encode())
                next_weather_at = datetime.now(ZONE) + WEATHER_INTERVAL
            render(snapshot)
        except Exception as exc:  # keep last good frames during API/network trouble
            LOG.exception("Weather/render failed; retaining last good frames")
            with state_lock:
                state["last_error"] = str(exc)
            if now >= next_weather_at:
                next_weather_at = datetime.now(ZONE) + FAILURE_RETRY
        now = datetime.now(ZONE)
        try:
            next_boundary = next_artwork_change(now)
        except Exception:
            LOG.exception("Could not calculate next artwork boundary; using weather schedule")
            next_boundary = next_weather_at
        deadline = min(next_weather_at, next_boundary)
        with state_lock:
            state["next_update_at"] = deadline
        # Wake just after the boundary, avoiding a millisecond-early render
        # which could otherwise select the outgoing daypart again.
        wait_seconds = max(1.0, (deadline - datetime.now(ZONE)).total_seconds() + 1.0)
        LOG.info("Next render at %s (%d seconds)", deadline.isoformat(), round(wait_seconds))
        threading.Event().wait(wait_seconds)


def next_check_seconds(deadline: datetime | None, now: datetime | None = None) -> int:
    """Tell the display when to check after the next planned server render."""
    if now is None:
        now = datetime.now(timezone.utc)
    if deadline is None:
        return int(WEATHER_INTERVAL.total_seconds())
    delay = math.ceil((deadline.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds())
    return max(30, min(int(WEATHER_INTERVAL.total_seconds()), delay + DISPLAY_GRACE_SECONDS))


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
                next_update_at = state["next_update_at"]
                payload = json.dumps({
                    "ready": len(state["pages"]) == len(PAGES),
                    "rendered_at": state["rendered_at"],
                    "last_error": state["last_error"],
                    "next_update_at": next_update_at.isoformat() if next_update_at else None,
                    "pages": list(state["pages"]),
                }).encode()
            self.send_bytes(200, payload, "application/json")
            return
        if path == "/manifest":
            with state_lock:
                manifest = {name: entry["etag"] for name, entry in state["pages"].items()}
                if manifest:
                    manifest["next_check_seconds"] = next_check_seconds(state["next_update_at"])
                payload = json.dumps(manifest).encode()
            self.send_bytes(200 if manifest else 503, payload, "application/json")
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
