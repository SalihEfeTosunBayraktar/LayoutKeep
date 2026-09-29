"""Unit tests for academic reference and bibliography preservation.

Akademik kaynakça ve atıf koruma mantığını doğrulayan birim testleri.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Document, Line, Page, Span, Style
from layoutkeep.core.reference import (
    is_bibliography_heading,
    is_citation_entry,
    tag_bibliography_blocks,
)
from layoutkeep.verify import is_checked


def _make_block(text: str, role: BlockRole = BlockRole.BODY, block_id: str = "b1") -> Block:
    # Test için yardımcı blok oluşturucu / Helper block factory for tests
    box = BBox(10.0, 10.0, 200.0, 30.0)
    return Block(
        id=block_id,
        role=role,
        bbox=box,
        lines=[Line(bbox=box, spans=[Span(text=text, bbox=box, style=Style())])],
    )


def test_is_bibliography_heading():
    # Kaynakça başlıklarının doğru tespit edildiğini doğrular / Verifies bibliography headers
    assert is_bibliography_heading("References")
    assert is_bibliography_heading("12. Bibliography")
    assert is_bibliography_heading("KAYNAKÇA:")
    assert is_bibliography_heading("Works Cited.")
    assert not is_bibliography_heading("Introduction")
    assert not is_bibliography_heading("System Architecture")


def test_is_citation_entry():
    # Atıf ve referans maddelerinin tespitini doğrular / Verifies citation entry detection
    # Bracketed citation / Köşeli parantezli atıf
    assert is_citation_entry("[1] J. Smith, Deep Learning, Nature vol. 12, pp. 30-45, 2020.")
    # DOI içeren akademik atıf / Academic citation with DOI
    assert is_citation_entry("Vaswani et al., Attention is all you need, doi: 10.1145/3000, 2017.")
    # Sıradan gövde metni atıf sayılmamalı / Ordinary prose is not a citation
    assert not is_citation_entry("This is an ordinary sentence describing the experimental setup.")


def test_tag_bibliography_blocks_in_document():
    # Doküman içindeki kaynakça bloklarının etiketlenmesi / Verifies tagging inside Document
    header = _make_block("References", role=BlockRole.HEADING, block_id="b0")
    ref1 = _make_block("[1] Turing, A. M. (1950). Computing Machinery. Mind.", block_id="b1")
    ref2 = _make_block("[2] Shannon, C. E. (1948). A Mathematical Theory.", block_id="b2")
    doc = Document(pages=[Page(number=1, width=595.0, height=842.0, blocks=[header, ref1, ref2])])

    tagged = tag_bibliography_blocks(doc, preserve=True)
    assert tagged == 2
    assert ref1.role == BlockRole.BIBLIOGRAPHY
    assert ref2.role == BlockRole.BIBLIOGRAPHY
    assert not ref1.translatable
    assert not ref2.translatable


def test_verify_is_checked_ignores_bibliography_blocks():
    # Doğrulama motorunun kaynakça bloklarını cezalandırmadığını doğrular / Verifies verify ignores bibliography
    ref_block = _make_block("[1] Einstein, A. (1905). Zur Elektrodynamik.", role=BlockRole.BIBLIOGRAPHY)
    assert not is_checked(ref_block)
