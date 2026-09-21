"""Small offline checks for the NAS weather and E1001 wire format."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PIL import Image

from frame_codec import FRAME_BYTES, pack_gray4
from live_data import ROOT, _special, build_live_data, next_artwork_change
from open_meteo import adapt, condition
from render_screens import SIZE
from service import next_check_seconds


class WeatherTests(unittest.TestCase):
    def test_next_artwork_change_uses_real_solar_boundaries(self):
        now = datetime(2026, 9, 20, 6, 5, tzinfo=ZoneInfo("Europe/London"))
        solar = {
            "dawn": now.replace(hour=6, minute=12),
            "sunrise": now.replace(hour=6, minute=48),
            "sunset": now.replace(hour=19, minute=2),
            "dusk": now.replace(hour=19, minute=38),
        }
        with patch("live_data.astronomy", return_value=({}, solar)):
            self.assertEqual(next_artwork_change(now), solar["dawn"])

        after_dawn = now.replace(hour=6, minute=20)
        with patch("live_data.astronomy", return_value=({}, solar)):
            self.assertEqual(next_artwork_change(after_dawn), solar["sunrise"] + timedelta(minutes=35))

    def test_display_check_is_shortly_after_server_deadline(self):
        now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(next_check_seconds(now + timedelta(minutes=7), now), 450)
        self.assertEqual(next_check_seconds(now + timedelta(hours=2), now), 1800)

    def test_special_editions_are_scheduled_only_on_their_dates(self):
        import json

        catalog = json.loads((ROOT / "artwork-selection.json").read_text(encoding="utf-8"))
        expected = {
            "2026-01-01": "new_year", "2026-10-31": "halloween",
            "2026-11-05": "bonfire_night", "2026-11-16": "birthday_abhi",
            "2026-12-19": "birthday_sarah_jane", "2026-12-25": "christmas",
        }
        for day, name in expected.items():
            with self.subTest(day=day):
                self.assertEqual(_special(datetime.fromisoformat(day), catalog), name)
        self.assertIsNone(_special(datetime.fromisoformat("2026-09-20"), catalog))

    def test_wmo_groups(self):
        self.assertEqual(condition(2), "Partly cloudy")
        self.assertEqual(condition(65), "Rain")
        self.assertEqual(condition(75), "Snow")
        self.assertEqual(condition(95), "Thunderstorm")
        self.assertEqual(condition(999), "unknown")

    def test_open_meteo_adapter_uses_next_hour(self):
        now = datetime(2026, 9, 20, 14, 15, tzinfo=ZoneInfo("Europe/London"))
        snapshot = adapt({
            "current": {"weather_code": 61, "wind_speed_10m": 8, "wind_direction_10m": 225},
            "daily": {"weather_code": [2], "temperature_2m_max": [19],
                      "temperature_2m_min": [11], "precipitation_probability_max": [40]},
            "hourly": {"time": ["2026-09-20T14:00", "2026-09-20T15:00"],
                       "precipitation_probability": [5, 70]},
        }, now)
        self.assertEqual(snapshot["current"]["condition"], "Rain")
        self.assertEqual(snapshot["daily"][0]["condition"], "Partly cloudy")
        self.assertEqual(snapshot["hourly"][0]["precipitation_probability"], 70)

    def test_live_data_does_not_use_example_weather(self):
        now = datetime(2026, 9, 20, 14, 15, tzinfo=ZoneInfo("Europe/London"))
        snapshot = {"generated_at": now.isoformat(), "current": {"condition": "Rain"},
                    "daily": [{"condition": "Rain", "temperature": 9, "templow": 4,
                               "precipitation_probability": 80}]}
        solar = {"dawn": now.replace(hour=6), "sunrise": now.replace(hour=7),
                 "sunset": now.replace(hour=19), "dusk": now.replace(hour=20)}
        almanac = {"sunrise": "07:00", "sunset": "19:00", "civil_dawn": "06:00",
                   "civil_dusk": "20:00", "moon_phase": "New Moon",
                   "moon_illumination_percent": 0, "moonrise": "—"}
        with patch("live_data.astronomy", return_value=(almanac, solar)):
            data = build_live_data(snapshot, now)
        self.assertEqual(data["portrait_variant"], "day_rain")
        self.assertEqual(data["foreground_slot"], "2026-09-20-2")
        self.assertEqual(data["forecast"]["high_c"], "9")
        self.assertIsNone(data["map_live"]["rain_next_hour_percent"])


class FrameTests(unittest.TestCase):
    def test_gray4_high_nibble_first(self):
        image = Image.new("L", SIZE, 255)
        image.putpixel((0, 0), 0)
        image.putpixel((1, 0), 85)
        image.putpixel((2, 0), 170)
        data = pack_gray4(image)
        self.assertEqual(len(data), FRAME_BYTES)
        self.assertEqual(data[:3], bytes((0x01, 0x23, 0x33)))


if __name__ == "__main__":
    unittest.main()
