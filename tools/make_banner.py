"""Render the project banner, in one language per run.

Drawn rather than assembled by hand so it can be regenerated when the wording or the palette
changes, and so both languages are guaranteed to be the same picture with different text.

    .venv/Scripts/python.exe tools/make_banner.py en docs/images/banner_en.png
    .venv/Scripts/python.exe tools/make_banner.py tr docs/images/banner_tr.png
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication

WIDTH, HEIGHT = 1280, 640

#: The two ends of the brand gradient, from docs/DESIGN.md's dark palette.
DEEP = QColor("#0b1220")
BLUE = QColor("#1d4ed8")
ACCENT = QColor("#3b82f6")
TEXT = QColor("#f8fafc")
MUTED = QColor("#94a3b8")

TEXTS = {
    "en": {
        "tagline": "Layout-preserving document translator",
        "pitch": "Translate a document and get the same document back -\nnot a wall of text where a page used to be.",
        "points": [
            "PDF, EPUB, DOCX, HTML and scanned images",
            "Columns, tables, figures and styling stay put",
            "Local models or DeepL - your files can stay on the machine",
        ],
        "footer": "Open source - AGPL-3.0",
    },
    "tr": {
        "tagline": "Düzen koruyan belge çevirmeni",
        "pitch": "Belgeyi çevir, aynı belgeyi geri al -\nsayfanın yerinde bir metin yığını değil.",
        "points": [
            "PDF, EPUB, DOCX, HTML ve taranmış görseller",
            "Kolonlar, tablolar, şekiller ve biçimlendirme yerinde kalır",
            "Yerel modeller veya DeepL - dosyalar makinede kalabilir",
        ],
        "footer": "Açık kaynak - AGPL-3.0",
    },
}


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def _draw_background(painter: QPainter) -> None:
    gradient = QLinearGradient(QPointF(0, 0), QPointF(WIDTH, HEIGHT))
    gradient.setColorAt(0.0, DEEP)
    gradient.setColorAt(1.0, BLUE)
    painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), gradient)

    # A faint page grid on the right half: the subject is documents, and an empty gradient
    # says nothing about them.
    painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
    for index in range(3):
        page = QRectF(760 + index * 34, 150 + index * 26, 300, 380)
        painter.drawRoundedRect(page, 10, 10)
    painter.setPen(QPen(QColor(255, 255, 255, 34), 2))
    for row in range(11):
        y = 210 + row * 28
        painter.drawLine(QPointF(848, y), QPointF(1040 if row % 3 else 980, y))


def _draw_logo(painter: QPainter, x: float, y: float, size: int) -> None:
    from layoutkeep.ui.branding import logo_pixmap

    pixmap = logo_pixmap(size)
    if not pixmap.isNull():
        painter.drawPixmap(int(x), int(y), pixmap)


def build(language: str, target: Path) -> Path:
    strings = TEXTS[language]
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    _draw_background(painter)
    _draw_logo(painter, 80, 76, 84)

    painter.setPen(TEXT)
    painter.setFont(_font(64, QFont.Weight.ExtraBold))
    painter.drawText(QRectF(184, 78, 620, 80), int(Qt.AlignmentFlag.AlignVCenter), "LayoutKeep")

    painter.setPen(ACCENT)
    painter.setFont(_font(24, QFont.Weight.DemiBold))
    painter.drawText(QRectF(186, 148, 620, 34), int(Qt.AlignmentFlag.AlignVCenter), strings["tagline"])

    painter.setPen(TEXT)
    painter.setFont(_font(28, QFont.Weight.Medium))
    painter.drawText(
        # Tall enough for three wrapped lines: at 100 the third was sliced through the middle,
        # which is worse than not having it.
        QRectF(80, 226, 640, 130),
        int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
        strings["pitch"],
    )

    painter.setFont(_font(21))
    for index, point in enumerate(strings["points"]):
        top = 372 + index * 46
        painter.setPen(QPen(ACCENT, 3))
        painter.drawLine(QPointF(84, top + 14), QPointF(100, top + 14))
        painter.setPen(MUTED)
        painter.drawText(
            QRectF(116, top, 620, 40),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
            point,
        )

    painter.setPen(QColor(148, 163, 184, 200))
    painter.setFont(_font(18))
    painter.drawText(QRectF(84, 552, 620, 30), int(Qt.AlignmentFlag.AlignVCenter), strings["footer"])

    painter.end()
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(target))
    return target


def main() -> int:
    language = sys.argv[1] if len(sys.argv) > 1 else "en"
    if language not in TEXTS:
        print(f"dil bilinmiyor: {language} (en, tr)")
        return 2
    target = Path(sys.argv[2] if len(sys.argv) > 2 else f"docs/images/banner_{language}.png")

    QApplication.instance() or QApplication([])
    written = build(language, target)
    print(f"{written} yazildi ({written.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
