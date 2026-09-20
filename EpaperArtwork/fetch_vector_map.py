"""Build a local, continuous road-line extract from Geofabrik county PBFs.

This is a one-off artwork build step, never run on the e-paper device.  It
downloads regional OSM extracts rather than bulk-fetching map tiles.
Requires pyosmium (``pip install osmium``) in the build environment.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import requests

from map_imagery import ROOT, map_bbox


COUNTIES = (
    "oxfordshire", "buckinghamshire", "northamptonshire", "berkshire",
    "bedfordshire", "warwickshire", "wiltshire", "gloucestershire",
    "hertfordshire",
)
BASE_URL = "https://download.geofabrik.de/europe/united-kingdom/england"
ROAD_CLASSES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "road", "motorway_link", "trunk_link",
    "primary_link", "secondary_link", "tertiary_link",
}


def fetch_pbf(county: str, cache: Path) -> Path:
    destination = cache / f"{county}-latest.osm.pbf"
    if destination.is_file() and destination.stat().st_size > 100_000:
        return destination
    cache.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    url = f"{BASE_URL}/{county}-latest.osm.pbf"
    with requests.get(url, stream=True, timeout=45,
                      headers={"User-Agent": "EpaperArtwork/0.1 (personal offline map preview)"}) as response:
        response.raise_for_status()
        length = int(response.headers.get("Content-Length", 0))
        if length > 120_000_000:
            raise ValueError(f"Unexpectedly large county extract: {county}")
        with temporary.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                output.write(chunk)
    temporary.replace(destination)
    print(f"Downloaded {county}: {destination.stat().st_size / 1e6:.1f} MB", flush=True)
    return destination


def build(data: dict, destination: Path, cache: Path, counties: tuple[str, ...] = COUNTIES) -> None:
    import osmium

    config = data["map"]
    lat, lon, width = (float(config[key]) for key in ("latitude", "longitude", "width_km"))
    xmin, ymin, xmax, ymax = map_bbox(lat, lon, width)
    # Slight padding avoids cutting ways at the picture edge.
    earth = 6378137.0
    west, east = math.degrees((xmin - 3000) / earth), math.degrees((xmax + 3000) / earth)
    south = math.degrees(2 * math.atan(math.exp((ymin - 3000) / earth)) - math.pi / 2)
    north = math.degrees(2 * math.atan(math.exp((ymax + 3000) / earth)) - math.pi / 2)
    seen: set[int] = set()
    features: list[dict] = []

    class Roads(osmium.SimpleHandler):
        def way(self, way) -> None:
            if way.id in seen:
                return
            road = way.tags.get("highway")
            rail = way.tags.get("railway")
            water = way.tags.get("waterway")
            if road not in ROAD_CLASSES and rail != "rail" and water not in {"river", "canal"}:
                return
            try:
                points = [[node.location.lat, node.location.lon] for node in way.nodes]
            except osmium.InvalidLocationError:
                return
            if len(points) < 2 or not any(south <= p[0] <= north and west <= p[1] <= east for p in points):
                return
            seen.add(way.id)
            kind, category = (("highway", road) if road in ROAD_CLASSES else
                              ("railway", rail) if rail == "rail" else ("waterway", water))
            features.append({"kind": kind, "class": category, "points": points})

        def node(self, node) -> None:
            place = node.tags.get("place")
            name = node.tags.get("name")
            if name and place in {"city", "town", "village"} and node.location.valid():
                if south <= node.location.lat <= north and west <= node.location.lon <= east:
                    features.append({"kind": "place", "class": place, "name": name,
                                     "latitude": node.location.lat, "longitude": node.location.lon})

    handler = Roads()
    for county in counties:
        source = fetch_pbf(county, cache)
        handler.apply_file(str(source), locations=True)
        print(f"Processed {county}; {len(seen)} unique lines", flush=True)
    if len(seen) < 1000:
        raise ValueError("Too few road lines; county data appears incomplete")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({
        "latitude": lat, "longitude": lon, "width_km": width,
        "source": "© OpenStreetMap contributors (ODbL), Geofabrik extract",
        "source_url": "https://www.openstreetmap.org/copyright",
        "features": features,
    }, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(features)} vector features to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "example-screen-data.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "road-network.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "output" / "geofabrik-cache")
    args = parser.parse_args()
    build(json.loads(args.data.read_text(encoding="utf-8")), args.output, args.cache)


if __name__ == "__main__":
    main()
