"""The topic map: what a stretch is about, and how it reaches the translation.

No network here. The model is a parameter of `build_keyword_map`, so a fake answer proves the
parsing and the failure paths; the last test drives the real segment builder to show that a map on
disk actually reaches a segment's context.
"""

from __future__ import annotations

import json

from layoutkeep.core import tunables
from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Span,
    Style,
    segments_from_document,
)
from layoutkeep.core.keywords import (
    build_keyword_map,
    filled_entries,
    write_keyword_map,
)
from layoutkeep.ui.topic_map import TopicMapBuilder


def _document() -> Document:
    """A document with four text blocks: enough for two stretches at a small batch size."""
    doc = Document(source_path="x.pdf", source_format="pdf")
    page = Page(number=1, width=595.0, height=842.0, blocks=[])
    for index, text in enumerate(
        [
            "The opening chapter describes a fishing village on the Black Sea coast.",
            "A second paragraph continues the same scene with the same people.",
            "Halfway through, the book turns to a courtroom in the capital city.",
            "The last part returns to the village, changed, with the same families.",
        ]
    ):
        page.blocks.append(
            Block(
                id=f"b{index}",
                role=BlockRole.BODY,
                bbox=BBox(x0=0.0, y0=float(index * 20), x1=500.0, y1=float(index * 20 + 18)),
                lines=[
                    Line(
                        bbox=BBox(x0=0.0, y0=float(index * 20), x1=500.0, y1=float(index * 20 + 18)),
                        spans=[
                            Span(
                                text=text,
                                bbox=BBox(
                                    x0=0.0,
                                    y0=float(index * 20),
                                    x1=500.0,
                                    y1=float(index * 20 + 18),
                                ),
                                style=Style(size=12.0),
                            )
                        ],
                    )
                ],
            )
        )
    doc.pages.append(page)
    return doc


def test_each_stretch_gets_one_entry_with_its_block_ids():
    calls: list[str] = []

    def ask(system: str, user: str) -> str:
        calls.append(user)
        return '["village", "Black Sea"]' if len(calls) == 1 else '["courtroom"]'

    entries = build_keyword_map(_document(), ask, batch_chars=120, per_batch=4)
    assert len(entries) == 2
    assert entries[0]["block_ids"] == ["b0", "b1"]
    assert entries[1]["block_ids"] == ["b2", "b3"]
    assert entries[0]["keywords"] == ["village", "Black Sea"]
    assert len(calls) == 2


def test_a_fenced_or_chatty_answer_still_yields_words():
    """Small models wrap JSON in fences or add a sentence; neither should lose the map."""
    for reply in (
        '```json\n["harbour", "storm"]\n```',
        'Here are the keywords: ["harbour", "storm"] - hope that helps.',
        '["harbour", "storm"]',
    ):
        entries = build_keyword_map(_document(), lambda _s, _u, r=reply: r, batch_chars=120)
        assert entries[0]["keywords"] == ["harbour", "storm"], reply


def test_a_failed_stretch_keeps_its_place_with_no_words():
    def ask(system: str, user: str) -> str:
        raise RuntimeError("model down")

    entries = build_keyword_map(_document(), ask, batch_chars=120)
    assert len(entries) == 2, "a failure must not drop the stretch"
    assert all(entry["keywords"] == [] for entry in entries)
    assert filled_entries(entries) == (0, 0)


def test_garbage_answers_do_not_invent_words():
    assert build_keyword_map(_document(), lambda _s, _u: "no json here", batch_chars=120)[0][
        "keywords"
    ] == []
    assert build_keyword_map(_document(), lambda _s, _u: "[not json", batch_chars=120)[0][
        "keywords"
    ] == []


def test_the_map_file_is_written_where_it_is_asked_to_land(tmp_path):
    entries = [{"index": 0, "block_ids": ["b0"], "keywords": ["village"]}]
    target = write_keyword_map(entries, tmp_path / "deep" / "book.keyword-map.json")
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == entries


def test_the_auto_setting_is_off_by_default():
    spec = tunables.definition("translation.keyword_map_auto")
    assert spec is not None
    assert spec.default is False
    assert spec.kind == "bool"


def test_a_map_on_disk_reaches_the_context_of_its_blocks(tmp_path, monkeypatch):
    """The whole point: with the file in place, each segment carries 'This part is about: ...'."""
    monkeypatch.setenv("LAYOUTKEEP_TUNABLES", str(tmp_path / "tunables.json"))
    tunables.reset_all()
    try:
        doc = _document()
        assert "This part is about" not in segments_from_document(doc)[0].context_before

        map_path = write_keyword_map(
            [{"index": 0, "block_ids": ["b0", "b1", "b2", "b3"], "keywords": ["village", "court"]}],
            tmp_path / "book.keyword-map.json",
        )
        tunables.set_value("translation.keyword_map_path", str(map_path))

        with_map = segments_from_document(doc)
        assert with_map, "the document produced no segments"
        # Every block of the part carries the topic line, including the first: it is prepended after
        # the context cap so it can never be clipped away - that is the whole point of the map.
        assert "This part is about: village, court" in with_map[0].context_before
        assert "This part is about: village, court" in with_map[1].context_before
    finally:
        tunables.reset_all()


# -- the application's provider, as the run hands it over ------------------------------------------


class _Wrapper:
    """One of the decorators the application wraps its provider in: it forwards `translate` only.

    `ProtectedProvider`, `CachedProvider` and `DedupeProvider` all keep the real provider on
    `inner`, and none of them forwards `_chat` - which is the whole reason this test exists.
    """

    def __init__(self, inner) -> None:
        self.inner = inner

    def translate(self, segments, src_lang, tgt_lang, glossary=None, on_progress=None):
        return self.inner.translate(segments, src_lang, tgt_lang, glossary, on_progress)


def test_the_map_is_built_through_the_wrapper_stack(tmp_path, monkeypatch):
    """The switch that never ran with a real provider.

    WHY THIS EXISTS: `TopicMapBuilder` asked the outermost object for `_chat`, which is None behind
    every wrapper (`ProtectedProvider(CachedProvider(DedupeProvider(...)))`), so with the setting on
    the map was skipped with "this provider has no chat call" - the defect
    `providers/base.chat_callable` was written for, left open on this path.
    """
    monkeypatch.setenv("LAYOUTKEEP_TUNABLES", str(tmp_path / "tunables.json"))
    tunables.reset_all()

    class _Inner:
        def __init__(self) -> None:
            self.calls: list[list[dict]] = []

        def _chat(self, messages):
            self.calls.append(messages)
            return '["village", "Black Sea"]'

    inner = _Inner()
    statuses: list[str] = []
    try:
        target, previous = TopicMapBuilder(on_status=statuses.append).build(
            _document(), tmp_path / "book.tr.epub", _Wrapper(_Wrapper(inner))
        )
        assert target is not None, statuses
        # The map is pointed at for this run only, and the setting's own value comes back.
        assert tunables.get("translation.keyword_map_path") == str(target)
        assert previous == ""
    finally:
        tunables.reset_all()

    assert any(status.startswith("topic map:") for status in statuses), statuses
    assert inner.calls, "the chat call under the wrappers was never reached"
    entries = json.loads(target.read_text(encoding="utf-8"))
    assert entries[0]["keywords"] == ["village", "Black Sea"]
