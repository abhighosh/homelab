"""Build and validate E1001 previews for every selected artwork asset."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from prepare_art import LEVELS, SIZE, prepare


ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "artwork-selection.json"


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    expected = {
        f"{part}_{weather}"
        for part in catalog["dayparts"]
        for weather in catalog["weather_groups"]
    }
    if set(catalog["variants"]) != expected:
        missing = sorted(expected - set(catalog["variants"]))
        extra = sorted(set(catalog["variants"]) - expected)
        raise ValueError(f"Incomplete weather/time matrix; missing={missing}, extra={extra}")

    entries = {**catalog["variants"], **catalog["special_editions"]}
    for name, entry in entries.items():
        source = ROOT / entry["path"]
        if not source.is_file():
            raise FileNotFoundError(f"{name}: {source}")
        target = ROOT / "output" / f"{source.stem}-e1001.png"
        prepare(source, target)
        with Image.open(target) as preview:
            if preview.size != SIZE or set(preview.getdata()) - set(LEVELS):
                raise ValueError(f"Invalid four-tone preview: {target}")
    print(f"Prepared and checked {len(entries)} E1001 previews")


if __name__ == "__main__":
    main()
