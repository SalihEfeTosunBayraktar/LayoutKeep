"""Elastic micro-flow layout: shifts subsequent blocks downward when a block expands.

Dinamik mikro-akış mizanpajı: çevrilen bir blok genişlediğinde altındaki blokları dikeyde
öteleyerek yazı boyutunun aşırı küçülmesini engeller.
"""

from __future__ import annotations

from collections.abc import Callable

from layoutkeep.core.docir import BBox, Block, Style

#: Default bottom margin guard / Varsayılan sayfa alt boşluk güvenlik sınırı
DEFAULT_BOTTOM_MARGIN_PT = 40.0

#: Horizontal column tolerance in points / Aynı sütunda sayılmak için yatay tolerans
COLUMN_X_TOLERANCE_PT = 20.0


def _is_in_same_column_bbox(b1: BBox, b2: BBox, tolerance: float = COLUMN_X_TOLERANCE_PT) -> bool:
    # İki kutunun aynı sütun hizasında olup olmadığını doğrular / Checks if two bboxes share column alignment
    overlap_x = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
    narrower = min(b1.width, b2.width)
    if narrower <= 0:
        return False
    return (overlap_x / narrower) >= 0.4 or abs(b1.x0 - b2.x0) <= tolerance


def compute_required_expansion(
    text: str,
    style: Style,
    bbox: BBox,
    measure_fn: Callable[..., tuple[bool, float]],
    *,
    min_scale: float = 0.85,
    max_expansion_ratio: float = 2.0,
    step_pt: float = 12.0,
) -> float:
    # Metnin sığması için gereken dikey ek yüksekliği hesaplar / Computes additional height needed for text to fit
    orig_h = bbox.height
    max_h = orig_h * max_expansion_ratio
    current_h = orig_h

    while current_h < max_h:
        test_bbox = BBox(bbox.x0, bbox.y0, bbox.x1, bbox.y0 + current_h)
        fits, _ = measure_fn(text, style, test_bbox, scale_low=min_scale)
        if fits:
            return round(current_h - orig_h, 2)
        current_h += step_pt

    return round(max_h - orig_h, 2)


class ElasticFlowEngine:
    """Calculates vertical offsets for blocks when preceding text expands.

    Önceki metin blokları genişlediğinde altındaki bloklar için dikey öteleme hesaplar.
    """

    def __init__(self, bottom_margin: float = DEFAULT_BOTTOM_MARGIN_PT) -> None:
        self._bottom_margin = bottom_margin

    def reflow_column(
        self,
        blocks: list[Block],
        expansions: dict[str, float],
        page_height: float,
    ) -> list[Block]:
        # Genişleyen bloklara göre sayfa mizanpajını aşağı doğru öteler / Pushes subsequent blocks downward
        if not expansions:
            return blocks

        sorted_blocks = sorted(blocks, key=lambda b: (b.order, b.bbox.y0))
        shifted_blocks: list[Block] = []
        active_shifts: list[tuple[BBox, float]] = []

        for b in sorted_blocks:
            orig_bbox = b.bbox
            current_shift = self._calculate_shift_for_block(orig_bbox, active_shifts)
            extra_h = expansions.get(b.id, 0.0)

            # Bloğun yeni koordinatlarını hesapla / Computes new bounding box
            new_y0 = orig_bbox.y0 + current_shift
            new_y1 = orig_bbox.y1 + current_shift + extra_h

            # Sayfa tabanını aşmaması için sınırla / Clamps to bottom margin
            max_allowed_y1 = page_height - self._bottom_margin
            if new_y1 > max_allowed_y1:
                b.needs_review = True
                b.review_reason = "Sayfa alt sınırını aştı / Exceeded bottom margin limit"

            b.bbox = BBox(orig_bbox.x0, round(new_y0, 2), orig_bbox.x1, round(new_y1, 2))
            shifted_blocks.append(b)

            if extra_h > 0:
                active_shifts.append((orig_bbox, extra_h))

        return shifted_blocks

    def _calculate_shift_for_block(
        self, orig_bbox: BBox, active_shifts: list[tuple[BBox, float]]
    ) -> float:
        # Bir bloğa etki eden kümülatif öteleme miktarını hesaplar / Calculates cumulative shift affecting block
        total_shift = 0.0
        for prior_orig_bbox, shift_amount in active_shifts:
            if prior_orig_bbox.y0 < orig_bbox.y0 and _is_in_same_column_bbox(prior_orig_bbox, orig_bbox):
                total_shift += shift_amount
        return total_shift
