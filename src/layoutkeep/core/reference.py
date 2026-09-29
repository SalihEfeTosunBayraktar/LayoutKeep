"""Academic bibliography and reference section preservation.

Akademik ve teknik belgelerde kaynakça ve referans bölümlerini tespit ederek
çeviri sırasında yazar adlarının, eser başlıklarının ve DOI/tarih bilgilerinin
bozulmasını engelleyen koruma modülü.
"""

from __future__ import annotations

import re

from layoutkeep.core.docir import Block, BlockRole, Document

#: Patterns indicating a bibliography or reference section header.
#: Kaynakça başlığı kalıpları (TR, EN, DE, FR).
BIBLIOGRAPHY_HEADERS = frozenset({
    "references",
    "reference",
    "bibliography",
    "literature cited",
    "works cited",
    "kaynakça",
    "kaynaklar",
    "referanslar",
    "literatur",
    "quellen",
})

#: Regex detecting citation item beginnings: [1], [Smith20], 1., (1999)
#: Alıntı ve referans maddesi başlangıç kalıpları.
_CITE_START_RE = re.compile(
    r"^(?:\[\d+(?:[–,\-]\s*\d+)*\]|\[[A-Za-z]+(?:\s*(?:et\s+al\.?|\d{2,4}))?\]|\d+\.\s+|(?:\([12]\d{3}[a-z]?\)))"
)

#: Regex detecting academic citation features: DOI, arXiv, vol/no, pp.
#: Akademik yayın belirteçleri.
_ACADEMIC_FEATURE_RE = re.compile(
    r"(?:\bdoi:\s*10\.\d{4,9}|\barXiv:\d{4}\.\d{4,5}|\bvol\.\s*\d+|\bpp\.\s*\d+[-–]\d+|\b(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)


def is_bibliography_heading(text: str) -> bool:
    # Metnin kaynakça başlığı olup olmadığını denetler / Checks if text is a bibliography heading
    normalized = text.strip().lower()
    cleaned = re.sub(r"^[0-9.\s]+", "", normalized).rstrip(":.")
    return cleaned in BIBLIOGRAPHY_HEADERS


def is_citation_entry(text: str) -> bool:
    # Bloğun bir kaynakça maddesi olup olmadığını denetler / Checks if block is a citation entry
    stripped = text.strip()
    if not stripped or len(stripped) < 15:
        return False
    # Başlangıçta [1], [Author20] gibi bir etiket var mı / Starts with citation bracket or number
    if _CITE_START_RE.match(stripped):
        return True
    # Metin içinde DOI, arXiv veya sayfa aralığı gibi belirteçler var mı / Contains DOI/arXiv/page tokens
    features = len(_ACADEMIC_FEATURE_RE.findall(stripped))
    return features >= 2


class ReferenceProtector:
    """Detects and protects reference and bibliography sections in documents.

    Belgelerdeki kaynakça ve referans bölümlerini tespit edip koruma altına alır.
    """

    def __init__(self, preserve: bool = True) -> None:
        self.preserve = preserve

    def tag_document(self, doc: Document) -> int:
        # Dokümandaki kaynakça bloklarını işaretler / Tags bibliography blocks in document
        tagged_count = 0
        in_references_section = False

        for page in doc.pages:
            # Blokları mantıksal sıraya göre gez / Iterate blocks in logical order
            sorted_blocks = sorted(page.blocks, key=lambda b: (b.order, b.bbox.y0))
            for block in sorted_blocks:
                source_text = block.source_text or block.text
                if not source_text:
                    continue

                if is_bibliography_heading(source_text):
                    in_references_section = True
                    block.role = BlockRole.BIBLIOGRAPHY
                    continue

                # Başka bir ana bölüm başlığı geldiğinde kaynakça bölümünü kapat / Close section on new heading
                if in_references_section and block.role in (BlockRole.TITLE, BlockRole.HEADING) and not is_bibliography_heading(source_text):
                    in_references_section = False

                if in_references_section or is_citation_entry(source_text):
                    self._tag_block(block)
                    tagged_count += 1

        return tagged_count

    def _tag_block(self, block: Block) -> None:
        # Tekil bloğu kaynakça olarak işaretler ve gerekirse korur / Tags single block as bibliography
        if self.preserve:
            block.role = BlockRole.BIBLIOGRAPHY


def tag_bibliography_blocks(doc: Document, *, preserve: bool = True) -> int:
    # Kolaylık fonksiyonu / Convenience helper to tag bibliography blocks
    protector = ReferenceProtector(preserve=preserve)
    return protector.tag_document(doc)
