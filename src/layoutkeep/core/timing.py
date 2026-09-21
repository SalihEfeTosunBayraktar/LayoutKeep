"""Where the time went: phase timings for one run, and the report that shows them.

Written because "why did that take an hour" is unanswerable after the fact. Each phase is timed as it
happens - read, segment, translate, fit, apply, write - and the run can write the breakdown next to
its own output. The report is one self-contained HTML file: no scripts, no network, opens anywhere.
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Phase:
    """One stage of a run, however long it took."""

    name: str
    seconds: float
    detail: str = ""


@dataclass
class TimingReport:
    """The phases of one run, in the order they happened."""

    document: str = ""
    provider: str = ""
    requests: int = 0
    flagged: int = 0
    phases: list[Phase] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(p.seconds for p in self.phases)

    def add(self, name: str, seconds: float, detail: str = "") -> None:
        """Record one phase. Its own method so callers never touch the list directly."""
        self.phases.append(Phase(name=name, seconds=seconds, detail=detail))

    def percent(self, phase: Phase) -> float:
        total = self.total
        return (phase.seconds / total * 100.0) if total > 0 else 0.0

    def write_html(self, path: str | Path) -> Path:
        """Write the report and return where it landed."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.as_html(), encoding="utf-8")
        return target

    def as_html(self) -> str:
        """The whole report as one self-contained page."""
        return _HTML_TEMPLATE.format(
            title=html.escape(self.document or "translation"),
            subtitle=html.escape(self.subtitle),
            bars=self._bars_html(),
            legend=self._legend_html(),
            footer=html.escape(self.footer),
        )

    @property
    def subtitle(self) -> str:
        parts = [self.document or "translation", f"{self._format(self.total)} total"]
        if self.provider:
            parts.append(self.provider)
        if self.requests:
            parts.append(f"{self.requests} requests")
        return " - ".join(parts)

    @property
    def footer(self) -> str:
        parts = [f"{len(self.phases)} phases, {self._format(self.total)} total"]
        if self.requests:
            parts.append(f"{self.requests} provider requests")
        if self.flagged:
            parts.append(f"{self.flagged} segments flagged for review")
        return " - ".join(parts)

    def _bars_html(self) -> str:
        """One row per phase: a bar sized by its share of the total, then the numbers."""
        if not self.phases:
            return '<p class="empty">No phases were recorded.</p>'
        rows = []
        for phase in self.phases:
            share = self.percent(phase)
            rows.append(
                '<div class="bar-row">'
                f'<div class="bar-label">{html.escape(phase.name)}</div>'
                '<div class="bar-track">'
                f'<div class="bar-fill" style="width: {share:.2f}%"></div>'
                f'<span class="bar-text">{self._format(phase.seconds)} - {share:.0f}%</span>'
                "</div>"
                f'<div class="bar-detail">{html.escape(phase.detail)}</div>'
                "</div>"
            )
        return "\n".join(rows)

    def _legend_html(self) -> str:
        return "".join(
            f'<span class="legend-item" title="{self._format(p.seconds)}">'
            f"{html.escape(p.name)}</span>"
            for p in self.phases
        )

    @staticmethod
    def _format(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.1f} s"
        minutes, rest = divmod(seconds, 60)
        return f"{int(minutes)} min {rest:.0f} s"


class PhaseTimer:
    """Times named phases in order: `with timer.phase("read", "12 pages"): ...`."""

    def __init__(self, report: TimingReport) -> None:
        self.report = report

    def phase(self, name: str, detail: str = "") -> _PhaseScope:
        return _PhaseScope(self.report, name, detail)


class _PhaseScope:
    """The object the `with` statement holds. Separate so the timer itself stays stateless."""

    def __init__(self, report: TimingReport, name: str, detail: str) -> None:
        self._report = report
        self._name = name
        self._detail = detail

    def __enter__(self) -> _PhaseScope:
        self._started = time.monotonic()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._report.add(self._name, time.monotonic() - self._started, self._detail)


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Where the time goes - {title}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; padding: 28px 32px; background: #f7f7f8; color: #1b1b1f;
         font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }}
  h1 {{ margin: 0 0 4px; font-size: 24px; }}
  .subtitle {{ color: #5a5a66; margin-bottom: 22px; }}
  .bar-row {{ display: grid; grid-template-columns: 120px 1fr 260px; gap: 12px;
             align-items: center; margin-bottom: 10px; }}
  .bar-label {{ font-weight: 600; }}
  .bar-track {{ position: relative; background: #e6e6ea; border-radius: 4px; height: 26px; }}
  .bar-fill {{ background: #1f5fd0; border-radius: 4px; height: 100%; }}
  .bar-text {{ position: absolute; left: 8px; top: 4px; color: #10111a; font-size: 13px; }}
  .bar-detail {{ color: #5a5a66; font-size: 13px; }}
  .legend {{ margin-top: 18px; color: #5a5a66; font-size: 13px; }}
  .legend-item {{ margin-right: 12px; }}
  .footer {{ margin-top: 10px; color: #5a5a66; font-size: 13px; }}
  .empty {{ color: #5a5a66; }}
</style>
</head>
<body>
<h1>Where the time goes in one translation</h1>
<div class="subtitle">{subtitle}</div>
{bars}
<div class="legend">{legend}</div>
<div class="footer">{footer}</div>
</body>
</html>
"""
