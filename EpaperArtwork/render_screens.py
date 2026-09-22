"""Render E1001 pages from explicit weather and almanac data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import deque
from datetime import date, datetime, time, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from map_imagery import map_bbox, mercator
from prepare_art import quantize_four_tone


ROOT = Path(__file__).resolve().parent
SIZE = (800, 480)
BLACK, DARK, LIGHT, WHITE = 0, 85, 170, 255
SERIF = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
SERIF_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
WEATHER_FONT = str(ROOT / "assets" / "fonts" / "material-weather.ttf")
WEATHER_GLYPHS = {
    "clear": "\uf157",
    "partly_cloudy": "\uf172",
    "cloudy": "\uf15c",
    "rain": "\uf176",
    "snow": "\ue2cd",
    "fog": "\ue818",
    "storm": "\uebdb",
}
OVERLAY_DIR = ROOT / "assets" / "overlays"
VISITOR_HEIGHTS = {
    "fox": 44,
    "rabbit": 52,
    "hedgehog": 29,
    "pheasant": 45,
    "cat": 43,
    "gnome": 48,
}
WEATHER_WIDTHS = {
    "leaves": 185,
    "puddles": 145,
    "mud-tracks": 92,
    "snow-tracks": 92,
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def material_weather_font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """Return the variable outline icon font at an explicit stroke weight."""
    face = font(WEATHER_FONT, size)
    face.set_variation_by_axes([0, 0, 48, weight])
    return face


def centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, face: ImageFont.FreeTypeFont, fill: int = BLACK) -> None:
    draw.text(xy, text, font=face, fill=fill, anchor="mm")


def date_label(value: date) -> str:
    return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"


def portrait_path(data: dict) -> Path:
    catalog = json.loads((ROOT / "artwork-selection.json").read_text(encoding="utf-8"))
    variant = data["portrait_variant"]
    entries = {**catalog["variants"], **catalog["special_editions"]}
    if variant not in entries:
        raise ValueError(f"Unknown portrait variant: {variant}")
    source = ROOT / entries[variant]["path"]
    prepared = ROOT / "output" / f"{source.stem}-e1001.png"
    if not prepared.is_file():
        raise FileNotFoundError(f"Run build_previews.py first: {prepared}")
    return prepared


def draw_dynamic_moon(image: Image.Image, almanac: dict) -> None:
    """Draw the real phase into the clear-night sky of a prepared portrait."""
    illumination = max(0.0, min(1.0, float(almanac["moon_illumination_percent"]) / 100))
    if illumination < 0.03:
        return
    waxing = almanac["moon_phase"].casefold().startswith("waxing") or \
        almanac["moon_phase"].casefold() == "first quarter"
    draw = ImageDraw.Draw(image)
    cx, cy, radius = 616, 80, 19
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=DARK)
    for y in range(cy - radius, cy + radius + 1):
        half_width = math.sqrt(max(0, radius * radius - (y - cy) ** 2))
        threshold = cx + (1 - 2 * illumination) * half_width if waxing else \
            cx + (2 * illumination - 1) * half_width
        for x in range(math.ceil(cx - half_width), math.floor(cx + half_width) + 1):
            lit = x >= threshold if waxing else x <= threshold
            if lit:
                draw.point((x, y), fill=WHITE)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=BLACK, width=1)


def _stable_random(data: dict) -> random.Random:
    """Return a reproducible RNG so routine refreshes do not move visitors."""
    slot = data.get("foreground_slot", f"{data['date']}-{data['portrait_variant']}")
    digest = hashlib.sha256(str(slot).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def select_foreground_overlays(data: dict) -> dict:
    """Choose restrained seasonal details for a normal house portrait.

    The result is stable for the supplied six-hour slot. Special editions are
    already composed illustrations and deliberately receive no extra props.
    """
    variant = data["portrait_variant"]
    if not variant.startswith(("dawn_", "day_", "dusk_", "night_")):
        return {"weather": None, "visitor": None, "flip": False, "spot": 0}
    daypart, condition = variant.split("_", 1)
    current = date.fromisoformat(data["date"])
    rng = _stable_random(data)

    weather = None
    roll = rng.random()
    if condition == "rain":
        weather = "puddles" if roll < 0.68 else "mud-tracks" if roll < 0.92 else None
    elif condition == "snow":
        weather = "snow-tracks" if roll < 0.78 else None
    elif current.month in (9, 10, 11) and roll < 0.52:
        weather = "leaves"

    # The gnome is an intentionally rare surprise. Ordinary wildlife appears
    # often enough to make the portrait feel alive without becoming a mascot.
    visitor = None
    visitor_roll = rng.random()
    if visitor_roll < 0.01:
        visitor = "gnome"
    elif visitor_roll < 0.43:
        pools = {
            "dawn": ("rabbit", "pheasant", "cat", "cat"),
            "day": ("rabbit", "pheasant", "cat", "cat"),
            "dusk": ("fox", "hedgehog", "rabbit", "cat", "cat"),
            "night": ("fox", "hedgehog", "cat", "cat"),
        }
        visitor = rng.choice(pools[daypart])
    return {
        "weather": weather,
        "visitor": visitor,
        "flip": rng.choice((False, True)),
        "spot": rng.randrange(3),
    }


@lru_cache(maxsize=16)
def _cropped_overlay(path: str) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA")
    alpha = image.getchannel("A")
    # Generated edges include a few nearly invisible pixels; ignoring them
    # gives predictable scaling while retaining the antialiased ink edge.
    bbox = alpha.point(lambda value: 255 if value >= 32 else 0).getbbox()
    if bbox is None:
        raise ValueError(f"Empty foreground overlay: {path}")
    return image.crop(bbox)


def _paste_overlay(image: Image.Image, path: Path, *, center_x: int, bottom: int,
                   target_height: int | None = None, target_width: int | None = None,
                   flip: bool = False) -> None:
    overlay = _cropped_overlay(str(path)).copy()
    if flip:
        overlay = ImageOps.mirror(overlay)
    if target_height is not None:
        scale = target_height / overlay.height
    elif target_width is not None:
        scale = target_width / overlay.width
    else:
        raise ValueError("An overlay needs a target height or width")
    size = (max(1, round(overlay.width * scale)), max(1, round(overlay.height * scale)))
    overlay = overlay.resize(size, Image.Resampling.LANCZOS)
    x, y = round(center_x - overlay.width / 2), bottom - overlay.height
    image.paste(overlay.convert("L"), (x, y), overlay.getchannel("A"))


def draw_foreground_overlays(image: Image.Image, data: dict) -> None:
    selection = select_foreground_overlays(data)
    weather = selection["weather"]
    if weather:
        weather_spots = ((590, 386), (660, 373), (520, 383))
        x, bottom = weather_spots[selection["spot"]]
        _paste_overlay(image, OVERLAY_DIR / f"weather-{weather}-v1.png",
                       center_x=x, bottom=bottom, target_width=WEATHER_WIDTHS[weather],
                       flip=selection["flip"])
    visitor = selection["visitor"]
    if visitor:
        visitor_spots = ((608, 367), (696, 374), (535, 371))
        x, bottom = visitor_spots[(selection["spot"] + 1) % len(visitor_spots)]
        filename = "surprise-gnome-v1.png" if visitor == "gnome" else f"visitor-{visitor}-v1.png"
        _paste_overlay(image, OVERLAY_DIR / filename, center_x=x, bottom=bottom,
                       target_height=VISITOR_HEIGHTS[visitor], flip=selection["flip"])


def portrait(data: dict) -> Image.Image:
    with Image.open(portrait_path(data)) as source:
        image = source.convert("L")
    # Cloud, rain, fog and snow naturally obscure the moon; only the selected
    # clear-night base contains a deliberately empty patch of sky for it.
    if data["portrait_variant"] == "night_clear":
        draw_dynamic_moon(image, data["almanac"])
    draw_foreground_overlays(image, data)
    return image


def weather_kind(condition: str) -> str:
    text = condition.casefold()
    if any(word in text for word in ("thunder", "storm", "lightning")):
        return "storm"
    if any(word in text for word in ("snow", "sleet", "hail")):
        return "snow"
    if any(word in text for word in ("rain", "shower", "drizzle", "pouring")):
        return "rain"
    if any(word in text for word in ("fog", "mist", "haze")):
        return "fog"
    if any(word in text for word in ("partly", "interval", "mostly sunny")):
        return "partly_cloudy"
    if any(word in text for word in ("cloud", "overcast")):
        return "cloudy"
    return "clear"


def weather_icon(draw: ImageDraw.ImageDraw, condition: str, x: int, y: int) -> None:
    """Rasterise a single Material Symbols glyph; no icon work on-device."""
    draw.text((x, y), WEATHER_GLYPHS[weather_kind(condition)],
              font=material_weather_font(64, 300), fill=BLACK, anchor="mm")


def today(data: dict) -> Image.Image:
    image = portrait(data)
    forecast = data["forecast"]
    current = date.fromisoformat(data["date"])
    date_text = f"{current.strftime('%A')} {current.day} {current.strftime('%B %Y')}".upper()
    weather_text = (f"{forecast['condition']}  ·  {forecast['high_c']}° / {forecast['low_c']}°"
                    f"  ·  {forecast['rain_chance_percent']}% rain")
    draw = ImageDraw.Draw(image)
    date_face = next((face for size in range(38, 29, -1)
                      if draw.textlength(date_text, font=(face := font(SERIF_BOLD, size))) <= 700),
                     font(SERIF_BOLD, 29))
    weather_face = next((face for size in range(34, 25, -1)
                         if draw.textlength(weather_text, font=(face := font(SANS_BOLD, size))) <= 740),
                        font(SANS_BOLD, 25))
    draw.text((775, 18), date_text, font=date_face, fill=BLACK, anchor="rt",
              stroke_width=6, stroke_fill=WHITE)
    draw.text((775, 68), weather_text, font=weather_face, fill=BLACK, anchor="rt",
              stroke_width=6, stroke_fill=WHITE)
    return image


def boundary_map(data: dict) -> Image.Image:
    border = ROOT / "output" / "map-border-preview.png"
    if not border.is_file():
        raise FileNotFoundError("Run prepare_art.py for the map-border-preview first")
    with Image.open(border) as source:
        image = source.convert("L")
    draw = ImageDraw.Draw(image)
    geojson = json.loads((ROOT / "assets" / "map" / "oxfordshire-boundary.geojson").read_text(encoding="utf-8"))
    if len(geojson["features"]) != 1:
        raise ValueError("Expected one Oxfordshire boundary feature")
    rings = geojson["features"][0]["geometry"]["coordinates"]
    coords = [point for ring in rings for point in ring]
    lon_min, lon_max = min(p[0] for p in coords), max(p[0] for p in coords)
    lat_min, lat_max = min(p[1] for p in coords), max(p[1] for p in coords)
    cos_lat = math.cos(math.radians((lat_min + lat_max) / 2))
    x_extent = (lon_max - lon_min) * cos_lat
    y_extent = lat_max - lat_min
    scale = min(360 / x_extent, 315 / y_extent)
    cx, cy = 404, 240
    center_lon, center_lat = (lon_min + lon_max) / 2, (lat_min + lat_max) / 2

    def point(lon: float, lat: float) -> tuple[int, int]:
        return (round(cx + (lon - center_lon) * cos_lat * scale), round(cy - (lat - center_lat) * scale))

    # Keep map geometry from the source; the ornamental artwork is decorative only.
    for ring in rings:
        pixels = [point(*coord[:2]) for coord in ring]
        draw.polygon(pixels, fill=WHITE)
        draw.line(pixels + pixels[:1], fill=BLACK, width=4, joint="curve")
    centered(draw, (403, 56), "OXFORDSHIRE", font(SERIF_BOLD, 30))
    # Public town centres verified against OpenStreetMap Nominatim, not private
    # home coordinates. Their labels are deliberately sparse at e-paper size.
    towns = (
        ("Banbury", -1.3402795, 52.0601807, (8, -18)),
        ("Bicester", -1.1518770, 51.8988385, (8, -17)),
        ("Witney", -1.4852861, 51.7838848, (8, -21)),
        ("Oxford", -1.258, 51.752, (8, -18)),
        ("Abingdon", -1.2779715, 51.6714842, (-83, 4)),
        ("Didcot", -1.2459990, 51.6063587, (8, 2)),
        ("Thame", -0.9781805, 51.7482733, (8, -17)),
    )
    for name, longitude, latitude, offset in towns:
        px, py = point(longitude, latitude)
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=BLACK)
        draw.text((px + offset[0], py + offset[1]), name,
                  font=font(SERIF_BOLD if name == "Oxford" else SERIF, 16), fill=BLACK)
    return image


def satellite_map(data: dict) -> Image.Image:
    source_path = ROOT / "output" / "satellite-source.jpg"
    metadata_path = source_path.with_suffix(".json")
    if not source_path.is_file() or not metadata_path.is_file():
        # A real geographic fallback is safer than a blank or invented map.
        return boundary_map(data)
    config = data["map"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for key in ("latitude", "longitude", "width_km"):
        if abs(float(metadata[key]) - float(config[key])) > 0.00001:
            raise ValueError("Cached satellite image does not match the configured map centre or zoom")
    with Image.open(source_path) as original:
        if original.size != SIZE:
            raise ValueError(f"Unexpected satellite image size: {original.size}")
        source = ImageOps.autocontrast(original.convert("L"), cutoff=2)
    # A faint aerial underlay plus real image edges reads more like an inked
    # diagram, while still preserving the geography of the source image.
    underlay = Image.blend(source, Image.new("L", SIZE, WHITE), 0.82)
    edges = source.filter(ImageFilter.GaussianBlur(3.0)).filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges, cutoff=3)
    ink = edges.point(lambda value: BLACK if value > 175 else DARK if value > 125 else WHITE)
    image = quantize_four_tone(ImageChops.darker(underlay, ink))
    draw = ImageDraw.Draw(image)
    xmin, ymin, xmax, ymax = map_bbox(float(config["latitude"]), float(config["longitude"]),
                                       float(config["width_km"]))
    for place in config.get("places", []):
        px, py = mercator(float(place["latitude"]), float(place["longitude"]))
        x = round((px - xmin) / (xmax - xmin) * SIZE[0])
        y = round((ymax - py) / (ymax - ymin) * SIZE[1])
        if not (22 <= x <= SIZE[0] - 22 and 22 <= y <= 428):
            continue
        dx, dy = place.get("label_offset", [9, -18])
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=BLACK, outline=WHITE, width=1)
        # A narrow text halo improves legibility without a label background.
        draw.text((x + dx, y + dy), place["name"], font=font(SANS_BOLD, 17),
                  fill=BLACK, stroke_width=2, stroke_fill=WHITE)

    draw.rectangle((0, 452, 799, 479), fill=BLACK)
    # The WMS bounds are in Web Mercator metres; correct for latitude so the
    # printed scale describes ground distance rather than projected distance.
    ground_width_km = float(config["width_km"]) * math.cos(math.radians(float(config["latitude"])))
    bar_px = round(5 / ground_width_km * SIZE[0])
    draw.line((20, 464, 20 + bar_px, 464), fill=WHITE, width=3)
    draw.line((20, 460, 20, 469), fill=WHITE, width=2)
    draw.line((20 + bar_px, 460, 20 + bar_px, 469), fill=WHITE, width=2)
    draw.text((27 + bar_px, 456), "5 km", font=font(SANS, 14), fill=WHITE)
    draw.text((787, 457), "Sentinel-2 cloudless by EOX IT Services GmbH · Copernicus 2016",
              font=font(SANS, 12), fill=WHITE, anchor="ra")
    return image


@lru_cache(maxsize=1)
def cached_road_network() -> dict:
    path = ROOT / "output" / "road-network.json"
    if not path.is_file():
        raise FileNotFoundError("Run fetch_road_map.py for this map centre before rendering")
    return json.loads(path.read_text(encoding="utf-8"))


def road_map(data: dict) -> Image.Image:
    """Render an offline OSM extract as a clean, four-tone street diagram."""
    config = data["map"]
    network = cached_road_network()
    for key in ("latitude", "longitude", "width_km"):
        if abs(float(network[key]) - float(config[key])) > 0.00001:
            raise ValueError("Cached road map does not match the configured centre or zoom")
    xmin, ymin, xmax, ymax = map_bbox(float(config["latitude"]), float(config["longitude"]),
                                       float(config["width_km"]))

    def pixel(latitude: float, longitude: float, multiplier: int = 1) -> tuple[int, int]:
        x, y = mercator(latitude, longitude)
        return (round((x - xmin) / (xmax - xmin) * SIZE[0] * multiplier),
                round((ymax - y) / (ymax - ymin) * SIZE[1] * multiplier))

    # Draw at the panel's native resolution. Downsampling and four-tone
    # quantisation used to drop isolated pixels from fine roads; native-width
    # vector strokes retain their continuity on the E1001.
    image = Image.new("L", SIZE, WHITE)
    lines = ImageDraw.Draw(image)
    roads = []
    for feature in network["features"]:
        if "points" not in feature or len(feature["points"]) < 2:
            continue
        kind, category = feature["kind"], feature["class"]
        # At this county-scale view, residential streets merge into solid
        # patches around towns. Preserve rural minor roads, but omit that
        # urban-scale detail until a separate zoomed-in map is requested.
        if float(config["width_km"]) > 40 and category in {"residential", "living_street", "road"}:
            continue
        if kind == "waterway":
            style = (0, LIGHT, 2)
        elif kind == "railway":
            style = (1, DARK, 2)
        elif category in {"footway", "path", "cycleway", "bridleway", "steps", "track"}:
            style = (2, LIGHT, 2)
        elif category in {"service", "living_street", "pedestrian"}:
            style = (3, DARK, 2)
        elif category in {"residential", "unclassified", "road"}:
            style = (4, LIGHT, 2)
        elif category in {"tertiary", "tertiary_link"}:
            style = (5, DARK, 2)
        elif category in {"secondary", "secondary_link"}:
            style = (6, BLACK, 2)
        elif category in {"primary", "primary_link", "trunk", "trunk_link", "motorway", "motorway_link"}:
            style = (7, BLACK, 3)
        else:
            style = (3, DARK, 2)
        roads.append((style, feature["points"]))
    for (priority, shade, thickness), points in sorted(roads, key=lambda item: item[0][0]):
        lines.line([pixel(lat, lon) for lat, lon in points], fill=shade, width=thickness, joint="curve")
    draw = ImageDraw.Draw(image)

    # Sparse named places and landmarks, prioritised and collision-checked.
    candidates = ([{"kind": "place", "class": "village", **place} for place in config["places"]]
                  if config.get("places") else
                  [feature for feature in network["features"] if "name" in feature])
    priorities = {name.casefold(): index for index, name in enumerate(config.get("priority_places", []))}
    candidates.sort(key=lambda feature: (priorities.get(feature["name"].casefold(), 100),
                                         0 if feature["kind"] == "place" else 1,
                                         feature["name"]))
    occupied = []
    shown = set()
    for feature in candidates:
        name = feature["name"]
        if name.casefold() in shown or len(shown) >= 14 or len(name) > 27:
            continue
        if priorities and name.casefold() not in priorities:
            continue
        x, y = pixel(feature["latitude"], feature["longitude"])
        if not (25 < x < 775 and 20 < y < 435):
            continue
        if feature["kind"] not in {"place", "railway"} and math.hypot(x - 400, y - 240) > 225:
            continue
        label = name.upper()
        face = font(SERIF_BOLD, 18 if name.casefold() == "launton" else 16)
        width = math.ceil(draw.textlength(label, font=face))
        offset = feature.get("label_offset")
        positions = (((x + offset[0], y + offset[1]),) if offset else
                     ((x + 9, y - 23), (x + 9, y + 6), (x - width - 9, y - 23), (x - width - 9, y + 6)))
        for tx, ty in positions:
            rect = (tx - 4, ty - 4, tx + width + 4, ty + 21)
            if rect[0] < 8 or rect[2] > 792 or rect[1] < 6 or rect[3] > 444:
                continue
            if any(not (rect[2] < other[0] or rect[0] > other[2] or
                        rect[3] < other[1] or rect[1] > other[3]) for other in occupied):
                continue
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=BLACK, outline=WHITE, width=1)
            draw.text((tx, ty), label, font=face, fill=BLACK, stroke_width=4, stroke_fill=WHITE)
            occupied.append(rect)
            shown.add(name.casefold())
            break

    if data.get("map_live"):
        draw_map_live_overlay(draw, data["map_live"])

    # Overlaid scale and attribution: no footer band obscures the map.
    ground_width = float(config["width_km"]) * math.cos(math.radians(float(config["latitude"])))
    scale_km = 20 if ground_width > 80 else 1
    bar_px = round(scale_km / ground_width * SIZE[0])
    draw.line((20, 461, 20 + bar_px, 461), fill=WHITE, width=5)
    draw.line((20, 461, 20 + bar_px, 461), fill=BLACK, width=2)
    for tick_x in (20, 20 + bar_px):
        draw.line((tick_x, 456, tick_x, 466), fill=WHITE, width=4)
        draw.line((tick_x, 456, tick_x, 466), fill=BLACK, width=2)
    draw.text((28 + bar_px, 451), f"{scale_km} km", font=font(SANS, 14), fill=BLACK,
              stroke_width=4, stroke_fill=WHITE)
    draw.text((788, 453), "© OpenStreetMap contributors · ODbL", font=font(SANS, 13),
              fill=BLACK, stroke_width=4, stroke_fill=WHITE, anchor="ra")
    return image


def draw_map_live_overlay(draw: ImageDraw.ImageDraw, status: dict) -> None:
    """Small north-up weather annotation; supplied data may be live or sample."""
    draw.rounded_rectangle((544, 361, 779, 441), radius=8, fill=WHITE, outline=DARK, width=1)
    bearing = status.get("wind_bearing")
    speed = status.get("wind_speed")
    if bearing is not None and speed is not None:
        bearing = float(bearing) % 360
        from_direction = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[round(bearing / 45) % 8]
        # Weather bearings name the direction wind comes FROM. The arrow
        # shows its actual travel direction on this north-up map.
        heading = math.radians((bearing + 180) % 360)
        ux, uy = math.sin(heading), -math.cos(heading)
        cx, cy = 563, 380
        tail = (round(cx - 11 * ux), round(cy - 11 * uy))
        tip = (round(cx + 11 * ux), round(cy + 11 * uy))
        draw.line((*tail, *tip), fill=BLACK, width=3)
        for side in (-1, 1):
            wing = (round(tip[0] - 7 * ux + side * 5 * uy),
                    round(tip[1] - 7 * uy - side * 5 * ux))
            draw.line((*tip, *wing), fill=BLACK, width=2)
        draw.text((582, 370), f"WIND FROM {from_direction}  {speed:g} {status.get('wind_unit', 'mph')}",
                  font=font(SANS_BOLD, 15), fill=BLACK)
    else:
        draw.text((557, 370), "WIND UNAVAILABLE", font=font(SANS_BOLD, 15), fill=BLACK)

    rain = status.get("rain_next_hour_percent")
    rain_text = f"RAIN NEXT HOUR  {rain}%" if rain is not None else "RAIN FORECAST UNAVAILABLE"
    draw.text((557, 395), rain_text, font=font(SANS_BOLD, 15), fill=BLACK)
    updated_at = status.get("updated_at")
    if updated_at:
        stamp = datetime.fromisoformat(updated_at)
        if stamp.tzinfo is None:
            raise ValueError("map_live.updated_at must include a timezone")
        updated = stamp.astimezone(ZoneInfo("Europe/London")).strftime("%H:%M")
        footer = f"UPDATED {updated}" + (" · SAMPLE" if status.get("sample") else "")
    else:
        footer = "UPDATE TIME UNKNOWN"
    draw.text((557, 420), footer, font=font(SANS_BOLD, 14), fill=BLACK)


def regional_tile_map(data: dict) -> Image.Image:
    """Make a low-ink regional view from cached OSM cartography."""
    path = ROOT / "output" / "tile-map-source.png"
    metadata_path = path.with_suffix(".json")
    if not path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("Run fetch_tile_map.py for this map centre before rendering")
    config = data["map"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for key in ("latitude", "longitude", "width_km"):
        if abs(float(metadata[key]) - float(config[key])) > 0.00001:
            raise ValueError("Cached tile map does not match the configured centre or zoom")
    with Image.open(path) as original:
        if list(original.size) != metadata.get("source_size"):
            raise ValueError("Cached tile image dimensions do not match its metadata")
        rgb = original.convert("RGB")
    # Keep the road-colour layer and pale waterways, but discard parks, land
    # tint and baked-in text. We add a small, explicit label set below.
    # This is deliberately not edge detection: it is stylised real cartography.
    source_width, source_height = rgb.size
    if source_width < SIZE[0] or source_height < SIZE[1] or source_width > 3000 or source_height > 2000:
        raise ValueError(f"Unexpected tile map size: {rgb.size}")
    ink = Image.new("L", rgb.size, WHITE)
    source_pixels, ink_pixels = rgb.load(), ink.load()
    fine = bytearray(source_width * source_height)
    for y in range(source_height):
        for x in range(source_width):
            red, green, blue = source_pixels[x, y]
            if red > green + 9 and red > blue + 7 and green < 230:
                shade = BLACK  # principal road colours
            elif blue > red + 13 and blue > green + 6:
                shade = LIGHT  # river or canal
            else:
                shade = WHITE
            ink_pixels[x, y] = shade
            if (max(red, green, blue) - min(red, green, blue) < 10 and
                    145 <= min(red, green, blue) < 210):
                fine[y * source_width + x] = 1
    # Restore tiny gaps at native tile resolution, then downsample the lines.
    ink = ink.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    ink_pixels = ink.load()
    visited = bytearray(len(fine))
    for start in range(len(fine)):
        if not fine[start] or visited[start]:
            continue
        visited[start] = 1
        queue = deque([start])
        component = []
        min_x = max_x = start % source_width
        min_y = max_y = start // source_width
        while queue:
            current = queue.popleft()
            component.append(current)
            x, y = current % source_width, current // source_width
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for ny in range(max(0, y - 1), min(source_height, y + 2)):
                for nx in range(max(0, x - 1), min(source_width, x + 2)):
                    neighbor = ny * source_width + nx
                    if fine[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        queue.append(neighbor)
        long_stroke = max(max_x - min_x, max_y - min_y) >= 65
        if long_stroke and len(component) >= 35:
            for point in component:
                x, y = point % source_width, point // source_width
                if ink_pixels[x, y] == WHITE:
                    ink_pixels[x, y] = DARK
    # Thicken connected road strokes, but do not enlarge isolated tile-colour
    # specks. Labels and attribution are drawn later at their normal size.
    thick_mask = Image.new("L", rgb.size, WHITE)
    thick_pixels = thick_mask.load()
    visited = bytearray(source_width * source_height)
    for start in range(len(visited)):
        sx, sy = start % source_width, start // source_width
        if ink_pixels[sx, sy] > DARK or visited[start]:
            continue
        visited[start] = 1
        queue = deque([start])
        component = []
        min_x = max_x = sx
        min_y = max_y = sy
        while queue:
            current = queue.popleft()
            component.append(current)
            x, y = current % source_width, current // source_width
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for ny in range(max(0, y - 1), min(source_height, y + 2)):
                for nx in range(max(0, x - 1), min(source_width, x + 2)):
                    neighbor = ny * source_width + nx
                    if ink_pixels[nx, ny] <= DARK and not visited[neighbor]:
                        visited[neighbor] = 1
                        queue.append(neighbor)
        if len(component) >= 12 and max(max_x - min_x, max_y - min_y) >= 8:
            for point in component:
                x, y = point % source_width, point // source_width
                thick_pixels[x, y] = ink_pixels[x, y]
    ink = ImageChops.darker(ink, thick_mask.filter(ImageFilter.MinFilter(3)))
    ink = four_tone(ink.resize(SIZE, Image.Resampling.LANCZOS))
    ink = ink.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    draw = ImageDraw.Draw(ink)
    xmin, ymin, xmax, ymax = map_bbox(float(config["latitude"]), float(config["longitude"]),
                                       float(config["width_km"]))
    for place in config.get("places", []):
        px, py = mercator(float(place["latitude"]), float(place["longitude"]))
        x = round((px - xmin) / (xmax - xmin) * SIZE[0])
        y = round((ymax - py) / (ymax - ymin) * SIZE[1])
        if not (20 <= x <= 780 and 18 <= y <= 444):
            continue
        dx, dy = place.get("label_offset", [10, -22])
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=BLACK, outline=WHITE, width=1)
        draw.text((x + dx, y + dy), place["name"], font=font(SANS_BOLD, 17), fill=BLACK,
                  stroke_width=2, stroke_fill=WHITE)
    ground_width = float(config["width_km"]) * math.cos(math.radians(float(config["latitude"])))
    bar_px = round(20 / ground_width * SIZE[0])
    draw.line((20, 461, 20 + bar_px, 461), fill=WHITE, width=5)
    draw.line((20, 461, 20 + bar_px, 461), fill=BLACK, width=2)
    for tick_x in (20, 20 + bar_px):
        draw.line((tick_x, 456, tick_x, 466), fill=WHITE, width=4)
        draw.line((tick_x, 456, tick_x, 466), fill=BLACK, width=2)
    draw.text((28 + bar_px, 451), "20 km", font=font(SANS, 14), fill=BLACK,
              stroke_width=2, stroke_fill=WHITE)
    draw.text((788, 453), "© OpenStreetMap contributors · ODbL", font=font(SANS, 13),
              fill=BLACK, stroke_width=2, stroke_fill=WHITE, anchor="ra")
    return ink


def parse_hm(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def almanac(data: dict) -> Image.Image:
    image = Image.new("L", SIZE, WHITE)
    draw = ImageDraw.Draw(image)
    current = date.fromisoformat(data["date"])
    sky = data["almanac"]
    forecast = data["forecast"]
    centers = (143, 400, 657)
    draw.rectangle((15, 15, 785, 465), outline=BLACK, width=3)
    centered(draw, (400, 46), date_label(current).upper(), font(SANS_BOLD, 26), BLACK)
    draw.line((45, 72, 755, 72), fill=LIGHT, width=2)
    for divider in (271, 529):
        draw.line((divider, 92, divider, 413), fill=LIGHT, width=2)

    weather_x, sun_x, moon_x = centers
    icon_y = 166
    draw.ellipse((sun_x - 46, icon_y - 46, sun_x + 46, icon_y + 46), outline=BLACK, width=3)
    for degrees in range(0, 360, 30):
        angle = math.radians(degrees)
        a, b = 56, 67
        draw.line((sun_x + a * math.cos(angle), icon_y + a * math.sin(angle),
                   sun_x + b * math.cos(angle), icon_y + b * math.sin(angle)), fill=BLACK, width=2)
    centered(draw, (sun_x, 256), "SUN", font(SERIF_BOLD, 26))
    draw.text((sun_x - 88, 292), "Rise", font=font(SANS_BOLD, 21), fill=BLACK)
    draw.text((sun_x + 104, 292), "Set", font=font(SANS_BOLD, 21), fill=BLACK, anchor="ra")
    draw.text((sun_x - 88, 326), sky["sunrise"], font=font(SERIF_BOLD, 30), fill=BLACK)
    draw.text((sun_x + 104, 326), sky["sunset"], font=font(SERIF_BOLD, 30), fill=BLACK, anchor="ra")
    daylight = parse_hm(sky["sunset"]) - parse_hm(sky["sunrise"])
    centered(draw, (sun_x, 388), f"{daylight // 60}h {daylight % 60:02d}m daylight", font(SANS_BOLD, 22), BLACK)

    # Render the illuminated fraction geometrically; white is lit, black is dark.
    fraction = max(0.0, min(1.0, sky["moon_illumination_percent"] / 100))
    waxing = sky["moon_phase"].lower().startswith("waxing") or sky["moon_phase"].lower() == "first quarter"
    mx, my, moon_radius = moon_x, icon_y, 46
    for y in range(my - moon_radius, my + moon_radius + 1):
        half_width = math.sqrt(max(0, moon_radius * moon_radius - (y - my) ** 2))
        threshold = mx + (1 - 2 * fraction) * half_width if waxing else mx + (2 * fraction - 1) * half_width
        for x in range(math.ceil(mx - half_width), math.floor(mx + half_width) + 1):
            lit = x >= threshold if waxing else x <= threshold
            draw.point((x, y), fill=WHITE if lit else BLACK)
    draw.ellipse((mx - moon_radius, my - moon_radius, mx + moon_radius, my + moon_radius), outline=BLACK, width=2)
    centered(draw, (moon_x, 256), "MOON", font(SERIF_BOLD, 26))
    centered(draw, (moon_x, 302), sky["moon_phase"], font(SERIF_BOLD, 25))
    centered(draw, (moon_x, 343), f"{sky['moon_illumination_percent']}% illuminated", font(SANS_BOLD, 21), BLACK)
    centered(draw, (moon_x, 388), f"Moonrise {sky['moonrise']}", font(SANS_BOLD, 22), BLACK)

    draw.text((weather_x, icon_y), WEATHER_GLYPHS[weather_kind(forecast["condition"])],
              font=material_weather_font(114, 250), fill=BLACK, anchor="mm")
    centered(draw, (weather_x, 256), "WEATHER", font(SERIF_BOLD, 26))
    condition = forecast["condition"]
    condition_face = next((face for size in range(25, 19, -1)
                           if draw.textlength(condition, font=(face := font(SERIF_BOLD, size))) <= 225),
                          font(SERIF_BOLD, 19))
    centered(draw, (weather_x, 302), condition, condition_face)
    centered(draw, (weather_x, 343), f"{forecast['high_c']}° / {forecast['low_c']}°", font(SERIF_BOLD, 30))
    centered(draw, (weather_x, 388), f"{forecast['rain_chance_percent']}% chance of rain", font(SANS_BOLD, 22), BLACK)

    centered(draw, (400, 438), f"Civil dawn {sky['civil_dawn']}  ·  Civil dusk {sky['civil_dusk']}", font(SANS_BOLD, 22), BLACK)
    return image


def sidereal_degrees(moment: datetime, longitude: float) -> float:
    utc = moment.astimezone(timezone.utc)
    midnight = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    jd0 = midnight.timestamp() / 86400 + 2440587.5
    h = (utc - midnight).total_seconds() / 3600
    d_ut = jd0 - 2451545.0
    t = (d_ut + h / 24) / 36525
    gmst_hours = (6.697375 + 0.065709824279 * d_ut + 1.0027379 * h + 0.0000258 * t * t) % 24
    return (gmst_hours * 15 + longitude) % 360


def horizontal(ra: float, dec: float, latitude: float, lst: float) -> tuple[float, float]:
    lat, declination, hour_angle = map(math.radians, (latitude, dec, (lst - ra + 180) % 360 - 180))
    sin_alt = math.sin(lat) * math.sin(declination) + math.cos(lat) * math.cos(declination) * math.cos(hour_angle)
    alt = math.degrees(math.asin(max(-1, min(1, sin_alt))))
    az = math.degrees(math.atan2(-math.sin(hour_angle) * math.cos(declination),
                                 math.sin(declination) * math.cos(lat) - math.cos(declination) * math.sin(lat) * math.cos(hour_angle))) % 360
    return alt, az


def constellations(data: dict) -> Image.Image:
    # A full-width altitude/azimuth atlas. N is at both edges because the
    # horizon wraps around; S is central. No circular inset or large heading.
    image = Image.new("L", SIZE, BLACK)
    draw = ImageDraw.Draw(image)
    current = date.fromisoformat(data["date"])
    local = datetime.combine(current, time(21, 0), tzinfo=ZoneInfo("Europe/London"))
    lst = sidereal_degrees(local, data["longitude"])
    catalog = json.loads((ROOT / "assets" / "sky" / "western-bright-stars.json").read_text(encoding="utf-8"))
    left, right, top, horizon = 28, 772, 18, 422

    def project(alt: float, az: float) -> tuple[int, int]:
        return (round(left + az / 360 * (right - left)),
                round(horizon - alt / 90 * (horizon - top)))

    sky_points = {}
    for hip, (ra, dec, mag) in catalog["stars"].items():
        alt, az = horizontal(ra, dec, data["latitude"], lst)
        if alt <= 0:
            continue
        x, y = project(alt, az)
        sky_points[int(hip)] = (x, y, alt, mag, az)

    # Favor bright, mostly visible figures. Avoid groups spanning the north
    # seam; those would otherwise acquire a misleading centre label.
    ranked = []
    for group in catalog["constellations"]:
        ids = {hip for line in group["lines"] for hip in line}
        visible = [sky_points[hip] for hip in ids if hip in sky_points and sky_points[hip][2] > 15]
        if len(visible) >= 3:
            azimuths = [p[4] for p in visible]
            if max(azimuths) - min(azimuths) > 180:
                continue
            mean_alt = sum(p[2] for p in visible) / len(visible)
            brightness = sum(max(0, 4.5 - p[3]) for p in visible)
            score = brightness * 2 + mean_alt / 4 + len(visible)
            ranked.append((score, group, visible))
    chosen = []
    for item in sorted(ranked, key=lambda candidate: candidate[0], reverse=True):
        centre = (sum(p[0] for p in item[2]) / len(item[2]), sum(p[1] for p in item[2]) / len(item[2]))
        if any(math.dist(centre, (sum(p[0] for p in old[2]) / len(old[2]),
                                  sum(p[1] for p in old[2]) / len(old[2]))) < 95 for old in chosen):
            continue
        chosen.append(item)
        if len(chosen) == 8:
            break

    for _, group, _ in chosen:
        for line in group["lines"]:
            for first_hip, second_hip in zip(line, line[1:]):
                if first_hip in sky_points and second_hip in sky_points:
                    a, b = sky_points[first_hip], sky_points[second_hip]
                    if a[2] > 15 and b[2] > 15 and abs(a[0] - b[0]) < 250:
                        draw.line((a[0], a[1], b[0], b[1]), fill=LIGHT, width=3)
    for x, y, _, mag, _ in sky_points.values():
        if mag <= 3.8:
            size = 3 if mag < 1.5 else (2 if mag < 3 else 1)
            draw.ellipse((x - size, y - size, x + size, y + size), fill=WHITE)
    occupied: list[tuple[int, int, int, int]] = []
    for _, group, visible in chosen:
        x = round(sum(p[0] for p in visible) / len(visible))
        bottom = max(p[1] for p in visible)
        name = group["name"].upper()
        face = font(SERIF_BOLD, 20)
        tracking = 2
        label_width = sum(draw.textlength(character, font=face) for character in name) + tracking * (len(name) - 1)
        for dx, dy in ((0, 0), (55, 0), (-55, 0), (0, 30), (55, 30), (-55, 30)):
            label_x, label_y = x + dx, bottom + 24 + dy
            text_box = draw.textbbox((label_x, label_y), name, font=face, anchor="mm")
            box = (round(label_x - label_width / 2) - 4, text_box[1] - 4,
                   round(label_x + label_width / 2) + 4, text_box[3] + 4)
            if box[0] < 8 or box[2] > 792 or box[1] < 8 or box[3] > 414:
                continue
            if any(not (box[2] + 3 < old[0] or box[0] - 3 > old[2] or
                        box[3] + 3 < old[1] or box[1] - 3 > old[3]) for old in occupied):
                continue
            occupied.append(box)
            draw.line((label_x, box[1], x, bottom), fill=DARK, width=2)
            cursor = label_x - label_width / 2
            for character in name:
                draw.text((cursor, label_y), character, font=face, fill=WHITE, anchor="lm",
                          stroke_width=1, stroke_fill=BLACK)
                cursor += draw.textlength(character, font=face) + tracking
            break

    draw.line((10, 430, 790, 430), fill=DARK, width=1)
    for label, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270), ("N", 360)):
        x, _ = project(0, az)
        centered(draw, (x, 449), label, font(SANS_BOLD, 20), WHITE)
    draw.text((14, 10), f"OXFORDSHIRE · {current.strftime('%d %b %Y').upper()} · 21:00 LOCAL",
              font=font(SANS_BOLD, 14), fill=WHITE)
    return image


def validate(image: Image.Image, label: str) -> None:
    if image.size != SIZE or set(image.getdata()) - {BLACK, DARK, LIGHT, WHITE}:
        raise ValueError(f"{label} is not an 800×480 four-tone image")


def four_tone(image: Image.Image) -> Image.Image:
    levels = (BLACK, DARK, LIGHT, WHITE)
    return image.point([min(levels, key=lambda level: abs(level - value)) for value in range(256)])


def dither_four_tone(image: Image.Image) -> Image.Image:
    """Preserve satellite texture using four-tone error diffusion."""
    return quantize_four_tone(image)


def render_pages(data: dict) -> dict[str, Image.Image]:
    """Return validated four-tone pages without persisting any preview files."""
    pages = {
        "portrait": portrait(data),
        "today": today(data),
        "map": (regional_tile_map(data) if data["map"].get("source") == "osm_tiles" else
                road_map(data) if data["map"].get("source") == "osm_lines" else satellite_map(data)),
        "almanac": almanac(data),
        "constellations": constellations(data),
    }
    result = {name: four_tone(image) for name, image in pages.items()}
    for name, image in result.items():
        validate(image, name)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    pages = render_pages(data)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, image in pages.items():
        image.save(args.output / f"screen-{name}.png", format="PNG", optimize=True)
    print(f"Rendered {len(pages)} screens from {args.data}; 'Surprise me' is a runtime mode, not an image")


if __name__ == "__main__":
    main()
