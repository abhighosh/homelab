"""Lightweight regression checks for the screen renderer and Surprise mode."""

from __future__ import annotations

import random
import unittest
from datetime import datetime, timezone

from screen_mode import PAGES, RANDOM_PAGES, ScreenMode
from daily_artwork import suitability
from render_screens import (BLACK, DARK, WEATHER_FONT, WEATHER_GLYPHS, WHITE, artwork, four_tone,
                            draw_dynamic_moon, horizontal, sidereal_degrees,
                            select_foreground_overlays, weather_kind)
from map_imagery import map_bbox, mercator
from fetch_road_map import inverse_mercator
from PIL import Image, ImageDraw, ImageFont


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
        mode.select("artwork", 3700)
        self.assertEqual(mode.hourly_tick(8000), "artwork")
        self.assertEqual(mode.page, "artwork")

    def test_all_pages_are_unique(self) -> None:
        self.assertEqual(len(PAGES), len(set(PAGES)))
        self.assertNotIn("surprise", RANDOM_PAGES)


class SkyGeometryTests(unittest.TestCase):
    def test_dynamic_moon_respects_waxing_and_waning_phase(self) -> None:
        waxing = Image.new("L", (800, 480), 0)
        draw_dynamic_moon(waxing, {
            "moon_illumination_percent": 50, "moon_phase": "First Quarter",
        })
        self.assertEqual(waxing.getpixel((626, 80)), WHITE)
        self.assertEqual(waxing.getpixel((606, 80)), DARK)

        waning = Image.new("L", (800, 480), 0)
        draw_dynamic_moon(waning, {
            "moon_illumination_percent": 50, "moon_phase": "Last Quarter",
        })
        self.assertEqual(waning.getpixel((606, 80)), WHITE)
        self.assertEqual(waning.getpixel((626, 80)), DARK)

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


class ArtworkPageTests(unittest.TestCase):
    def test_selection_rejects_portrait_and_dense_sources(self) -> None:
        portrait = Image.new("L", (700, 1000), WHITE)
        self.assertFalse(suitability(portrait)[0])

        dense = Image.new("L", (1200, 650), WHITE)
        dense_draw = ImageDraw.Draw(dense)
        for x in range(0, 1200, 5):
            dense_draw.line((x, 0, x, 649), fill=BLACK, width=2)
        self.assertFalse(suitability(dense)[0])

        simple = Image.new("L", (1200, 650), WHITE)
        simple_draw = ImageDraw.Draw(simple)
        simple_draw.rectangle((80, 180, 1120, 570), fill=170, outline=BLACK, width=8)
        simple_draw.ellipse((440, 70, 760, 390), fill=WHITE, outline=BLACK, width=8)
        self.assertTrue(suitability(simple)[0])

    def test_artwork_is_display_sized_and_four_tone(self) -> None:
        image = four_tone(artwork({"artwork": {
            "image_path": "assets/house/day-clear-hand-ink-v1.png",
            "title": "A deliberately long sample title for the daily gallery view",
            "artist": "Sample artist", "object_date": "nineteenth century",
        }}))
        self.assertEqual(image.size, (800, 480))
        self.assertFalse(set(image.getdata()) - {BLACK, DARK, 170, WHITE})


class ForegroundOverlayTests(unittest.TestCase):
    def test_choice_is_stable_within_a_slot(self) -> None:
        data = {"date": "2026-10-18", "portrait_variant": "day_clear",
                "foreground_slot": "2026-10-18-2"}
        self.assertEqual(select_foreground_overlays(data), select_foreground_overlays(data))

    def test_special_editions_are_not_modified(self) -> None:
        data = {"date": "2026-12-25", "portrait_variant": "christmas",
                "foreground_slot": "2026-12-25-1"}
        chosen = select_foreground_overlays(data)
        self.assertIsNone(chosen["weather"])
        self.assertIsNone(chosen["visitor"])

    def test_overlay_vocabulary_excludes_flowers(self) -> None:
        visitors, weather = set(), set()
        for day in range(1, 29):
            for slot in range(4):
                chosen = select_foreground_overlays({
                    "date": f"2026-10-{day:02d}", "portrait_variant": "dusk_rain",
                    "foreground_slot": f"2026-10-{day:02d}-{slot}",
                })
                visitors.add(chosen["visitor"])
                weather.add(chosen["weather"])
        self.assertTrue(visitors <= {None, "fox", "rabbit", "hedgehog", "cat", "gnome"})
        self.assertTrue(weather <= {None, "puddles", "mud-tracks"})
        self.assertIn("cat", visitors)


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
