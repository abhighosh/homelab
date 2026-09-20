"""Small, testable E1001 page-selection state machine (not firmware wiring)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


PAGES = ("portrait", "today", "map", "almanac", "constellations", "surprise")
RANDOM_PAGES = PAGES[:-1]


@dataclass
class ScreenMode:
    page: str = "portrait"
    shown: str = "portrait"
    random_interval_seconds: int = 3600
    last_random_change: float = 0.0
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        if self.page not in PAGES or self.shown not in RANDOM_PAGES:
            raise ValueError("Invalid screen")

    def select(self, page: str, now: float) -> str:
        if page not in PAGES:
            raise ValueError(page)
        self.page = page
        if page == "surprise":
            return self.reroll(now)
        self.shown = page
        return self.shown

    def move(self, direction: int, now: float) -> str:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        return self.select(PAGES[(PAGES.index(self.page) + direction) % len(PAGES)], now)

    def reroll(self, now: float) -> str:
        if self.page != "surprise":
            return self.shown
        choices = [page for page in RANDOM_PAGES if page != self.shown]
        self.shown = self.rng.choice(choices)
        self.last_random_change = now
        return self.shown

    def green_button(self, now: float) -> str:
        if self.page == "surprise":
            return self.reroll(now)
        return self.select("portrait", now)

    def hourly_tick(self, now: float) -> str:
        if self.page == "surprise" and now - self.last_random_change >= self.random_interval_seconds:
            return self.reroll(now)
        return self.shown
