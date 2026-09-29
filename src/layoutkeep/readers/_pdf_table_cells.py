"""Table cells and label roles inside the layout model's table regions.

Düzen modelinin tablo bölgelerindeki hücreleri ve etiket rollerini çıkarır.
"""

from __future__ import annotations

import pymupdf

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    BlockRole,
    Line,
)
from layoutkeep.readers._nonprose import is_prose_label

#: Lines of one table cell sit this close: within a line spacing of each other, left edges aligned.
_CELL_GAP = 0.6


def _horizontal_rules(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """The page's horizontal rules: what separates one table row from the next."""
    return [d["rect"] for d in page.get_drawings() if d["rect"].height <= 1.5 and d["rect"].width >= 5]


def _label_role(role: BlockRole, group: list[Line]) -> BlockRole:
    """A figure's line becomes a translated label when the setting is on and it reads as words.

    Off by default (translation.figure_text): diagram labels are mostly names and signals, and
    translating them broke diagrams before (Think Python p. 97). Names, code and pin runs stay
    part of the picture even when it is on (`_nonprose.is_prose_label`).
    """
    if role is not BlockRole.FIGURE or not tunables.get("translation.figure_text"):
        return role
    text = " ".join(span.text for line in group for span in line.spans)
    return BlockRole.FIGURE_LABEL if is_prose_label(text) else role


def _table_cells(lines: list[Line], rules: list[pymupdf.Rect], line_height: float) -> list[list[Line]]:
    """A table's lines grouped into cells: one block per cell, not one per line.

    Arm E, tr_shk_2828: a cell wrapped over "Mülki / İdare / Amirliği" came out as three blocks,
    each word translated alone ("aybaşında" -> "at the full moon") and too long for its one-line
    box. Lines join a cell when they are stacked in its column (left edges within a line height, or
    overlapping by half the narrower line for a centred cell),
    a line spacing apart at most, and no rule runs between them - a rule or a wider gap is a row.
    """
    groups: list[list[Line]] = []
    blank: list[list[Line]] = []
    for line in lines:  # sorted top to bottom
        if not "".join(span.text for span in line.spans).strip():
            blank.append([line])  # a blank line joins no cell and separates none
            continue
        box = line.bbox
        home = None
        for group in reversed(groups):
            last = group[-1].bbox
            if box.y0 < last.y1 - 0.5 * line_height:
                # On the same row: a piece of a justified line inside the cell's width belongs to
                # it ("... tabi personel kadroları Mülki İdare" came as four pieces); one beside it
                # is the next column.
                left = min(line.bbox.x0 for line in group)
                right = max(line.bbox.x1 for line in group)
                if left - 1 <= box.x0 and box.x1 <= right + 1:
                    home = group
                    break
                continue
            overlap = min(last.x1, box.x1) - max(last.x0, box.x0)
            narrower = min(last.x1 - last.x0, box.x1 - box.x0)
            aligned = abs(last.x0 - box.x0) <= line_height or overlap >= 0.5 * narrower
            if not aligned or box.y0 - last.y1 > _CELL_GAP * line_height:
                continue
            ruled = any(
                last.y1 - 1 <= rule.y0 <= box.y0 + 1 and rule.x0 < box.x1 and rule.x1 > box.x0
                for rule in rules
            )
            if not ruled:
                home = group
            break
        if home is None:
            groups.append([line])
        else:
            home.append(line)
    return groups + blank
