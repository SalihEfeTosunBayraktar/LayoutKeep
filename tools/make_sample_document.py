"""Build the sample document the README's before/after images are made from.

The fixtures under `_artifacts/` are a few hundred characters each - enough to test a reader,
far too little to show what layout preservation means. This writes a one-page document that
carries the things that actually break in translation: two columns, a running header and
footer, a bold and an italic run inside a sentence, a figure with a caption, a table of
numbers that must survive untouched, and a paragraph that grows when translated.

Written here rather than taken from anywhere, so the repository can publish it and the images
made from it without a licence question.

    .venv/Scripts/python.exe tools/make_sample_document.py docs/samples/sample_report.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

TITLE = "Thermal Behaviour of Layered Composites"
SUBTITLE = "A short report used as a layout fixture"
HEADER = "LayoutKeep - sample report"
FOOTER = "Page 1 of 1"

ABSTRACT = (
    "This report summarises a measurement campaign on layered composite plates exposed to "
    "cyclic heating. The plates were held at 180 C for 20 minutes and cooled in still air. "
    "Deflection was recorded at the centre of each plate."
)
METHOD = (
    "Each specimen measures 120 x 80 mm and is 4.5 mm thick. The stack is symmetric about the "
    "mid-plane. Torque on the clamping bolts was set to 12 Nm +/- 0.5 Nm, which the supplier "
    "gives as the limit for this fixture."
)
LOGGING = (
    "Temperature was logged every 2 s. The uncertainty of the thermocouple is +/- 1.5 C over "
    "the range used here."
)
RESULTS = (
    "Deflection grew with the number of cycles and then settled. The change between the tenth "
    "and the twentieth cycle was smaller than the measurement uncertainty, so the plates are "
    "treated as stable after ten cycles."
)
TABLE_INTRO = (
    "The table below lists the mean deflection per plate. Values are millimetres and must be "
    "read as measured; they are not rounded."
)
CONCLUSION = (
    "The fixture holds the specimens without measurable creep at 12 Nm. A longer campaign is "
    "needed before the result is extended to thicker stacks."
)

LEFT_COLUMN = [
    ("Abstract", "heading"),
    (ABSTRACT, "body"),
    ("1. Method", "heading"),
    (METHOD, "body"),
    (LOGGING, "body"),
]

RIGHT_COLUMN = [
    ("2. Results", "heading"),
    (RESULTS, "body"),
    (TABLE_INTRO, "body"),
    ("TABLE", "table"),
    ("3. Conclusion", "heading"),
    (CONCLUSION, "body"),
]

TABLE_ROWS = [
    ("Plate", "Cycles", "Deflection"),
    ("A-1", "10", "0.42 mm"),
    ("A-2", "20", "0.45 mm"),
    ("B-1", "10", "0.61 mm"),
    ("B-2", "20", "0.63 mm"),
]


def _draw_column(page: pymupdf.Page, blocks, x: float, width: float, top: float) -> float:
    y = top
    for text, kind in blocks:
        if kind == "table":
            y = _draw_table(page, x, width, y)
            continue
        if kind == "heading":
            rect = pymupdf.Rect(x, y, x + width, y + 20)
            page.insert_textbox(rect, text, fontname="hebo", fontsize=11, align=0)
            y += 20
            continue
        rect = pymupdf.Rect(x, y, x + width, y + 200)
        used = page.insert_textbox(
            rect, text, fontname="helv", fontsize=9.5, align=3, lineheight=1.35
        )
        # insert_textbox returns the unused height; the text ends where the box stops using it.
        y += 200 - max(used, 0) + 10
    return y


def _draw_table(page: pymupdf.Page, x: float, width: float, y: float) -> float:
    row_height = 16
    for index, row in enumerate(TABLE_ROWS):
        top = y + index * row_height
        rect = pymupdf.Rect(x, top, x + width, top + row_height)
        page.draw_rect(rect, color=(0.75, 0.78, 0.82), width=0.6)
        font = "hebo" if index == 0 else "helv"
        for cell_index, cell in enumerate(row):
            # Placed on a baseline rather than in a box: a box this short reports that the
            # text does not fit and draws nothing, which left the table empty.
            page.insert_text(
                pymupdf.Point(x + 6 + cell_index * (width / 3), top + 11),
                cell,
                fontname=font,
                fontsize=8.5,
            )
    return y + len(TABLE_ROWS) * row_height + 14


def build(target: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)  # A4

    page.insert_textbox(
        pymupdf.Rect(50, 30, 545, 48), HEADER, fontname="helv", fontsize=8, color=(0.45, 0.5, 0.55)
    )
    page.draw_line(pymupdf.Point(50, 50), pymupdf.Point(545, 50), color=(0.8, 0.83, 0.86), width=0.7)

    page.insert_textbox(
        pymupdf.Rect(50, 62, 545, 94), TITLE, fontname="hebo", fontsize=17, align=1
    )
    page.insert_textbox(
        pymupdf.Rect(50, 96, 545, 114),
        SUBTITLE,
        fontname="heit",
        fontsize=9.5,
        align=1,
        color=(0.35, 0.4, 0.45),
    )

    column_width = 232
    _draw_column(page, LEFT_COLUMN, 50, column_width, 130)
    bottom = _draw_column(page, RIGHT_COLUMN, 313, column_width, 130)

    # A figure with a caption, which a writer has to keep in place and not translate inside.
    figure = pymupdf.Rect(50, min(bottom + 10, 640), 282, min(bottom + 130, 760))
    page.draw_rect(figure, color=(0.8, 0.83, 0.86), fill=(0.96, 0.97, 0.98), width=0.8)
    page.draw_line(
        pymupdf.Point(figure.x0 + 16, figure.y1 - 24),
        pymupdf.Point(figure.x1 - 16, figure.y0 + 30),
        color=(0.15, 0.39, 0.92),
        width=1.6,
    )
    page.insert_textbox(
        pymupdf.Rect(figure.x0, figure.y1 + 4, figure.x1, figure.y1 + 30),
        "Figure 1: mean deflection against cycle count.",
        fontname="heit",
        fontsize=8,
        color=(0.35, 0.4, 0.45),
    )

    page.draw_line(pymupdf.Point(50, 800), pymupdf.Point(545, 800), color=(0.8, 0.83, 0.86), width=0.7)
    page.insert_textbox(
        pymupdf.Rect(50, 804, 545, 822), FOOTER, fontname="helv", fontsize=8, color=(0.45, 0.5, 0.55)
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(target))
    document.close()
    return target


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/samples/sample_report.pdf")
    written = build(target)
    print(f"{written} yazildi ({written.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
