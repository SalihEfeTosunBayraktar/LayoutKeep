"""Build a long academic-style paper to translate, of the kind that actually breaks converters.

The one-page sample in `docs/samples/` shows what layout preservation means. It does not show
whether the thing holds up over a hundred pages, and the parts that fail at that length are the
ones this generator puts in: two-column body text that wraps differently once translated, tables
whose header rows must survive, and charts whose axis labels, tick labels and legends are text
drawn inside a picture - a translator that treats a figure as an opaque image leaves those in
the source language, and one that treats them as body text scatters them.

Everything here is written for this fixture, so the repository can publish the document and the
images made from it without a licence question.

    .venv/Scripts/python.exe tools/make_academic_paper.py docs/samples/academic_paper.pdf 100
"""

from __future__ import annotations

import io
import itertools
import math
import random
import sys
from pathlib import Path

import pymupdf

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 54.0
GUTTER = 18.0
COLUMN_W = (PAGE_W - 2 * MARGIN - GUTTER) / 2
BODY_TOP = 96.0
BODY_BOTTOM = PAGE_H - 66.0

TITLE = "Thermal Fatigue of Layered Composite Plates: A Measurement Campaign"
AUTHORS = "E. Lindqvist, M. Aydin, R. Castellani"
AFFILIATION = "Institute for Structural Materials, Department of Mechanical Engineering"
RUNNING_HEAD = "Lindqvist et al. - Thermal Fatigue of Layered Composite Plates"

INK = (0.06, 0.09, 0.15)
MUTED = (0.42, 0.47, 0.55)
RULE = (0.80, 0.83, 0.87)
ACCENT = (0.11, 0.31, 0.85)
ACCENT_2 = (0.85, 0.42, 0.13)
PANEL = (0.965, 0.972, 0.98)

SECTIONS = [
    ("Introduction", ["Motivation", "Scope of this study", "Related measurements"]),
    ("Materials", ["Laminate stacking", "Resin system", "Specimen preparation"]),
    ("Method", ["Thermal cycling rig", "Instrumentation", "Uncertainty budget"]),
    ("Results", ["Deflection against cycle count", "Effect of stacking order", "Residual stiffness"]),
    ("Discussion", ["Comparison with the analytical model", "Limits of the fixture"]),
    ("Conclusion", ["Findings", "Further work"]),
]

PARAGRAPHS = [
    ("The plates were held at {temp} C for {minutes} minutes and cooled in still air before the "
    "next cycle began. Deflection was recorded at the centre of each plate with a dial gauge "
    "reading to {precision} mm, and the reading was taken once the surface had returned to "
    "ambient temperature."),
    ("Each specimen measures 120 x 80 mm and is {thickness} mm thick. The stack is symmetric "
    "about the mid-plane, which removes the bending-extension coupling that would otherwise "
    "dominate the response at this aspect ratio."),
    ("Torque on the clamping bolts was set to {torque} Nm, which the supplier gives as the limit "
    "for this fixture. Above that figure the washers begin to bite into the laminate and the "
    "boundary condition is no longer the one the model assumes."),
    ("Temperature was logged every {interval} s. The uncertainty of the thermocouple is "
    "{uncertainty} C over the range used here, and the logger adds a further quantisation error "
    "of half a least significant bit."),
    ("Deflection grew with the number of cycles and then settled. The change between the tenth "
    "and the twentieth cycle was smaller than the measurement uncertainty, so the plates are "
    "treated as stable after ten cycles for the purposes of this report."),
    ("The analytical model assumes a perfectly clamped edge. The measured stiffness sits "
    "{percent} per cent below that prediction, which is consistent with the compliance of the "
    "fixture itself rather than with damage in the laminate."),
    ("No delamination was visible under the optical microscope at {magnification}x after the "
    "full campaign. That does not rule out matrix microcracking below the resolution of the "
    "instrument, and the residual stiffness measurement is the more sensitive indicator."),
    ("Two specimens were removed from the campaign after cycle {cycle}: one because a "
    "thermocouple detached, and one because the clamping torque had relaxed below the "
    "tolerance band. Their partial series are excluded from the averages reported here."),
    ("The rig heats the specimen from one side only. A through-thickness gradient of "
    "{gradient} C was measured at steady state, which is small compared with the excursion but "
    "not negligible when the residual stress is estimated from the free-edge condition."),
    ("Values in this section are means over {count} specimens unless stated otherwise. The "
    "spread is reported as the sample standard deviation rather than the standard error, "
    "because the quantity of interest is the behaviour of an individual plate."),
]

CAPTIONS = [
    "Mean deflection against cycle count for the three stacking sequences.",
    "Residual stiffness after thermal cycling, normalised to the as-received value.",
    "Through-thickness temperature gradient at steady state.",
    "Deflection spread across specimens, by cycle count.",
    "Surface of specimen B-2 after the full campaign.",
]

TABLE_HEADERS = [
    ("Plate", "Cycles", "Deflection", "Spread"),
    ("Stacking", "Thickness", "Stiffness", "Change"),
    ("Specimen", "Peak temp.", "Gradient", "Note"),
]

_random = random.Random(20260909)


def _png(size: tuple[int, int], seed: int) -> bytes:
    """A synthetic micrograph. Raster content the writer has to carry across formats."""
    from PIL import Image, ImageDraw

    rng = random.Random(seed)
    image = Image.new("RGB", size, (232, 234, 238))
    draw = ImageDraw.Draw(image)
    for _ in range(160):
        x, y = rng.randrange(size[0]), rng.randrange(size[1])
        r = rng.randrange(2, 9)
        shade = rng.randrange(90, 190)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(shade, shade - 6, shade - 12))
    for _ in range(12):
        x0, y0 = rng.randrange(size[0]), rng.randrange(size[1])
        draw.line([x0, y0, x0 + rng.randrange(-40, 40), y0 + rng.randrange(-25, 25)],
                  fill=(70, 74, 82), width=1)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _text(page: pymupdf.Page, rect: pymupdf.Rect, text: str, *, font="helv", size=9.0,
          align=0, color=INK, leading=1.32) -> float:
    """Draw text into `rect`, returning the height it did not use."""
    return page.insert_textbox(
        rect, text, fontname=font, fontsize=size, align=align, color=color, lineheight=leading
    )


def _chart(page: pymupdf.Page, rect: pymupdf.Rect, index: int) -> None:
    """A line chart with axis labels, tick labels and a legend - all of it text inside a figure.

    This is the part a translator gets wrong in one of two ways: leaving the labels in the
    source language because the figure is treated as an image, or lifting them into the body
    text because they are treated as prose.
    """
    page.draw_rect(rect, color=RULE, fill=PANEL, width=0.7)
    plot = pymupdf.Rect(rect.x0 + 38, rect.y0 + 14, rect.x1 - 10, rect.y1 - 30)

    page.draw_line(pymupdf.Point(plot.x0, plot.y0), pymupdf.Point(plot.x0, plot.y1),
                   color=MUTED, width=0.8)
    page.draw_line(pymupdf.Point(plot.x0, plot.y1), pymupdf.Point(plot.x1, plot.y1),
                   color=MUTED, width=0.8)

    for step in range(4):
        y = plot.y1 - step * plot.height / 3.0
        page.draw_line(pymupdf.Point(plot.x0 - 3, y), pymupdf.Point(plot.x0, y),
                       color=MUTED, width=0.6)
        page.insert_text(pymupdf.Point(rect.x0 + 12, y + 2.5), f"{step * 0.2:.1f}",
                         fontname="helv", fontsize=6.0, color=MUTED)
    for step in range(4):
        x = plot.x0 + step * plot.width / 3.0
        page.draw_line(pymupdf.Point(x, plot.y1), pymupdf.Point(x, plot.y1 + 3),
                       color=MUTED, width=0.6)
        page.insert_text(pymupdf.Point(x - 4, plot.y1 + 11), str(step * 10),
                         fontname="helv", fontsize=6.0, color=MUTED)

    for series, colour in ((0, ACCENT), (1, ACCENT_2)):
        points = []
        for step in range(11):
            x = plot.x0 + step * plot.width / 10.0
            level = 1 - math.exp(-0.32 * step - 0.12 * series)
            y = plot.y1 - level * plot.height * (0.82 - 0.14 * series)
            points.append(pymupdf.Point(x, y))
        for start, end in itertools.pairwise(points):
            page.draw_line(start, end, color=colour, width=1.5)

    legend_y = plot.y0 + 6
    for offset, (label, colour) in enumerate((("Symmetric", ACCENT), ("Asymmetric", ACCENT_2))):
        x = plot.x1 - 96
        page.draw_line(pymupdf.Point(x, legend_y + offset * 11 - 2.5),
                       pymupdf.Point(x + 12, legend_y + offset * 11 - 2.5), color=colour, width=1.5)
        page.insert_text(pymupdf.Point(x + 17, legend_y + offset * 11), label,
                         fontname="helv", fontsize=6.5, color=INK)

    page.insert_text(pymupdf.Point(plot.x0 + plot.width / 2 - 26, rect.y1 - 6),
                     "Cycle count", fontname="helv", fontsize=6.5, color=MUTED)
    page.insert_text(pymupdf.Point(rect.x0 + 8, plot.y0 - 2), "Deflection (mm)",
                     fontname="helv", fontsize=6.5, color=MUTED)


def _table(page: pymupdf.Page, x: float, width: float, y: float, index: int) -> float:
    header = TABLE_HEADERS[index % len(TABLE_HEADERS)]
    rows = [
        (f"{chr(65 + row)}-{row + 1}", f"{(row + 1) * 10}", f"0.{40 + row * 7} mm",
         f"±0.0{row + 2}")
        for row in range(4)
    ]
    row_h = 13.0
    col_w = width / len(header)
    for row_index, row in enumerate([header, *rows]):
        top = y + row_index * row_h
        page.draw_rect(pymupdf.Rect(x, top, x + width, top + row_h), color=RULE, width=0.5)
        for cell_index, cell in enumerate(row):
            page.insert_text(
                pymupdf.Point(x + 4 + cell_index * col_w, top + 9),
                cell,
                fontname="hebo" if row_index == 0 else "helv",
                fontsize=6.8,
                color=INK,
            )
    return y + (len(rows) + 1) * row_h + 6


def _paragraph_text(index: int) -> str:
    template = PARAGRAPHS[index % len(PARAGRAPHS)]
    return template.format(
        temp=_random.choice([160, 170, 180, 190]),
        minutes=_random.choice([15, 20, 25]),
        precision="0.01",
        thickness=_random.choice(["3.0", "4.5", "6.0"]),
        torque=f"{_random.choice([10, 12, 14])} +/- 0.5",
        interval=_random.choice([1, 2, 5]),
        uncertainty="+/- 1.5",
        percent=_random.choice([6, 8, 11, 14]),
        magnification=_random.choice([50, 100, 200]),
        cycle=_random.choice([12, 18, 24]),
        gradient=_random.choice([3, 5, 7]),
        count=_random.choice([4, 5, 6]),
    )


def _page_furniture(page: pymupdf.Page, number: int) -> None:
    page.insert_textbox(pymupdf.Rect(MARGIN, 34, PAGE_W - MARGIN, 50), RUNNING_HEAD,
                        fontname="helv", fontsize=7.5, color=MUTED)
    page.draw_line(pymupdf.Point(MARGIN, 54), pymupdf.Point(PAGE_W - MARGIN, 54),
                   color=RULE, width=0.6)
    page.draw_line(pymupdf.Point(MARGIN, PAGE_H - 52), pymupdf.Point(PAGE_W - MARGIN, PAGE_H - 52),
                   color=RULE, width=0.6)
    page.insert_textbox(pymupdf.Rect(MARGIN, PAGE_H - 46, PAGE_W - MARGIN, PAGE_H - 30),
                        f"{number}", fontname="helv", fontsize=8, align=1, color=MUTED)


def _title_page(document: pymupdf.Document) -> None:
    page = document.new_page(width=PAGE_W, height=PAGE_H)
    _page_furniture(page, 1)
    _text(page, pymupdf.Rect(MARGIN, 96, PAGE_W - MARGIN, 160), TITLE,
          font="hebo", size=17, align=1)
    _text(page, pymupdf.Rect(MARGIN, 168, PAGE_W - MARGIN, 186), AUTHORS,
          font="helv", size=10, align=1)
    _text(page, pymupdf.Rect(MARGIN, 186, PAGE_W - MARGIN, 204), AFFILIATION,
          font="heit", size=8.5, align=1, color=MUTED)

    _text(page, pymupdf.Rect(MARGIN + 40, 226, PAGE_W - MARGIN - 40, 244), "Abstract",
          font="hebo", size=10, align=1)
    abstract = (
        "Layered composite plates were cycled between ambient and elevated temperature while "
        "the centre deflection of each plate was recorded. Three stacking sequences were "
        "compared over forty cycles. Deflection grew with cycle count and settled after ten "
        "cycles in every sequence; the symmetric stack settled at the lowest value. Residual "
        "stiffness fell by between six and fourteen per cent, with the largest fall in the "
        "asymmetric stack. The measured stiffness sits consistently below the clamped-edge "
        "prediction, which is attributed to the compliance of the fixture rather than to "
        "damage within the laminate."
    )
    _text(page, pymupdf.Rect(MARGIN + 40, 248, PAGE_W - MARGIN - 40, 360), abstract,
          size=9, align=3)
    _text(page, pymupdf.Rect(MARGIN + 40, 372, PAGE_W - MARGIN - 40, 392),
          "Keywords: thermal fatigue, laminate, deflection, residual stiffness, fixture "
          "compliance", font="heit", size=8, color=MUTED)

    _text(page, pymupdf.Rect(MARGIN, 420, PAGE_W - MARGIN, 440), "1. Introduction",
          font="hebo", size=11)
    intro = " ".join(_paragraph_text(i) for i in range(3))
    _text(page, pymupdf.Rect(MARGIN, 444, MARGIN + COLUMN_W, BODY_BOTTOM), intro, align=3)
    _text(page, pymupdf.Rect(MARGIN + COLUMN_W + GUTTER, 444, PAGE_W - MARGIN, BODY_BOTTOM),
          " ".join(_paragraph_text(i) for i in range(3, 6)), align=3)


def _body_page(document: pymupdf.Document, number: int, state: dict) -> None:
    page = document.new_page(width=PAGE_W, height=PAGE_H)
    _page_furniture(page, number)

    for column in range(2):
        x = MARGIN + column * (COLUMN_W + GUTTER)
        y = BODY_TOP
        rect_right = x + COLUMN_W

        while y < BODY_BOTTOM - 40:
            slot = state["slot"]
            state["slot"] += 1

            if slot % 9 == 4:  # a chart, with its labels and caption
                height = 118
                if y + height + 26 > BODY_BOTTOM:
                    break
                _chart(page, pymupdf.Rect(x, y, rect_right, y + height), state["figure"])
                y += height + 4
                caption = f"Figure {state['figure']}: {CAPTIONS[state['figure'] % len(CAPTIONS)]}"
                used = _text(page, pymupdf.Rect(x, y, rect_right, y + 30), caption,
                             font="heit", size=7.5, color=MUTED)
                y += 30 - max(used, 0) + 10
                state["figure"] += 1
                continue

            if slot % 9 == 7:  # a table with a header row
                if y + 80 > BODY_BOTTOM:
                    break
                caption = f"Table {state['table']}: measured values, {state['table'] * 10} cycles."
                used = _text(page, pymupdf.Rect(x, y, rect_right, y + 24), caption,
                             font="heit", size=7.5, color=MUTED)
                y += 24 - max(used, 0) + 4
                y = _table(page, x, COLUMN_W, y, state["table"])
                state["table"] += 1
                continue

            if slot % 23 == 11:  # a raster figure
                height = 96
                if y + height + 26 > BODY_BOTTOM:
                    break
                page.insert_image(pymupdf.Rect(x, y, rect_right, y + height),
                                  stream=_png((320, 200), state["image"]))
                y += height + 4
                caption = f"Figure {state['figure']}: {CAPTIONS[4]}"
                used = _text(page, pymupdf.Rect(x, y, rect_right, y + 26), caption,
                             font="heit", size=7.5, color=MUTED)
                y += 26 - max(used, 0) + 10
                state["figure"] += 1
                state["image"] += 1
                continue

            if slot % 6 == 0:  # a heading
                section, subs = SECTIONS[state["section"] % len(SECTIONS)]
                if state["sub"] == 0:
                    heading = f"{state['section'] + 2}. {section}"
                    font, size = "hebo", 11
                else:
                    heading = (
                        f"{state['section'] + 2}.{state['sub']} "
                        f"{subs[(state['sub'] - 1) % len(subs)]}"
                    )
                    font, size = "hebo", 9.5
                if y + 22 > BODY_BOTTOM:
                    break
                _text(page, pymupdf.Rect(x, y, rect_right, y + 20), heading, font=font, size=size)
                y += 20
                state["sub"] += 1
                if state["sub"] > len(subs):
                    state["sub"] = 0
                    state["section"] += 1
                continue

            text = _paragraph_text(state["paragraph"])
            state["paragraph"] += 1
            box = pymupdf.Rect(x, y, rect_right, min(y + 150, BODY_BOTTOM))
            used = _text(page, box, text, align=3)
            if used < 0:  # did not fit in what is left of the column
                break
            y += box.height - used + 8


def build(target: Path, pages: int) -> Path:
    document = pymupdf.open()
    _title_page(document)
    state = {"slot": 0, "paragraph": 6, "figure": 1, "table": 1, "image": 1, "section": 0, "sub": 0}
    for number in range(2, pages + 1):
        _body_page(document, number, state)

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(target), deflate=True)
    document.close()
    return target


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/samples/academic_paper.pdf")
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    written = build(target, pages)

    check = pymupdf.open(written)
    chars = sum(len(check[i].get_text()) for i in range(check.page_count))
    images = sum(len(check[i].get_images()) for i in range(check.page_count))
    print(
        f"{written} yazildi: {check.page_count} sayfa, {chars:,} karakter, "
        f"{images} gomulu gorsel, {written.stat().st_size // 1024} KB"
    )
    check.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
