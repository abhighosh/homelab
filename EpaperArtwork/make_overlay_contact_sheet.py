"""Build a labelled review sheet of foreground overlays at production scale."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from render_screens import (OVERLAY_DIR, ROOT, VISITOR_HEIGHTS, WEATHER_WIDTHS,
                            _paste_overlay, four_tone)


CELL = (400, 264)
PREVIEW = (400, 240)
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"


def prepared(variant: str) -> Image.Image:
    import json

    catalog = json.loads((ROOT / "artwork-selection.json").read_text(encoding="utf-8"))
    source = ROOT / catalog["variants"][variant]["path"]
    path = ROOT / "output" / f"{source.stem}-e1001.png"
    with Image.open(path) as image:
        return image.convert("L")


def main() -> None:
    items = (
        ("Autumn leaves", "day_clear", "weather", "leaves"),
        ("Rain puddles", "day_rain", "weather", "puddles"),
        ("Muddy tracks", "day_rain", "weather", "mud-tracks"),
        ("Snow tracks", "day_snow", "weather", "snow-tracks"),
        ("Fox visitor", "dusk_clear", "visitor", "fox"),
        ("Rabbit visitor", "day_clear", "visitor", "rabbit"),
        ("Hedgehog visitor", "dusk_clear", "visitor", "hedgehog"),
        ("Pheasant visitor", "day_clear", "visitor", "pheasant"),
        ("Cat visitor", "day_clear", "visitor", "cat"),
        ("Rare garden gnome", "day_clear", "visitor", "gnome"),
    )
    sheet = Image.new("L", (CELL[0] * 2, CELL[1] * 5), 255)
    draw = ImageDraw.Draw(sheet)
    face = ImageFont.truetype(FONT, 17)
    for index, (label, variant, kind, name) in enumerate(items):
        image = prepared(variant)
        if kind == "weather":
            _paste_overlay(image, OVERLAY_DIR / f"weather-{name}-v1.png",
                           center_x=590, bottom=386, target_width=WEATHER_WIDTHS[name])
        else:
            filename = "surprise-gnome-v1.png" if name == "gnome" else f"visitor-{name}-v1.png"
            _paste_overlay(image, OVERLAY_DIR / filename, center_x=608, bottom=367,
                           target_height=VISITOR_HEIGHTS[name])
        rendered = four_tone(image)
        slug = name.replace("-", "_")
        rendered.save(ROOT / "output" / f"foreground-overlay-{slug}.png", optimize=True)
        preview = rendered.resize(PREVIEW, Image.Resampling.NEAREST)
        x, y = (index % 2) * CELL[0], (index // 2) * CELL[1]
        sheet.paste(preview, (x, y))
        draw.text((x + 10, y + 244), label, font=face, fill=0)
    target = ROOT / "output" / "foreground-overlays-contact-sheet.png"
    sheet.save(target, optimize=True)
    print(target)


if __name__ == "__main__":
    main()
