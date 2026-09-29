"""The live feed on the progress screen: every phase and event of the run, newest first.

The progress card had one status line, and each message overwrote the one before: the glossary
being built, a missed term fixed, the fit pass shrinking blocks - all of it happened out of sight
and the screen looked the same from the first minute to the last. The feed keeps the last few
events with the time they happened, so a run shows what it is doing while it does it.
"""

from __future__ import annotations

import time

from PySide6.QtWidgets import QListWidget, QListWidgetItem

#: How many events stay visible; older ones scroll off.
FEED_KEEP = 12


class ActivityFeed(QListWidget):
    """A short, newest-first list of the run's events, each with its clock time."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("activityFeed")
        self.setProperty("class", "muted")
        self.setFocusPolicy(self.focusPolicy().NoFocus)
        self.setMaximumHeight(118)
        self._last = ""

    def add(self, text: str) -> None:
        """Put `text` at the top, unless it repeats the event already there."""
        text = " ".join(str(text).split())
        if not text or text == self._last:
            return
        self._last = text
        self.insertItem(0, QListWidgetItem(f"{time.strftime('%H:%M:%S')}  {text}"))
        while self.count() > FEED_KEEP:
            self.takeItem(self.count() - 1)

    def start_over(self) -> None:
        self.clear()
        self._last = ""

    def texts(self) -> list[str]:
        """The events on screen, newest first, without their times (for tests and logs)."""
        return [self.item(i).text().split("  ", 1)[-1] for i in range(self.count())]
