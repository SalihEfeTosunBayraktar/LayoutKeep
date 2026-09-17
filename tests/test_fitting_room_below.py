"""A block's text may not be drawn into the block beneath it.

Campaign, The Time Machine: on 46 of 120 pages words were drawn over other words - the last line of
a paragraph over the first line of the next. The writer lays text out in the block's box plus a
slack below (for its own inset), and paragraphs set close together have no room below at all: one
box ended at 194.8 pt, the next began at 194.1 pt. The slack below is only what the page has free.

The box itself is not shortened: the writer clears the source text by that box, and a shorter box
would leave the bottom of the last source line on the page.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Span, Style
from layoutkeep.fitting.room import room_below


def _block(y0: float, y1: float, x0: float = 72.0, x1: float = 540.0) -> Block:
    box = BBox(x0, y0, x1, y1)
    span = Span(text="text", bbox=box, style=Style(size=10.0))
    return Block(id=f"{x0}-{y0}", role=BlockRole.BODY, bbox=box, lines=[Line(spans=[span], bbox=box)])


def test_no_room_below_a_box_touching_the_next_paragraph() -> None:
    upper, lower = _block(50.1, 194.8), _block(194.1, 230.8)
    assert abs(room_below(upper, [upper, lower], slack=3.0) - (-0.7)) < 1e-6


def test_negative_room_when_the_next_block_starts_inside_this_one() -> None:
    """Popular Science: the model's regions overlap partly (5-10 pt) and so did their blocks, which
    were drawn over each other. The room is then negative - the drawing stops where the next block
    starts - while the box the source is cleared by stays whole."""
    upper, lower = _block(151.0, 235.0, 45, 99), _block(224.0, 307.0, 46, 219)
    assert room_below(upper, [upper, lower], slack=3.0) == -11.0


def test_part_of_the_slack_where_the_gap_is_smaller() -> None:
    upper, lower = _block(50.0, 100.0), _block(101.5, 140.0)
    assert room_below(upper, [upper, lower], slack=3.0) == 1.5


def test_the_whole_slack_with_free_space_below() -> None:
    upper, lower = _block(50.0, 100.0), _block(140.0, 180.0)
    assert room_below(upper, [upper, lower], slack=3.0) == 3.0


def test_a_block_in_another_column_is_not_a_neighbour() -> None:
    left, right = _block(50.0, 194.8, 72, 290), _block(194.1, 230.8, 320, 540)
    assert room_below(left, [left, right], slack=3.0) == 3.0


def test_translated_paragraphs_set_close_together_are_not_drawn_over_each_other(tmp_path) -> None:
    import pymupdf

    from layoutkeep.core.docir import apply_segments, segments_from_document
    from layoutkeep.readers.pdf_reader import read_pdf
    from layoutkeep.writers.pdf_writer import write_pdf

    src = tmp_path / "close.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=322, height=483)
    upper = pymupdf.Rect(44, 60, 278, 130)
    lower = pymupdf.Rect(44, 130, 278, 200)
    page.insert_textbox(upper, "the Time Traveller. And therewith, taking the lamp in his hand, he led the way "
                        "down the long, draughty corridor to his laboratory, and there we beheld it.", fontsize=10)
    page.insert_textbox(lower, "Look here, said the Medical Man, are you perfectly serious? Or is this a trick "
                        "like that ghost you showed us last Christmas? None of us knew how to take it.", fontsize=10)
    doc.save(str(src))

    read = read_pdf(src)
    blocks = [b for _p, b in read.iter_blocks()]
    assert len(blocks) == 2, [b.text for b in blocks]
    # As on the real page: the upper box ends where the lower one begins.
    blocks[0].bbox.y1 = blocks[1].bbox.y0 + 0.7
    segments = segments_from_document(read)
    for seg in segments:
        seg.target = ("Zaman Yolcusu. Ve boylece, elindeki lambayla, onu laboratuvarina kadar uzanan uzun, "
                      "ruzgarli koridora dogru goturdu ve orada onu gorduk, cok sasirdik ve bekledik.")
    apply_segments(read, segments)
    out = tmp_path / "out.pdf"
    write_pdf(read, src, out)

    with pymupdf.open(out) as result:
        words = [(pymupdf.Rect(w[:4]), (w[5], w[6])) for w in result[0].get_text("words") if len(w[4]) > 1]
    over = sum(
        1 for i, (a, la) in enumerate(words) for b, lb in words[i + 1:]
        if la != lb and not (a & b).is_empty and (a & b).get_area() / min(a.get_area(), b.get_area()) > 0.3
    )
    assert over == 0, f"{over} word pairs drawn over each other"
