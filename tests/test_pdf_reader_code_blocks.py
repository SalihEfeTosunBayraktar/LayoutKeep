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
