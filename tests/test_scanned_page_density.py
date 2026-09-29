"""Whether a page needs OCR is a question about text DENSITY, not a character count.

`is_scanned_page` compared the page's extracted text against an absolute threshold of ten
characters. That assumes something about page size and about what a text layer contains, and
both assumptions broke on the second document tried:

`Notes_260730_153127.pdf` is 22 A4 pages, each an image with a thirteen-character template stamp
in the text layer - "my notes / date". Thirteen is not under ten, so every page was read as
though it had a text layer, OCR never ran, and the whole of each page's content was silently
ignored: the reader returned 96 characters for the entire document. OCR reads 362 characters off
page 2 alone.

Density separates the cases by a factor of 370, and it scales with the page rather than assuming
a size:

    book, 318x424pt, no text layer            0.00 chars / 1000pt2
    notes, A4, template stamp only            0.03
    a real text layer (our own output)       11.16 - 21.38

So the threshold sits between them with three orders of magnitude to spare, where the old one sat
three characters away from a stamp.
"""

from __future__ import annotations

from layoutkeep.readers.image_reader import is_scanned_page

#: The two page sizes in play: the textbook's small trim, and A4.
BOOK_AREA = 318.0 * 424.0
A4_AREA = 596.0 * 842.0


def test_a_page_with_no_text_layer_needs_ocr() -> None:
    assert is_scanned_page("", BOOK_AREA) is True


def test_a_template_stamp_does_not_count_as_a_text_layer() -> None:
    """The case that was missed: 13 characters on A4, and a page full of image under them."""
    assert is_scanned_page("my notes\ndate", A4_AREA) is True


def test_a_real_text_layer_is_left_alone() -> None:
    """OCR'ing a page that already has its text would duplicate every line of it."""
    assert is_scanned_page("A" * 2883, BOOK_AREA) is False


def test_the_same_text_means_different_things_on_different_page_sizes() -> None:
    """The property an absolute count cannot express.

    Two hundred characters is a caption lost on A4 and two full lines on this book's small
    trim - 0.40 against 1.48 characters per 1000pt2 - so the same text has to be read
    differently depending on how much page is around it.
    """
    same_text = "word " * 40
    assert is_scanned_page(same_text, A4_AREA) is True
    assert is_scanned_page(same_text, BOOK_AREA) is False


def test_a_zero_area_page_is_not_guessed_at() -> None:
    """A malformed page reports no area; treating that as infinite density would skip OCR on
    every page of the document."""
    assert is_scanned_page("", 0.0) is True
    assert is_scanned_page("A" * 500, 0.0) is False
