"""Reading a table's grid: rows and columns from line positions.

Satır konumlarından tablonun satır ve sütun ızgarasını okur.
"""

from __future__ import annotations

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    Block,
)

#: How close two blocks' left edges must be, relative to the row's height, to count as the same
#: column. A table's columns line up; a paragraph's lines do not have columns to line up with.
_COLUMN_ALIGN_KEY = "table.column_align_ratio"  # tunables key; the value is read where it is used


#: Two blocks are the same kind of thing when their heights are within this factor. A cell and
#: the paragraph beside it differ by much more than that.
_HEIGHT_SIMILARITY_KEY = "table.height_similarity"  # tunables key; the value is read where it is used


#: How much of the shorter block two blocks must share vertically to be the same row.
_ROW_OVERLAP_KEY = "table.row_overlap_ratio"  # tunables key; the value is read where it is used


def _y_overlap_fraction(a: Block, b: Block) -> float:
    overlap = min(a.bbox.y1, b.bbox.y1) - max(a.bbox.y0, b.bbox.y0)
    shorter = min(a.bbox.height, b.bbox.height)
    return overlap / shorter if shorter > 0 else 0.0


def _similar_height(a: Block, b: Block) -> bool:
    taller = max(a.bbox.height, b.bbox.height)
    shorter = min(a.bbox.height, b.bbox.height)
    return shorter > 0 and taller / shorter <= tunables.get(_HEIGHT_SIMILARITY_KEY)


def _table_grid(blocks: list[Block]) -> dict[str, tuple[int, int, int]]:
    """(table_id, row, col) for every block that sits in a table grid, keyed by block id.

    A row of cells and a line of a paragraph look alike to a merger that only asks about font
    size, vertical gap and horizontal overlap. What tells them apart is repetition: cells line
    up into columns across consecutive rows, and a paragraph has no columns to line up with.

    Which table a row belongs to is found by chaining that relation transitively (row 1 lines up
    with row 2, row 2 lines up with row 3 -> rows 1-3 are one table) via union-find over row
    indices, rather than only ever comparing a row to its immediate neighbour - the middle row of
    a three-row table is what every other row matches against, and a purely pairwise scan without
    the union step would still find the table, but two tables placed close enough that their
    outer rows also pass the alignment test would merge into one.
    """
    # A row is blocks that share a band *and* a height. Without the height test the paragraph
    # in the next column joins the row - it spans several of them - and the row comes out one
    # member longer than the row below it, so the two never line up and the table is missed.
    # Only single-line blocks can be cells. A paragraph is many lines in one block, and two
    # paragraphs sitting side by side in a two-column page would otherwise look exactly like a
    # row of cells that repeats down the page.
    cells = [b for b in blocks if len(b.lines) <= 2]

    # Rows are grouped on how *much* two blocks overlap, not whether they touch at all. Two
    # tables on one page sit a few points out of step with each other, and a half-point overlap
    # was enough to chain one row to the next until a single band held 37 blocks from all over
    # the page.
    rows: list[list[Block]] = []
    for block in sorted(cells, key=lambda b: b.bbox.y0):
        for row in rows:
            if any(
                _y_overlap_fraction(block, other) >= tunables.get(_ROW_OVERLAP_KEY)
                and _similar_height(block, other)
                for other in row
            ):
                row.append(block)
                break
        else:
            rows.append([block])

    candidates = [sorted(row, key=lambda b: b.bbox.x0) for row in rows if len(row) >= 2]
    if not candidates:
        return {}

    parent = list(range(len(candidates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # Which cell ids each row actually matched - a row can have a cell that lines up with
    # nothing in any other row (a caption sharing the row's band, say), and that one cell stays
    # out of the table while its row-mates go in.
    row_matches: dict[int, set[str]] = {i: set() for i in range(len(candidates))}
    for index, row in enumerate(candidates):
        height = max(b.bbox.height for b in row) or 1.0
        for j, other in enumerate(candidates[index + 1 :], start=index + 1):
            # Matched column by column rather than row against row. A page can hold two tables
            # whose rows interleave - the left column's table starting a few points below the
            # right column's - and then no two rows have the same number of cells, which is how
            # a whole page of tables went undetected.
            matched = [
                (a, b)
                for a in row
                for b in other
                if abs(a.bbox.x0 - b.bbox.x0) <= height * tunables.get(_COLUMN_ALIGN_KEY)
                and _similar_height(a, b)
            ]
            if len(matched) >= 2:
                union(index, j)
                row_matches[index].update(a.id for a, _ in matched)
                row_matches[j].update(b.id for _, b in matched)

    components: dict[int, list[int]] = {}
    for i in range(len(candidates)):
        if row_matches[i]:
            components.setdefault(find(i), []).append(i)

    result: dict[str, tuple[int, int, int]] = {}
    for table_id, row_indices in enumerate(components.values()):
        row_indices.sort(key=lambda i: candidates[i][0].bbox.y0)
        cell_ids = {cid for i in row_indices for cid in row_matches[i]}
        table_cells = [b for i in row_indices for b in candidates[i] if b.id in cell_ids]
        height = max(b.bbox.height for b in table_cells) or 1.0

        # Columns: cluster every matched cell's x0 across the whole table into buckets, in
        # left-to-right order, so a cell's column index is consistent across every row even when
        # a row is missing a cell (a merged header, a short last row).
        columns: list[float] = []
        col_of: dict[str, int] = {}
        for cell in sorted(table_cells, key=lambda b: b.bbox.x0):
            for col_index, x0 in enumerate(columns):
                if abs(cell.bbox.x0 - x0) <= height * tunables.get(_COLUMN_ALIGN_KEY):
                    col_of[cell.id] = col_index
                    break
            else:
                col_of[cell.id] = len(columns)
                columns.append(cell.bbox.x0)

        for row_position, i in enumerate(row_indices):
            for cell in candidates[i]:
                if cell.id in cell_ids:
                    result[cell.id] = (table_id, row_position, col_of[cell.id])

    return result
