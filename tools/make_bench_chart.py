"""Draw the phase breakdown of one or more benchmark runs.

`bench_pipeline.py` writes what each stage of a translation cost as JSON. This turns those
numbers into one picture: a stacked bar per run, so the answer to "where did the time go" is
visible rather than counted off a table.

    .venv/Scripts/python.exe tools/make_bench_chart.py docs/samples/bench_*.json out.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

WIDTH = 1180
MARGIN = 64

#: Chrome above the bars, chrome below them, and what one bar costs. The image is only as tall
#: as the runs it carries, so two runs do not sit in a page of empty space.
_HEAD, _FOOT, _ROW = 110, 140, 120

PAPER = QColor("#f7f8fb")
INK = QColor("#101a2b")
MUTED = QColor("#6b788c")
RULE = QColor("#dfe4ec")

#: One colour per phase, in the order the pipeline runs them. Read is barely visible on purpose:
#: it is barely any of the time, and a chart that gives it a fat band would say otherwise.
PHASE_COLORS = {
    "read": QColor("#94a3b8"),
    "segment": QColor("#64748b"),
    "translate": QColor("#1d4ed8"),
    "fit": QColor("#0d9488"),
    "apply": QColor("#7c3aed"),
    "write pdf": QColor("#ea7317"),
    "write docx": QColor("#0f766e"),
    "write html": QColor("#0891b2"),
}


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def _load(paths: list[Path]) -> list[dict]:
    runs = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_total"] = sum(phase["seconds"] for phase in data["phases"])
        runs.append(data)
    return runs


def draw(runs: list[dict], target: Path) -> Path:
    height = _HEAD + _ROW * max(len(runs), 1) + _FOOT
    image = QImage(WIDTH, height, QImage.Format.Format_RGB32)
    image.fill(PAPER)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    painter.setPen(INK)
    painter.setFont(_font(24, QFont.Weight.DemiBold))
    painter.drawText(QRectF(MARGIN, 26, WIDTH - 2 * MARGIN, 32), 0,
                     "Where the time goes in one translation")
    painter.setPen(MUTED)
    painter.setFont(_font(15))
    subtitle = runs[0]["document"] if runs else ""
    pages = runs[0].get("pages", 0) if runs else 0
    chars = runs[0].get("characters", 0) if runs else 0
    painter.drawText(QRectF(MARGIN, 60, WIDTH - 2 * MARGIN, 24), 0,
                     f"{subtitle} - {pages} pages, {chars:,} characters")

    plot = QRectF(MARGIN + 108, _HEAD, WIDTH - MARGIN * 2 - 130, _ROW * max(len(runs), 1))
    longest = max((run["_total"] for run in runs), default=1.0)
    scale = plot.width() / (longest * 1.08)

    # Grid: one line per 60 seconds, labelled in minutes where that reads better.
    step = 60.0 if longest > 180 else 15.0
    ticks = int(longest / step) + 2
    painter.setFont(_font(12))
    for index in range(ticks):
        seconds = index * step
        x = plot.x() + seconds * scale
        if x > plot.right():
            break
        painter.setPen(QPen(RULE, 1))
        painter.drawLine(QPointF(x, plot.y() - 6), QPointF(x, plot.bottom() + 6))
        painter.setPen(MUTED)
        label = f"{seconds / 60:.0f} min" if step >= 60 else f"{seconds:.0f} s"
        painter.drawText(QRectF(x - 30, plot.bottom() + 12, 60, 18),
                         int(Qt.AlignmentFlag.AlignHCenter), label)

    bar_h = _ROW - 46.0
    for index, run in enumerate(runs):
        top = plot.y() + index * (bar_h + 46)

        # The label column runs from the left edge to 18px short of the plot, so a two-word
        # total and a request count each get a line of their own rather than being clipped.
        label_w = plot.x() - MARGIN / 2 - 18
        painter.setPen(INK)
        painter.setFont(_font(16, QFont.Weight.DemiBold))
        painter.drawText(QRectF(MARGIN / 2, top + bar_h / 2 - 30, label_w, 22),
                         int(Qt.AlignmentFlag.AlignRight), run["provider"])
        painter.setPen(MUTED)
        painter.setFont(_font(12))
        painter.drawText(QRectF(MARGIN / 2, top + bar_h / 2 - 4, label_w, 18),
                         int(Qt.AlignmentFlag.AlignRight), f"{run['_total']:.0f} s total")
        if run.get("requests"):
            painter.drawText(QRectF(MARGIN / 2, top + bar_h / 2 + 14, label_w, 18),
                             int(Qt.AlignmentFlag.AlignRight),
                             f"{run['requests']} requests")

        x = plot.x()
        for phase in run["phases"]:
            width = phase["seconds"] * scale
            colour = PHASE_COLORS.get(phase["name"], QColor("#94a3b8"))
            painter.fillRect(QRectF(x, top, max(width, 1.0), bar_h), colour)
            # Label inside the band when it is wide enough to hold the text, above it otherwise.
            share = phase["seconds"] / (run["_total"] or 1) * 100
            if width > 86:
                painter.setPen(QColor("#ffffff"))
                painter.setFont(_font(13, QFont.Weight.DemiBold))
                painter.drawText(QRectF(x + 8, top + bar_h / 2 - 20, width - 16, 18),
                                 0, phase["name"])
                painter.setFont(_font(12))
                painter.drawText(QRectF(x + 8, top + bar_h / 2, width - 16, 18), 0,
                                 f"{phase['seconds']:.0f} s · {share:.0f}%")
            x += width

        painter.setPen(QPen(RULE, 1))
        painter.drawRect(QRectF(plot.x(), top, max(run["_total"] * scale, 1.0), bar_h))

    # Legend for the bands too narrow to carry their own label.
    legend_y = height - 96
    painter.setFont(_font(12))
    x = MARGIN + 108
    for name, colour in PHASE_COLORS.items():
        if not any(any(p["name"] == name for p in run["phases"]) for run in runs):
            continue
        painter.fillRect(QRectF(x, legend_y, 12, 12), colour)
        painter.setPen(MUTED)
        painter.drawText(QRectF(x + 18, legend_y - 3, 130, 18), 0, name)
        x += 18 + painter.fontMetrics().horizontalAdvance(name) + 26

    painter.setPen(MUTED)
    painter.setFont(_font(12))
    flagged = runs[0].get("flagged", 0) if runs else 0
    segments = runs[0].get("segments", 0) if runs else 0
    painter.drawText(
        QRectF(MARGIN + 108, height - 58, WIDTH - MARGIN * 2, 18), 0,
        f"{segments:,} segments, {flagged} flagged for review - measured with "
        f"tools/bench_pipeline.py",
    )

    painter.end()
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(target))
    return target


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    paths = [Path(arg) for arg in sys.argv[1:-1]]
    target = Path(sys.argv[-1])

    QApplication.instance() or QApplication([])
    runs = _load(paths)
    written = draw(runs, target)
    print(f"{written} yazildi ({written.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
