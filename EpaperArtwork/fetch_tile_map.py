"""Fetch a small set of OSM raster tiles for an offline regional map preview.

This is a one-off build step. The renderer and e-paper device do not fetch tiles.
Respect OSM's tile usage policy: cache the tiles and do not use this as a bulk
downloader or regularly scheduled job.
"""

from __future__ import annotations

import argparse
import json
import math
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

from map_imagery import EARTH_RADIUS_M, ROOT, map_bbox


ZOOM = 10
TILE_PIXELS = 256
WORLD_M = 2 * math.pi * EARTH_RADIUS_M


def world_pixel(x: float, y: float, zoom: int) -> tuple[float, float]:
    pixels = TILE_PIXELS * 2 ** zoom
    return ((x + WORLD_M / 2) / WORLD_M * pixels,
            (WORLD_M / 2 - y) / WORLD_M * pixels)


def fetch(data: dict, destination: Path) -> None:
    config = data["map"]
    lat, lon, width = (float(config[key]) for key in ("latitude", "longitude", "width_km"))
    xmin, ymin, xmax, ymax = map_bbox(lat, lon, width)
    left, top = world_pixel(xmin, ymax, ZOOM)
    right, bottom = world_pixel(xmax, ymin, ZOOM)
    x0, x1 = math.floor(left / TILE_PIXELS), math.floor(right / TILE_PIXELS)
    y0, y1 = math.floor(top / TILE_PIXELS), math.floor(bottom / TILE_PIXELS)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 36:
        raise ValueError("Map would request too many tiles")
    atlas = Image.new("RGB", ((x1 - x0 + 1) * TILE_PIXELS, (y1 - y0 + 1) * TILE_PIXELS), "white")
    cache = ROOT / "output" / "osm-tile-cache" / str(ZOOM)
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            tile_path = cache / str(tx) / f"{ty}.png"
            if tile_path.is_file():
                tile_bytes = tile_path.read_bytes()
            else:
                response = requests.get(f"https://tile.openstreetmap.org/{ZOOM}/{tx}/{ty}.png",
                                        headers={"User-Agent": "EpaperArtwork/0.1 (one-off personal preview)"},
                                        timeout=25)
                response.raise_for_status()
                if len(response.content) > 1_000_000:
                    raise ValueError("Unexpectedly large map tile")
                tile_bytes = response.content
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                tile_path.write_bytes(tile_bytes)
            with Image.open(BytesIO(tile_bytes)) as tile:
                if tile.size != (TILE_PIXELS, TILE_PIXELS):
                    raise ValueError("Unexpected tile dimensions")
                atlas.paste(tile.convert("RGB"), ((tx - x0) * TILE_PIXELS, (ty - y0) * TILE_PIXELS))
    crop = atlas.crop((left - x0 * TILE_PIXELS, top - y0 * TILE_PIXELS,
                       right - x0 * TILE_PIXELS, bottom - y0 * TILE_PIXELS))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep source pixels intact: monochrome road extraction must happen before
    # scaling down to 800×480 or thin roads break into dashes.
    crop.save(destination)
    destination.with_suffix(".json").write_text(json.dumps({
        "latitude": lat, "longitude": lon, "width_km": width, "zoom": ZOOM,
        "source_size": crop.size,
        "attribution": "© OpenStreetMap contributors, ODbL",
        "source": "https://www.openstreetmap.org/copyright",
    }, indent=2), encoding="utf-8")
    print(f"Saved {destination} from {(x1 - x0 + 1) * (y1 - y0 + 1)} cached/fetched tiles")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "tile-map-source.png")
    args = parser.parse_args()
    fetch(json.loads(args.data.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
