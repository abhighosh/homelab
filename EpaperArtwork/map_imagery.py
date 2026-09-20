"""Fetch one attributed Sentinel-2 cloudless map image for offline rendering.

This is an explicit build step, not a network request made by the E1001.
The 2016 EOX layer is CC BY 4.0; see README for required attribution.
"""

from __future__ import annotations

import argparse
import json
import math
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parent
SIZE = (800, 480)
EARTH_RADIUS_M = 6378137.0
WMS_URL = "https://tiles.maps.eox.at/map"
LAYER = "s2cloudless_3857"


def mercator(latitude: float, longitude: float) -> tuple[float, float]:
    if not (-85 < latitude < 85 and -180 <= longitude <= 180):
        raise ValueError("Map centre is outside Web Mercator's useful range")
    lat = math.radians(latitude)
    return EARTH_RADIUS_M * math.radians(longitude), EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + lat / 2))


def map_bbox(latitude: float, longitude: float, width_km: float) -> tuple[float, float, float, float]:
    if not 5 <= width_km <= 200:
        raise ValueError("Map width must be between 5 and 200 km")
    x, y = mercator(latitude, longitude)
    half_width_m = width_km * 500
    half_height_m = half_width_m * SIZE[1] / SIZE[0]
    return (x - half_width_m, y - half_height_m, x + half_width_m, y + half_height_m)


def fetch(data: dict, destination: Path) -> None:
    config = data["map"]
    lat, lon = float(config["latitude"]), float(config["longitude"])
    width_km = float(config["width_km"])
    bbox = map_bbox(lat, lon, width_km)
    response = requests.get(WMS_URL, params={
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "LAYERS": LAYER, "STYLES": "", "SRS": "EPSG:3857",
        "BBOX": ",".join(f"{value:.2f}" for value in bbox),
        "WIDTH": SIZE[0], "HEIGHT": SIZE[1], "FORMAT": "image/jpeg",
    }, timeout=35)
    response.raise_for_status()
    if not response.headers.get("Content-Type", "").startswith("image/") or len(response.content) > 10_000_000:
        raise ValueError("WMS returned an unexpected response")
    with Image.open(BytesIO(response.content)) as source:
        source.load()
        if source.size != SIZE:
            raise ValueError(f"Unexpected WMS image size: {source.size}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.convert("RGB").save(destination, quality=93)
    destination.with_suffix(".json").write_text(json.dumps({
        "latitude": lat, "longitude": lon, "width_km": width_km,
        "bbox_epsg3857": bbox,
        "layer": LAYER,
        "attribution": "Sentinel-2 cloudless by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016), CC BY 4.0",
        "source": "https://cloudless.eox.at/",
    }, indent=2), encoding="utf-8")
    print(f"Saved {destination} and attribution metadata")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "satellite-source.jpg")
    args = parser.parse_args()
    fetch(json.loads(args.data.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
