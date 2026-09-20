"""Extract a small, attributed sky catalog from HYG and Stellarium source files.

Run only when updating source data; the renderer uses the compact JSON offline.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hyg_gz", type=Path)
    parser.add_argument("stellarium_index", type=Path)
    args = parser.parse_args()

    culture = json.loads(args.stellarium_index.read_text(encoding="utf-8"))
    constellations = []
    line_ids: set[int] = set()
    for item in culture["constellations"]:
        lines = [[int(hip) for hip in line if isinstance(hip, int)] for line in item.get("lines", [])]
        lines = [line for line in lines if len(line) >= 2]
        if not lines:
            continue
        line_ids.update(hip for line in lines for hip in line)
        constellations.append({
            "name": item.get("common_name", {}).get("native", item["iau"]),
            "iau": item["iau"],
            "lines": lines,
        })

    stars = {}
    with gzip.open(args.hyg_gz, "rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if not row["hip"] or not row["ra"] or not row["dec"] or not row["mag"]:
                continue
            hip = int(row["hip"])
            mag = float(row["mag"])
            if hip in line_ids or mag <= 4.2:
                stars[str(hip)] = [round(float(row["ra"]) * 15, 5), round(float(row["dec"]), 5), round(mag, 2)]

    constellations = [
        {**item, "lines": [[hip for hip in line if str(hip) in stars] for line in item["lines"]]}
        for item in constellations
    ]
    constellations = [
        {**item, "lines": [line for line in item["lines"] if len(line) >= 2]}
        for item in constellations
    ]
    constellations = [item for item in constellations if item["lines"]]
    output = {
        "attribution": "HYG Database v4.0 (CC BY-SA 4.0); Stellarium Western Sky Culture data (CC BY-SA)",
        "sources": [
            "https://github.com/astronexus/HYG-Database/tree/main/hyg/CURRENT",
            "https://github.com/Stellarium/stellarium-skycultures/tree/master/western",
        ],
        "stars": stars,
        "constellations": constellations,
    }
    destination = ROOT / "assets" / "sky" / "western-bright-stars.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(f"Saved {len(stars)} stars and {len(constellations)} constellations to {destination}")


if __name__ == "__main__":
    main()
