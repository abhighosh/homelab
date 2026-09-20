"""Fetch a small, public-area OpenStreetMap line extract for offline previews.

The chosen map bounds are sent to Overpass. Do not use private home coordinates
without permission. Nothing is fetched by the renderer or the e-paper device.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import requests

from map_imagery import EARTH_RADIUS_M, ROOT, map_bbox


OVERPASS_URL = "https://overpass.private.coffee/api/interpreter"


def inverse_mercator(x: float, y: float) -> tuple[float, float]:
    return (math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS_M)) - math.pi / 2),
            math.degrees(x / EARTH_RADIUS_M))


def fetch(data: dict, destination: Path) -> None:
    config = data["map"]
    lat, lon, width = (float(config[key]) for key in ("latitude", "longitude", "width_km"))
    xmin, ymin, xmax, ymax = map_bbox(lat, lon, width)
    south, west = inverse_mercator(xmin, ymin)
    north, east = inverse_mercator(xmax, ymax)
    broad = width > 40
    road_filter = ('["highway"~"^(motorway|trunk|primary|secondary|motorway_link|trunk_link|primary_link|secondary_link)$"]'
                   if broad else '["highway"]')
    place_filter = ('["place"~"^(city|town|village)$"]' if broad else
                    '["place"~"^(city|town|village|hamlet|suburb)$"]')
    def request_area(area: tuple[float, float, float, float]) -> list[dict]:
        box = ",".join(f"{number:.6f}" for number in area)
        local_pois = ("" if broad else
                      f'node["name"]["amenity"~"^(place_of_worship|school|library)$"]({box});'
                      f'node["name"]["railway"="station"]({box});'
                      f'way["name"]["amenity"~"^(place_of_worship|school|library)$"]({box});'
                      f'way["name"]["leisure"~"^(park|playground)$"]({box});'
                      f'way["name"]["tourism"~"^(museum|attraction)$"]({box});')
        query = (
            "[out:json][timeout:90];("
            f'way{road_filter}({box});'
            f'way["railway"="rail"]({box});'
            f'way["waterway"~"^(river|canal)$"]({box});'
            f'node{place_filter}({box});'
            f'{local_pois}'
            ");out center geom;"
        )
        tile_cache = ROOT / "output" / "road-tiles" / f"{hashlib.sha256(query.encode()).hexdigest()}.json"
        if tile_cache.is_file():
            return json.loads(tile_cache.read_text(encoding="utf-8"))
        for attempt in range(4):
            response = requests.get(OVERPASS_URL, params={"data": query},
                                    headers={"User-Agent": "EpaperArtwork/0.1 (local preview)"}, timeout=110)
            if response.status_code == 429 and attempt < 3:
                time.sleep(8 * (attempt + 1))
                continue
            response.raise_for_status()
            if len(response.content) > 20_000_000:
                raise ValueError("Overpass response was unexpectedly large")
            elements = response.json().get("elements", [])
            tile_cache.parent.mkdir(parents=True, exist_ok=True)
            tile_cache.write_text(json.dumps(elements, separators=(",", ":")), encoding="utf-8")
            return elements
        raise RuntimeError("Could not retrieve map tile")

    # Regional extents are tiled to avoid a single expensive Overpass query.
    divisions = 3 if broad else 1
    elements_by_id = {}
    for row in range(divisions):
        for column in range(divisions):
            area = (south + (north - south) * row / divisions,
                    west + (east - west) * column / divisions,
                    south + (north - south) * (row + 1) / divisions,
                    west + (east - west) * (column + 1) / divisions)
            for element in request_area(area):
                elements_by_id[(element["type"], element["id"])] = element
            if broad:
                print(f"Fetched region {row * divisions + column + 1}/{divisions ** 2}", flush=True)
                time.sleep(2)
    features = []
    for element in elements_by_id.values():
        tags = element.get("tags", {})
        if element["type"] == "way" and "geometry" in element:
            kind = next((key for key in ("highway", "railway", "waterway") if key in tags), None)
            if kind:
                features.append({"kind": kind, "class": tags[kind],
                                 "points": [[point["lat"], point["lon"]] for point in element["geometry"]]})
            elif "name" in tags and (kind := next((key for key in ("amenity", "leisure", "tourism") if key in tags), None)):
                centre = element.get("center")
                if centre:
                    features.append({"kind": kind, "class": tags[kind], "name": tags["name"],
                                     "latitude": centre["lat"], "longitude": centre["lon"]})
        elif element["type"] == "node" and "name" in tags:
            kind = next((key for key in ("place", "railway", "amenity") if key in tags), None)
            if kind:
                features.append({"kind": kind, "class": tags[kind], "name": tags["name"],
                                 "latitude": element["lat"], "longitude": element["lon"]})
    if len(features) < 100:
        raise ValueError("Too few mapped features returned for a useful road map")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"latitude": lat, "longitude": lon, "width_km": width,
                                       "source": "OpenStreetMap contributors (ODbL) via Overpass",
                                       "source_url": "https://www.openstreetmap.org/copyright",
                                       "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(features)} mapped features to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "road-network.json")
    args = parser.parse_args()
    fetch(json.loads(args.data.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
