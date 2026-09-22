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
from PIL import Image, ImageFilter, ImageOps, ImageStat


LOG = logging.getLogger("e1001.artwork")
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "output" / "daily-artwork"
SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
USER_AGENT = "E1001-Living-Artwork/1.0 (private non-commercial display)"
SELECTION_VERSION = 2

# Drawings and Prints (department 9) is deliberately favoured: its strong
# lines and restrained tones survive a four-grey 800x480 display much better
# than a random sample of the whole collection.
SEARCHES = (
    {"departmentId": 9, "q": "landscape"},
    {"departmentId": 9, "q": "architecture"},
    {"departmentId": 9, "q": "countryside"},
    {"departmentId": 9, "q": "garden"},
    {"departmentId": 9, "q": "trees"},
    {"departmentId": 9, "q": "river"},
    {"departmentId": 6, "q": "landscape woodblock print"},
)


def _seed(day: date) -> int:
    return int.from_bytes(hashlib.sha256(day.isoformat().encode()).digest()[:8], "big")


def _write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _paths(day: date) -> tuple[Path, Path]:
    return CACHE / f"{day.isoformat()}.jpg", CACHE / f"{day.isoformat()}.json"


def _load(metadata_path: Path, *, current_only: bool = False) -> dict | None:
    if not metadata_path.is_file():
        return None
    try:
        record = json.loads(metadata_path.read_text(encoding="utf-8"))
        if current_only and record.get("selection_version") != SELECTION_VERSION:
            return None
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


def _download_image(session: requests.Session, urls: list[str]) -> tuple[bytes, Image.Image, str]:
    """Try the web derivative, then the original when The Met returns 406."""
    last_error: Exception | None = None
    for url in dict.fromkeys(urls):
        try:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != "images.metmuseum.org":
                raise ValueError("Refusing unexpected artwork image host")
            # The JSON API session advertises application/json. The image CDN
            # correctly answers 406 to that media type, so override it here.
            response = session.get(url, timeout=(5, 25), stream=True,
                                   headers={"Accept": "image/*,*/*;q=0.8"})
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
            return payload, image, url
        except (OSError, ValueError, requests.RequestException) as exc:
            last_error = exc
    raise RuntimeError(f"No usable Met image URL: {last_error}")


def suitability(image: Image.Image) -> tuple[bool, str]:
    """Judge the work after reducing it to approximately the panel's scale."""
    width, height = image.size
    aspect = width / height
    if width < 650 or height < 320:
        return False, "source is too small"
    # The display artwork region is almost 2:1. Restricting the source to a
    # landscape composition lets a modest centre crop fill it without either
    # huge side margins or destructive portrait-to-landscape cropping.
    if not 1.45 <= aspect <= 2.45:
        return False, f"aspect {aspect:.2f} is not display-friendly"
    preview = ImageOps.fit(ImageOps.autocontrast(image.copy(), cutoff=1),
                           (390, 195), Image.Resampling.LANCZOS)
    softened = preview.filter(ImageFilter.GaussianBlur(0.8))
    stats = ImageStat.Stat(softened)
    if stats.stddev[0] < 20:
        return False, "insufficient tonal separation"
    if stats.mean[0] < 105:
        return False, "image is too dark for the panel"
    edges = softened.filter(ImageFilter.FIND_EDGES).crop((2, 2, 388, 193))
    pixels = list(edges.getdata())
    edge_ratio = sum(value > 40 for value in pixels) / len(pixels)
    if edge_ratio > 0.23:
        return False, f"detail density {edge_ratio:.2f} is too high"
    return True, f"aspect {aspect:.2f}, detail density {edge_ratio:.2f}"


def _fetch(day: date) -> dict:
    rng = random.Random(_seed(day))
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    searches = list(SEARCHES)
    rng.shuffle(searches)
    for specification in searches[:4]:
        search = dict(specification)
        search.update(hasImages="true", limit=100)
        response = session.get(SEARCH_URL, params=search, timeout=(5, 20))
        response.raise_for_status()
        result = response.json()
        total = min(int(result.get("total", 0)), 10_000)
        if total <= 0:
            continue
        offset = min((rng.randrange(total) // 100) * 100, max(0, total - 100))
        if offset:
            search["offset"] = offset
            response = session.get(SEARCH_URL, params=search, timeout=(5, 20))
            response.raise_for_status()
            result = response.json()
        object_ids = list(result.get("objectIDs") or [])
        rng.shuffle(object_ids)

        for object_id in object_ids[:15]:
            try:
                response = session.get(OBJECT_URL.format(object_id=int(object_id)), timeout=(5, 20))
                response.raise_for_status()
                item = response.json()
                # Prefer the original: web-large derivatives are often only
                # 600 px wide, which is marginal after a landscape crop.
                image_urls = [url for url in (item.get("primaryImage"), item.get("primaryImageSmall")) if url]
                if not item.get("isPublicDomain") or not image_urls:
                    continue
                payload, image, image_url = _download_image(session, image_urls)
                accepted, reason = suitability(image)
                if not accepted:
                    LOG.info("Rejected Met object %s: %s", object_id, reason)
                    continue
                image_path, metadata_path = _paths(day)
                record = {
                    "selection_version": SELECTION_VERSION,
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
                    "display_quality": reason,
                }
                _write(image_path, payload)
                _write(metadata_path, json.dumps(record, indent=2, ensure_ascii=False).encode())
                record["image_path"] = str(image_path)
                LOG.info("Selected Met artwork %s (%s): %s", object_id, reason, record["title"])
                return record
            except (OSError, RuntimeError, ValueError, requests.RequestException) as exc:
                LOG.warning("Rejected Met object %s: %s", object_id, exc)
    raise RuntimeError("No suitable public-domain artwork found in the daily sample")


def daily_artwork(day: date) -> dict:
    """Return today's cached work, fetching it once; fall back to last-good."""
    CACHE.mkdir(parents=True, exist_ok=True)
    _, metadata_path = _paths(day)
    if record := _load(metadata_path, current_only=True):
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
