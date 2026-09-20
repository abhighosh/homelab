"""Lightweight regression checks for the screen renderer and Surprise mode."""

from __future__ import annotations

import random
import unittest
from datetime import datetime, timezone

from screen_mode import PAGES, RANDOM_PAGES, ScreenMode
from render_screens import WEATHER_FONT, WEATHER_GLYPHS, horizontal, sidereal_degrees, weather_kind
from map_imagery import map_bbox, mercator
from fetch_road_map import inverse_mercator
from PIL import ImageFont


class ScreenModeTests(unittest.TestCase):
    def test_navigation_and_portrait_shortcut(self) -> None:
        mode = ScreenMode(rng=random.Random(1))
        self.assertEqual(mode.move(1, 1), "today")
        self.assertEqual(mode.move(-1, 2), "portrait")
        self.assertEqual(mode.move(-1, 3), mode.shown)
        self.assertEqual(mode.page, "surprise")
        self.assertIn(mode.shown, RANDOM_PAGES)
        self.assertEqual(mode.move(1, 4), "portrait")
        self.assertEqual(mode.green_button(5), "portrait")

    def test_surprise_never_repeats_and_only_ticks_in_mode(self) -> None:
        mode = ScreenMode(rng=random.Random(5))
        first = mode.select("surprise", 0)
        second = mode.green_button(10)
        self.assertNotEqual(first, second)
        self.assertEqual(mode.hourly_tick(3500), second)
        third = mode.hourly_tick(3610)
        self.assertNotEqual(second, third)
        mode.select("map", 3700)
        self.assertEqual(mode.hourly_tick(8000), "map")
        self.assertEqual(mode.page, "map")

    def test_all_pages_are_unique(self) -> None:
        self.assertEqual(len(PAGES), len(set(PAGES)))
        self.assertNotIn("surprise", RANDOM_PAGES)


class SkyGeometryTests(unittest.TestCase):
    def test_zenith_star_is_overhead(self) -> None:
        moment = datetime(2026, 9, 20, 20, tzinfo=timezone.utc)
        lst = sidereal_degrees(moment, -1.258)
        altitude, _ = horizontal(lst, 51.752, 51.752, lst)
        self.assertAlmostEqual(altitude, 90, places=5)

    def test_east_west_orientation(self) -> None:
        lst = 180
        _, east = horizontal(270, 0, 0, lst)
        _, west = horizontal(90, 0, 0, lst)
        self.assertAlmostEqual(east, 90, places=5)
        self.assertAlmostEqual(west, 270, places=5)


class WeatherIconTests(unittest.TestCase):
    def test_condition_mapping(self) -> None:
        self.assertEqual(weather_kind("Partly cloudy"), "partly_cloudy")
        self.assertEqual(weather_kind("Light rain showers"), "rain")
        self.assertEqual(weather_kind("Snow"), "snow")
        self.assertEqual(weather_kind("Clear"), "clear")

    def test_font_contains_each_weather_glyph(self) -> None:
        face = ImageFont.truetype(WEATHER_FONT, 64)
        self.assertTrue(all(face.getmask(glyph).getbbox() for glyph in WEATHER_GLYPHS.values()))


class MapTests(unittest.TestCase):
    def test_mercator_round_trip_for_village_centre(self) -> None:
        x, y = mercator(51.89769, -1.11603)
        latitude, longitude = inverse_mercator(x, y)
        self.assertAlmostEqual(latitude, 51.89769, places=5)
        self.assertAlmostEqual(longitude, -1.11603, places=5)

    def test_web_mercator_bbox_has_display_aspect_ratio(self) -> None:
        left, bottom, right, top = map_bbox(51.752, -1.258, 24)
        self.assertAlmostEqual(right - left, 24000)
        self.assertAlmostEqual((top - bottom) / (right - left), 480 / 800)

    def test_map_width_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            map_bbox(51.752, -1.258, 1)

    def test_wide_launton_view_contains_oxford_and_abingdon(self) -> None:
        left, bottom, right, top = map_bbox(51.89769, -1.11603, 185)
        for latitude, longitude in ((51.751977, -1.257647), (51.6714842, -1.2779715)):
            x, y = mercator(latitude, longitude)
            self.assertLess(left, x)
            self.assertLess(x, right)
            self.assertLess(bottom, y)
            self.assertLess(y, top)
            self.assertLess((top - y) / (top - bottom) * 480, 444)


if __name__ == "__main__":
    unittest.main()
