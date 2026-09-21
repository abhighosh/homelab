"""Turn a weather snapshot into renderer input.

The example JSON supplies only public, static map geometry. Its example weather
and astronomy values are never copied into live output.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from render_screens import ROOT, weather_kind


ZONE = ZoneInfo("Europe/London")
STATIC = json.loads((ROOT / "example-screen-data.json").read_text(encoding="utf-8"))
SPECIAL_DATES = {
    "christmas": "12-25", "halloween": "10-31", "new_year": "01-01",
    "bonfire_night": "11-05", "birthday_sarah_jane": "12-19",
    "birthday_abhi": "11-16",
}


def number(value):
    try:
        return float(value) if value is not None and value not in ("", "unknown", "unavailable") else None
    except (TypeError, ValueError):
        return None


def rounded(value, suffix=""):
    value = number(value)
    return f"{round(value):d}{suffix}" if value is not None else "?"


def forecast_list(value):
    if isinstance(value, dict):
        value = value.get("forecast", [])
    return value if isinstance(value, list) else []


def _phase_label(value: float) -> str:
    if value < 1.75 or value >= 26.25:
        return "New Moon"
    if value < 5.25:
        return "Waxing Crescent"
    if value < 8.75:
        return "First Quarter"
    if value < 12.25:
        return "Waxing Gibbous"
    if value < 15.75:
        return "Full Moon"
    if value < 19.25:
        return "Waning Gibbous"
    if value < 22.75:
        return "Last Quarter"
    return "Waning Crescent"


def astronomy(now: datetime) -> tuple[dict, dict]:
    from astral import Observer
    from astral.moon import moonrise, phase
    from astral.sun import sun

    observer = Observer(latitude=STATIC["latitude"], longitude=STATIC["longitude"])
    solar = sun(observer, date=now.date(), tzinfo=ZONE)
    lunar_phase = phase(now.date())
    try:
        rise = moonrise(observer, date=now.date(), tzinfo=ZONE)
        moonrise_label = rise.strftime("%H:%M") if rise else "—"
    except ValueError:
        moonrise_label = "—"
    almanac = {
        "sunrise": solar["sunrise"].strftime("%H:%M"),
        "sunset": solar["sunset"].strftime("%H:%M"),
        "civil_dawn": solar["dawn"].strftime("%H:%M"),
        "civil_dusk": solar["dusk"].strftime("%H:%M"),
        "moon_phase": _phase_label(lunar_phase),
        "moon_illumination_percent": round((1 - math.cos(2 * math.pi * lunar_phase / 28)) * 50),
        "moonrise": moonrise_label,
        "source": "Astral, Oxfordshire public reference coordinate",
    }
    return almanac, solar


def daypart(now: datetime, solar: dict) -> str:
    if solar["dawn"] <= now < solar["sunrise"] + timedelta(minutes=35):
        return "dawn"
    if solar["sunset"] - timedelta(minutes=35) <= now < solar["dusk"]:
        return "dusk"
    if solar["sunrise"] + timedelta(minutes=35) <= now < solar["sunset"] - timedelta(minutes=35):
        return "day"
    return "night"


def next_artwork_change(now: datetime) -> datetime:
    """Return the next time-driven render boundary in local time.

    Weather is scheduled separately by the service. These boundaries cover
    solar dayparts, the six-hour foreground slot, the date on Today/almanac,
    and date-triggered special editions.
    """
    now = now.astimezone(ZONE)
    _, solar = astronomy(now)
    candidates = [
        solar["dawn"],
        solar["sunrise"] + timedelta(minutes=35),
        solar["sunset"] - timedelta(minutes=35),
        solar["dusk"],
    ]
    next_slot_hour = (now.hour // 6 + 1) * 6
    if next_slot_hour < 24:
        candidates.append(now.replace(hour=next_slot_hour, minute=0, second=0, microsecond=0))
    else:
        candidates.append((now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0))
    future = [candidate for candidate in candidates if candidate > now]
    if not future:
        raise ValueError("No future artwork boundary could be calculated")
    return min(future)


def _special(now: datetime, catalog: dict) -> str | None:
    for name, month_day in SPECIAL_DATES.items():
        entry = catalog["special_editions"].get(name, {})
        if entry.get("enabled") and now.strftime("%m-%d") == entry.get("month_day", month_day):
            return name
    return None


def build_live_data(snapshot: dict, now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(ZONE)
    now = now.astimezone(ZONE)
    generated = datetime.fromisoformat(snapshot["generated_at"])
    if generated.tzinfo is None or abs((now - generated).total_seconds()) > 3 * 3600:
        raise ValueError("Home Assistant weather snapshot is stale or lacks a timezone")
    current = snapshot.get("current") or {}
    daily = forecast_list(snapshot.get("daily"))
    hourly = forecast_list(snapshot.get("hourly"))
    day = daily[0] if daily else {}
    hour = hourly[0] if hourly else {}
    condition = str(day.get("condition") or current.get("condition") or "unknown").replace("_", " ")
    pretty = condition.title() if condition != "unknown" else "Weather unavailable"
    rain_chance = number(day.get("precipitation_probability"))
    if rain_chance is None:
        rain_chance = number(current.get("precipitation_probability"))
    almanac, solar = astronomy(now)
    catalog = json.loads((ROOT / "artwork-selection.json").read_text(encoding="utf-8"))
    group = weather_kind(str(current.get("condition") or condition))
    if group == "partly_cloudy":
        group = "cloudy"
    if group == "storm":
        group = "rain"
    variant = f"{daypart(now, solar)}_{group}"
    if variant not in catalog["variants"]:
        variant = "day_clear"
    special = _special(now, catalog)
    if special:
        # The renderer resolves entries under `variants`; the special image is
        # selectable only when an owner has explicitly enabled that edition.
        variant = special
    data = {
        "date": now.date().isoformat(),
        "location_label": "Oxfordshire",
        "latitude": STATIC["latitude"], "longitude": STATIC["longitude"],
        "map": STATIC["map"],
        "portrait_variant": variant,
        # Foreground visitors remain fixed across the half-hour weather polls,
        # then receive a fresh deterministic choice at 00:00/06:00/12:00/18:00.
        "foreground_slot": f"{now.date().isoformat()}-{now.hour // 6}",
        "forecast": {
            "condition": pretty,
            "high_c": rounded(day.get("temperature")),
            "low_c": rounded(day.get("templow")),
            "rain_chance_percent": rounded(rain_chance),
        },
        "map_live": {
            "wind_bearing": number(current.get("wind_bearing")),
            "wind_speed": number(current.get("wind_speed")),
            "wind_unit": current.get("wind_unit") or "mph",
            "rain_next_hour_percent": rounded(hour.get("precipitation_probability")) if
                                      number(hour.get("precipitation_probability")) is not None else None,
            "updated_at": generated.isoformat(),
        },
        "almanac": almanac,
    }
    return data
