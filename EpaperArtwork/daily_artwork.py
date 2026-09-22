"""Fetch and cache one e-paper-friendly public-domain Met artwork per day."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import random
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps, ImageStat


LOG = logging.getLogger("e1001.artwork")
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "output" / "daily-artwork"
SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
USER_AGENT = "E1001-Living-Artwork/1.0 (private non-commercial display)"

# Drawings and Prints (department 9) is deliberately favoured: its strong
# lines and restrained tones survive a four-grey 800x480 display much better
# than a random sample of the whole collection.
SEARCHES = (
    {"departmentId": 9, "q": "landscape"},
    {"departmentId": 9, "q": "architecture"},
    {"departmentId": 9, "q": "botanical"},
    {"departmentId": 9, "q": "garden"},
    {"departmentId": 9, "q": "trees"},
    {"departmentId": 9, "q": "birds"},
    {"departmentId": 6, "q": "woodblock print"},
)


def _seed(day: date) -> int:
    return int.from_bytes(hashlib.sha256(day.isoformat().encode()).digest()[:8], "big")


def _write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _paths(day: date) -> tuple[Path, Path]:
    return CACHE / f"{day.isoformat()}.jpg", CACHE / f"{day.isoformat()}.json"


def _load(metadata_path: Path) -> dict | None:
    try:
        record = json.loads(metadata_path.read_text(encoding="utf-8"))
        image_path = metadata_path.with_suffix(".jpg")
        if image_path.is_file():
            record["image_path"] = str(image_path)
            return record
    except (OSError, ValueError, TypeError):
        LOG.warning("Ignoring invalid artwork cache entry %s", metadata_path)
    return None


def _last_good() -> dict | None:
    if not CACHE.is_dir():
        return None
    for metadata_path in sorted(CACHE.glob("????-??-??.json"), reverse=True):
        if record := _load(metadata_path):
            return record
    return None


def _download_image(session: requests.Session, url: str) -> tuple[bytes, Image.Image]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "images.metmuseum.org":
        raise ValueError("Refusing unexpected artwork image host")
    response = session.get(url, timeout=(5, 25), stream=True)
    response.raise_for_status()
    length = int(response.headers.get("Content-Length", 0))
    if length > 15_000_000:
        raise ValueError("Artwork image is too large")
    payload = response.content
    if len(payload) > 15_000_000:
        raise ValueError("Artwork image is too large")
    with Image.open(io.BytesIO(payload)) as source:
        source.verify()
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    return payload, image


def _suitable(image: Image.Image) -> bool:
    width, height = image.size
    aspect = width / height
    if width < 500 or height < 300 or not 0.65 <= aspect <= 2.5:
        return False
    preview = ImageOps.autocontrast(image.copy(), cutoff=1)
    preview.thumbnail((400, 240))
    return ImageStat.Stat(preview).stddev[0] >= 22


def _fetch(day: date) -> dict:
    rng = random.Random(_seed(day))
    search = dict(SEARCHES[rng.randrange(len(SEARCHES))])
    search.update(hasImages="true", limit=100)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    response = session.get(SEARCH_URL, params=search, timeout=(5, 20))
    response.raise_for_status()
    result = response.json()
    total = min(int(result.get("total", 0)), 10_000)
    if total <= 0:
        raise RuntimeError("Met search returned no artworks")

    # A stable page offset provides far more variety than always sampling the
    # API's first hundred results, while staying within its documented window.
    offset = min((rng.randrange(total) // 100) * 100, max(0, total - 100))
    if offset:
        search["offset"] = offset
        response = session.get(SEARCH_URL, params=search, timeout=(5, 20))
        response.raise_for_status()
        result = response.json()
    object_ids = list(result.get("objectIDs") or [])
    rng.shuffle(object_ids)

    for object_id in object_ids[:18]:
        try:
            response = session.get(OBJECT_URL.format(object_id=int(object_id)), timeout=(5, 20))
            response.raise_for_status()
            item = response.json()
            image_url = item.get("primaryImageSmall") or item.get("primaryImage")
            if not item.get("isPublicDomain") or not image_url:
                continue
            payload, image = _download_image(session, image_url)
            if not _suitable(image):
                continue
            image_path, metadata_path = _paths(day)
            record = {
                "selected_for": day.isoformat(),
                "object_id": int(item["objectID"]),
                "title": (item.get("title") or "Untitled").strip(),
                "artist": (item.get("artistDisplayName") or item.get("culture") or "Unknown artist").strip(),
                "object_date": (item.get("objectDate") or "").strip(),
                "medium": (item.get("medium") or "").strip(),
                "department": (item.get("department") or "").strip(),
                "object_url": (item.get("objectURL") or "").strip(),
                "image_url": image_url,
                "source": "The Metropolitan Museum of Art Open Access",
            }
            _write(image_path, payload)
            _write(metadata_path, json.dumps(record, indent=2, ensure_ascii=False).encode())
            record["image_path"] = str(image_path)
            LOG.info("Selected Met artwork %s: %s", object_id, record["title"])
            return record
        except (OSError, ValueError, requests.RequestException) as exc:
            LOG.warning("Rejected Met object %s: %s", object_id, exc)
    raise RuntimeError("No suitable public-domain artwork found in the daily sample")


def daily_artwork(day: date) -> dict:
    """Return today's cached work, fetching it once; fall back to last-good."""
    CACHE.mkdir(parents=True, exist_ok=True)
    _, metadata_path = _paths(day)
    if record := _load(metadata_path):
        return record
    try:
        return _fetch(day)
    except Exception:
        fallback = _last_good()
        if fallback:
            LOG.exception("Artwork refresh failed; retaining cached Met artwork")
            fallback["stale_for"] = day.isoformat()
            return fallback
        raise
