"""The progress screen keeps the run's events in a live feed, newest first.

The status line overwrote each message with the next, so a glossary built, a missed term fixed or
a fit pass that shrank forty blocks went by unseen. The feed lists them as they happen.
"""

from __future__ import annotations

from layoutkeep.ui.activity_feed import FEED_KEEP, ActivityFeed
from layoutkeep.ui.progress import ProgressWidget


def test_events_are_listed_newest_first_without_repeats(qtbot):
    feed = ActivityFeed()
    qtbot.addWidget(feed)
    for text in ("one", "two", "two", "three"):
        feed.add(text)
    assert feed.texts() == ["three", "two", "one"]


def test_only_the_last_events_are_kept(qtbot):
    feed = ActivityFeed()
    qtbot.addWidget(feed)
    for n in range(FEED_KEEP + 5):
        feed.add(f"event {n}")
    assert feed.count() == FEED_KEEP and feed.texts()[0] == f"event {FEED_KEEP + 4}"


def test_the_progress_screen_feeds_its_phases_and_flags(qtbot):
    screen = ProgressWidget()
    qtbot.addWidget(screen)
    screen.start(10, 100)
    screen.set_status("translating")
    screen.set_review_flags(3, 5)
    texts = screen._feed.texts()
    assert len(texts) == 2 and "3" in texts[0]
    screen.start(10, 100)
    assert screen._feed.texts() == [], "a new run starts with an empty feed"
