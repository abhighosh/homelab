"""Build labeled review sheets from the selected E1001-sized previews."""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
PHASES = ("dawn", "day", "dusk", "night")
WEATHERS = ("clear", "cloudy", "rain", "fog", "snow")
CELL = (320, 219)
IMAGE_SIZE = (320, 192)


def main() -> None:
    catalog = json.loads((ROOT / "artwork-selection.json").read_text(encoding="utf-8"))
    sheet = Image.new("RGB", (CELL[0] * len(WEATHERS), CELL[1] * len(PHASES)), "white")
    draw = ImageDraw.Draw(sheet)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 16) if Path(font_path).exists() else ImageFont.load_default()

    for row, phase in enumerate(PHASES):
        for column, weather in enumerate(WEATHERS):
            entry = catalog["variants"][f"{phase}_{weather}"]
            source = ROOT / "output" / f"{Path(entry['path']).stem}-e1001.png"
            if not source.exists():
                raise FileNotFoundError(f"Missing prepared preview: {source}")
            with Image.open(source) as original:
                preview = original.convert("RGB").resize(IMAGE_SIZE, Image.Resampling.LANCZOS)
            x, y = column * CELL[0], row * CELL[1]
            sheet.paste(preview, (x, y))
            draw.text((x + 8, y + 195), f"{phase.title()} · {weather.title()}", font=font, fill="black")

    target = ROOT / "output" / "weather-time-contact-sheet.png"
    sheet.save(target, optimize=True)
    print(target)

    specials = list(catalog["special_editions"].items())
    columns = 3
    rows = math.ceil(len(specials) / columns)
    special = Image.new("RGB", (CELL[0] * columns, CELL[1] * rows), "white")
    special_draw = ImageDraw.Draw(special)
    for index, (name, entry) in enumerate(specials):
        source = ROOT / "output" / f"{Path(entry['path']).stem}-e1001.png"
        with Image.open(source) as original:
            preview = original.convert("RGB").resize(IMAGE_SIZE, Image.Resampling.LANCZOS)
        x, y = (index % columns) * CELL[0], (index // columns) * CELL[1]
        special.paste(preview, (x, y))
        label = entry.get("display_name", name.replace("_", " ").title())
        special_draw.text((x + 8, y + 195), label, font=font, fill="black")
    special_target = ROOT / "output" / "special-editions-contact-sheet.png"
    special.save(special_target, optimize=True)
    print(special_target)

    screen_names = ("portrait", "today", "map", "almanac", "constellations")
    if all((ROOT / "output" / f"screen-{name}.png").is_file() for name in screen_names):
        screen_sheet = Image.new("RGB", (CELL[0] * 2, CELL[1] * 3), "white")
        screen_draw = ImageDraw.Draw(screen_sheet)
        for index, name in enumerate(screen_names):
            with Image.open(ROOT / "output" / f"screen-{name}.png") as original:
                preview = original.convert("RGB").resize(IMAGE_SIZE, Image.Resampling.LANCZOS)
            x, y = (index % 2) * CELL[0], (index // 2) * CELL[1]
            screen_sheet.paste(preview, (x, y))
            screen_draw.text((x + 8, y + 195), name.title(), font=font, fill="black")
        target = ROOT / "output" / "screens-contact-sheet.png"
        screen_sheet.save(target, optimize=True)
        print(target)


if __name__ == "__main__":
    main()
