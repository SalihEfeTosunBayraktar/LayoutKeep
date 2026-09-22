"""Unit tests for elastic micro-flow reflow engine.

Elastik mikro-akış dikey öteleme motorunu doğrulayan birim testleri.
"""

from __future__ import annotations

from layoutkeep.core.docir import BBox, Block, BlockRole, Line, Span, Style
from layoutkeep.fitting.elastic_flow import ElasticFlowEngine


def _make_test_block(block_id: str, x0: float, y0: float, x1: float, y1: float, order: int = 0) -> Block:
    # Test için yardımcı blok üretici / Helper test block factory
    box = BBox(x0, y0, x1, y1)
    return Block(
        id=block_id,
        role=BlockRole.BODY,
        bbox=box,
        order=order,
        lines=[Line(bbox=box, spans=[Span(text=f"Text {block_id}", bbox=box, style=Style())])],
    )


def test_single_column_vertical_shift():
    # Tek sütunda bir blok genişlediğinde alttaki bloğun ötelendiğini doğrular / Verifies downward shift in single column
    b1 = _make_test_block("b1", 50.0, 50.0, 250.0, 100.0, order=1)
    b2 = _make_test_block("b2", 50.0, 110.0, 250.0, 160.0, order=2)
    engine = ElasticFlowEngine(bottom_margin=40.0)

    # b1 bloğu 30 pt genişlesin / b1 expands by 30 pt
    expansions = {"b1": 30.0}
    shifted = engine.reflow_column([b1, b2], expansions, page_height=800.0)

    # b1: y0 aynı kalır, y1 30 pt uzar (100 -> 130) / b1 height increases
    assert shifted[0].bbox.y0 == 50.0
    assert shifted[0].bbox.y1 == 130.0

    # b2: 30 pt aşağı ötelenir (110 -> 140, 160 -> 190) / b2 shifted down by 30 pt
    assert shifted[1].bbox.y0 == 140.0
    assert shifted[1].bbox.y1 == 190.0


def test_multi_column_isolation():
    # Sol sütundaki genişlemenin sağ sütunu etkilemediğini doğrular / Verifies multi-column independence
    col1_top = _make_test_block("c1_top", 50.0, 50.0, 250.0, 100.0, order=1)
    col1_bot = _make_test_block("c1_bot", 50.0, 110.0, 250.0, 160.0, order=2)

    col2_top = _make_test_block("c2_top", 300.0, 50.0, 500.0, 100.0, order=3)
    col2_bot = _make_test_block("c2_bot", 300.0, 110.0, 500.0, 160.0, order=4)

    engine = ElasticFlowEngine(bottom_margin=40.0)
    expansions = {"c1_top": 40.0}
    shifted = engine.reflow_column([col1_top, col1_bot, col2_top, col2_bot], expansions, page_height=800.0)

    by_id = {b.id: b for b in shifted}
    # Sol sütun alt bloğu 40 pt kaymalı / Col1 bottom must shift
    assert by_id["c1_bot"].bbox.y0 == 150.0
    # Sağ sütun blokları hiç kaymamalı / Col2 blocks must remain unchanged
    assert by_id["c2_top"].bbox.y0 == 50.0
    assert by_id["c2_bot"].bbox.y0 == 110.0


def test_bottom_margin_guard_flags_review():
    # Sayfa alt sınırını aşan blokların inceleme için bayraklandığını doğrular / Verifies bottom margin flag
    b1 = _make_test_block("b1", 50.0, 700.0, 250.0, 750.0, order=1)
    b2 = _make_test_block("b2", 50.0, 760.0, 250.0, 790.0, order=2)

    engine = ElasticFlowEngine(bottom_margin=40.0)
    # 800 pt sayfada alt sınır 760 pt'dir (800 - 40). b1 20 pt genişlerse b2 780-810 olur ve taşar.
    expansions = {"b1": 20.0}
    shifted = engine.reflow_column([b1, b2], expansions, page_height=800.0)

    assert shifted[1].needs_review
    assert "REVIEW_BOTTOM_MARGIN" in shifted[1].review_reason
