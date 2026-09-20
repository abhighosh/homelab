"""Small direct forecast adapter for public Launton, without Home Assistant."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


ZONE = ZoneInfo("Europe/London")
URL = "https://api.open-meteo.com/v1/forecast"
PUBLIC_VILLAGE_LATITUDE = 51.89769
PUBLIC_VILLAGE_LONGITUDE = -1.11603


def condition(code) -> str:
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "unknown"
    if code == 0:
        return "Clear"
    if code == 1:
        return "Mainly clear"
    if code == 2:
        return "Partly cloudy"
    if code == 3:
        return "Cloudy"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67):
        return "Rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    if code in (80, 81, 82):
        return "Rain showers"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "unknown"


def first(values: dict, key: str):
    items = values.get(key) or []
    return items[0] if items else None


def adapt(payload: dict, now: datetime | None = None) -> dict:
    now = (now or datetime.now(ZONE)).astimezone(ZONE)
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    next_rain = None
    for index, label in enumerate(times):
        stamp = datetime.fromisoformat(label)
        if stamp.replace(tzinfo=ZONE) >= next_hour:
            probabilities = hourly.get("precipitation_probability") or []
            next_rain = probabilities[index] if index < len(probabilities) else None
            break
    return {
        "generated_at": now.isoformat(),
        "current": {
            "condition": condition(current.get("weather_code")),
            "wind_bearing": current.get("wind_direction_10m"),
            "wind_speed": current.get("wind_speed_10m"),
            "wind_unit": "mph",
        },
        "daily": [{
            "condition": condition(first(daily, "weather_code")),
            "temperature": first(daily, "temperature_2m_max"),
            "templow": first(daily, "temperature_2m_min"),
            "precipitation_probability": first(daily, "precipitation_probability_max"),
        }],
        "hourly": [{"precipitation_probability": next_rain}],
        "source": "Open-Meteo",
    }


def fetch() -> dict:
    params = {
        "latitude": PUBLIC_VILLAGE_LATITUDE,
        "longitude": PUBLIC_VILLAGE_LONGITUDE,
        "timezone": "Europe/London",
        "wind_speed_unit": "mph",
        "forecast_days": 2,
        "current": "weather_code,wind_speed_10m,wind_direction_10m",
        "hourly": "precipitation_probability",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    }
    response = requests.get(URL, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error") or not payload.get("daily", {}).get("time"):
        raise ValueError("Open-Meteo did not return a daily forecast")
    return adapt(payload)
