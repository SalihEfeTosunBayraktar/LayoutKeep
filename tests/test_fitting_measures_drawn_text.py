"""The fit measures the text the page carries, not the provider's marker syntax.

A translation comes back with the inline markers the provider was handed: `Etiketli <0>terim</0>
dar bir sütunda durur`. They are not glyphs. `_span_html` builds the html from the block's *spans*
and `_replace_block_text` consumes the markers into them - that is the string the page gets. The
fit measured `Segment.target` as it stood, so every marker was counted as text: on the 17-source
bench (commit d9f2129) 123 of the 226 flagged blocks carried markers, 1659 characters of syntax
between them, up to 133 on one paragraph. Measured over the recorded runs (tools/audit/fit_probe
plus the drawn-form probe): 215 blocks still do not fit when the markers are counted, 196 when the
text is measured as drawn - and of the 19 that flip, the ones with a marked run set smaller than
their block (`<1>2</1>` at 5.9pt in an 11.8pt paragraph) are the plainest: eight characters of
syntax at the block's size for one glyph at a third of it.
"""

from __future__ import annotations

import copy
import re

import pytest

from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Segment,
    Span,
    Style,
    apply_segments,
    drawn_runs,
)
from layoutkeep.fitting.pdf_pass import fit_pdf_pass
from layoutkeep.writers.pdf_writer import measure_fit

_SOURCE = "The tagged term sits in a narrow column"
_MARKED = "Etiketli <0>terim</0> dar bir sütunda durur"


def _styles() -> tuple[Style, Style]:
    return (
        Style(font_family="URWPalladioL-Roma", size=10.0, serif=True),
        # The marked run the way a source draws a term of its own: 7pt inside a 10pt paragraph.
        Style(font_family="URWPalladioL-Roma", size=7.0, serif=True),
    )


def _doc(marked_run: bool = True, *, width: float = 160.0) -> tuple[Document, Block]:
    """One line box with the next block 2pt under it: the granted room below is nil.

    The block carries the *source* run split, as a real reader leaves it: the marked run's own
    style only becomes marker 0 because its run holds text (an empty run is not a style - see
    `_inline_styles`).
    """
    dominant, smaller = _styles()
    box = BBox(72, 200, 72 + width, 214)
    spans = [Span(text=_SOURCE, bbox=box, style=dominant)]
    if marked_run:
        spans = [
            Span(text="The tagged ", bbox=box, style=dominant),
            Span(text="term", bbox=box, style=smaller),
            Span(text=" sits in a narrow column", bbox=box, style=dominant),
        ]
    block = Block(
        id="b1", role=BlockRole.BODY, bbox=box,
        lines=[Line(spans=spans, bbox=box)], order=0, source_text=_SOURCE,
    )
    below_box = BBox(72, 216, 372, 226)
    below = Block(
        id="b2", role=BlockRole.BODY, bbox=below_box,
        lines=[Line(spans=[Span(text="x = y + z", bbox=below_box, style=dominant)], bbox=below_box)],
        order=1, source_text="x = y + z",
    )
    doc = Document(target_lang="tr", pages=[Page(number=1, width=612, height=792, blocks=[block, below])])
    return doc, block


def _fit(doc: Document, target: str = _MARKED, seen: list | None = None):
    segment = Segment(block_id="b1", source=_SOURCE, target=target)
    return fit_pdf_pass(
        doc,
        [segment],
        retranslate=lambda seg, budget: seg.target,
        target_lang="tr",
        on_fitted=(lambda _s, _b, r: seen.append(r)) if seen is not None else None,
    )


def test_the_fit_measures_what_the_page_gets_not_the_providers_markers():
    """A one-line box, a translation that needs one line once its markers are markup.

    Measured at 160pt wide (Noto Serif, 10pt, the marked run at 7pt): the marked spelling needs
    more than the box at the 0.85 floor and was flagged "did not fit, shrinking was not enough",
    while the drawn spelling fits at 0.93. Same box, same text - only the syntax counted twice.
    """
    doc, _block = _doc()
    seen: list = []
    _fit(doc, seen=seen)

    assert seen, "the segment must reach the engine"
    assert seen[0].text == _MARKED, "the write-back keeps the markup for the writer"
    assert not seen[0].needs_review, (
        f"the drawn text fits this box: layer={seen[0].layer} scale={seen[0].scale}"
    )


def test_the_measured_string_keeps_the_run_markup_and_drops_the_marker_syntax(monkeypatch):
    """Dropping the markers is not enough: the marked run is drawn at its own size, so a
    measurement that forgot it would leave the writer to shrink the block a second time."""
    measured: list[tuple[str, bool]] = []

    def fake(text, style, bbox, *, scale_low=0.85, rotation=0.0, markup=False):
        measured.append((text, markup))
        return True, 1.0

    monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", fake)
    doc, _block = _doc()
    _fit(doc)

    assert measured, "measure_fit must have been called"
    text, markup = measured[0]
    assert markup is True
    assert "<0>" not in text and "</0>" not in text, text
    assert '<span style="font-size:7.00pt">terim</span>' in text, text


def test_a_marker_the_writer_will_strip_is_not_measured_either(monkeypatch):
    """A block with no styled runs was never given markers, so any that come back are the model's
    invention - `_replace_block_text` strips them (K2) instead of leaking them into the page."""
    measured: list[str] = []

    def fake(text, style, bbox, *, scale_low=0.85, rotation=0.0, markup=False):
        measured.append(text)
        return True, 1.0

    monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", fake)
    doc, _block = _doc(marked_run=False)
    _fit(doc, target="Etiketli <0>terim</0> dar bir sütunda durur")

    assert measured and "<0>" not in measured[0], measured
    assert "Etiketli terim dar bir sütunda durur" in measured[0], measured


def test_a_rotated_block_is_measured_without_marker_syntax(monkeypatch):
    """Rotated blocks are drawn by the `TextWriter` path, which takes the runs straight - no html
    there, so the measurement keeps the plain text rather than markup."""
    measured: list[tuple[str, bool]] = []

    def fake(text, style, bbox, *, scale_low=0.85, rotation=0.0, markup=False):
        measured.append((text, markup))
        return True, 1.0

    monkeypatch.setattr("layoutkeep.writers.pdf_writer.measure_fit", fake)
    doc, block = _doc()
    block.rotation = 90.0
    _fit(doc)

    assert measured, "measure_fit must have been called"
    text, markup = measured[0]
    assert markup is False
    assert "<" not in text and ">" not in text, text
    assert "<0>" not in text, text


@pytest.mark.parametrize(
    "text",
    [
        _MARKED,
        "Etiketli <0>terim</0> ve <1>başka</1> bir şey",
        "Marker'sız düz metin",
        # Unusable markers: no closing tag, an index that does not exist. The writer strips them.
        "Etiketli <0>terim dar bir sütunda durur",
        "Etiketli <7>terim</7> dar bir sütunda durur",
    ],
)
def test_the_runs_the_fit_measures_are_the_runs_the_writer_draws(text: str) -> None:
    """`drawn_runs` is a promise about `_replace_block_text`: same split, same styles, same
    stripping. If the two drift, the fit is measuring a page that is not the one drawn - which is
    how a block ends up shrunk twice."""
    _doc_unused, block = _doc()
    drawn = drawn_runs(block, text)

    written = copy.deepcopy(block)
    apply_segments(
        Document(target_lang="tr", pages=[Page(number=1, width=612, height=792, blocks=[written])]),
        [Segment(block_id="b1", source=_SOURCE, target=text)],
    )
    on_page = [span for line in written.lines for span in line.spans]

    assert [(s.text, s.style.key()) for s in drawn] == [(s.text, s.style.key()) for s in on_page]
    assert "".join(s.text for s in drawn) == re.sub(r"</?\d+>", "", text)


#: NIST JR block img0#44: 8.95pt in its own 13.2pt box, the case that caught the wrapper.
_PLAIN_TEXT = "Başkan Baldrige Kazananlarını Onurlandırıyor"
_PLAIN_STYLE = Style(font_family="NimbusRomNo9L-Medi", size=8.9505, serif=True)
_PLAIN_BOX = BBox(71.3, 577.2, 231.0, 590.4)


def test_a_text_with_nothing_to_escape_is_measured_the_same_either_way():
    """`markup=True` only skips the escaping: the paragraph the renderer is given has to be otherwise
    the same, and a text with no `<`, `&` or control character measures identically.

    The `<p>` wrapper is what makes that true, and it is not decoration: without it the renderer
    never applies `p { font-size: ... }` and lays the text out at its own default size. Measured on
    the bench before this was caught - NIST JR img0#44, 8.95pt in its own 13.2pt box - the wrapper
    fits at 0.878 and the bare form does not fit at all, which flagged two extra blocks on that run
    and only that run.
    """
    plain = measure_fit(_PLAIN_TEXT, _PLAIN_STYLE, _PLAIN_BOX, scale_low=0.85)
    as_markup = measure_fit(_PLAIN_TEXT, _PLAIN_STYLE, _PLAIN_BOX, scale_low=0.85, markup=True)

    assert plain == as_markup
    assert plain[0] is True
    assert plain[1] == pytest.approx(0.878, abs=0.005)
