"""Code set in a monospaced face is code, and is not sent for translation.

Campaign, Think Python: blocks of Python ("def different_words(hist): return len(hist)",
">>> os.path.exists('memo.txt')", a traceback) were sent to the model as prose. Most came back
unchanged, but some came back with their strings translated - "print('Toplam kelime sayisi:',
...)" - which changes the program the book prints. A born-digital PDF says which runs are set in a
monospaced face (PyMuPDF span flag 8; Think Python's code font SFTT1000 carries it on every span,
its body text on none). A block entirely in such a face is code.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from layoutkeep.core.docir import BlockRole
from layoutkeep.readers.pdf_reader import read_pdf


def test_a_block_set_in_courier_is_code_and_not_translatable(tmp_path: Path) -> None:
    src = tmp_path / "code.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 60), "Here is a function that counts the words in a list:", fontname="helv", fontsize=11)
    page.insert_text((40, 120), "def different_words(hist):", fontname="cour", fontsize=10)
    page.insert_text((40, 133), "    return len(hist)", fontname="cour", fontsize=10)
    doc.save(str(src))

    blocks = [b for _p, b in read_pdf(src).iter_blocks()]
    code = [b for b in blocks if "different_words" in b.text]
    prose = [b for b in blocks if "counts the words" in b.text]
    assert code and code[0].role == BlockRole.CODE and not code[0].translatable, [(b.role, b.text) for b in blocks]
    assert prose and prose[0].translatable


def test_a_verbatim_line_in_an_ordinary_face_is_code() -> None:
    """Held-out arXiv 2609.19145: LaTeX's verbatim fragments are not set in a monospaced face, so
    nothing caught them, and the audit counted them as text left untranslated (L2) - seven blocks,
    each of which the retry ladder could only ever be answered with."""
    from layoutkeep.readers._nonprose import is_code_like

    assert is_code_like("trim_offsets=True, use_regex=True)")
    assert is_code_like("trim_offsets=False, use_regex=True)")
    assert is_code_like('print("Toplam kelime sayisi:", total)')
    assert is_code_like("words = compute_frequencies(hist)")


def test_prose_with_parentheses_and_a_sentence_end_is_not_code() -> None:
    """A missed line costs one wasted retry; a false positive leaves a reader's paragraph in the
    source language, which is the failure this project spends its effort avoiding."""
    from layoutkeep.readers._nonprose import is_code_like

    assert not is_code_like("Form 1099-B (or 1099-DA) goes to the same address.")
    assert not is_code_like("Tighten the bolts (3) and the tie rod (1) before starting.")
    assert not is_code_like(
        "(ii) the new token s1 \u25c6s2 changes from frequency 0 to nD s1,s2. Further, the total"
    )
    assert not is_code_like("All four tokenisers use the same preprocessing pipeline.")
    assert not is_code_like("")


def test_a_code_line_is_read_as_code_and_a_sentence_beside_it_is_not(tmp_path: Path) -> None:
    src = tmp_path / "verbatim.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 60), "Here is how the tokens are normalised:", fontname="helv", fontsize=11)
    page.insert_text((40, 100), "trim_offsets=True, use_regex=True)", fontname="helv", fontsize=10)
    doc.save(str(src))

    blocks = [b for _p, b in read_pdf(src).iter_blocks()]
    code = [b for b in blocks if "trim_offsets" in b.text]
    prose = [b for b in blocks if "tokens are normalised" in b.text]
    assert code and code[0].role == BlockRole.CODE and not code[0].translatable, [
        (b.role, b.text) for b in blocks
    ]
    assert prose and prose[0].translatable
