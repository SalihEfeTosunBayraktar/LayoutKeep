"""The automatic document glossary: the model renders the document's recurring terms, once.

No network here. `ask` is a parameter of `build_doc_glossary`, so a written answer proves the
parsing and the failure paths; the rest of the file drives the real worker and the real command
line with a provider whose chat call is a string. What is pinned is that ONE request happens, that
its terms reach the translation, the fitting pass and the check as one merged list, and that the
user's own glossary file wins where the two disagree.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from layoutkeep import cli
from layoutkeep.core import tunables
from layoutkeep.core.doc_glossary import build_doc_glossary, merge_glossaries, write_glossary
from layoutkeep.core.docir import (
    BBox,
    Block,
    BlockRole,
    Document,
    Line,
    Page,
    Span,
    Style,
)
from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.worker import TranslationWorker
from layoutkeep.writers.converter import read_any_document

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import build_epub_fixture

#: Two terms that recur in the sentences below, each spelled the same way every time. The
#: candidate finder is a frequency rule (core/terms.py), so the test's text has to repeat for
#: there to be anything to ask about - and `test_the_candidates_are_what_is_asked_about` says so
#: out loud if that ever stops being true.
TERM = "buffer overflow"
SECOND_TERM = "sample rate"

SENTENCES = (
    f"The {TERM} test measures the {SECOND_TERM} of the receiver.",
    f"A second {TERM} test repeats the {SECOND_TERM} on the same bench.",
    f"The footnote describes the {TERM} together with its {SECOND_TERM}.",
    f"Finally the {TERM} bench is described again in the appendix.",
)

#: What the fake model answers with, and what the user's own file says about the same term.
AUTO_TERM = "otomatik terim"
AUTO_TERM_2 = "ikinci otomatik terim"
USER_TERM = "kullanicinin terimi"


# -- fixtures -------------------------------------------------------------------------------------


def _document() -> Document:
    """Four body blocks whose text repeats both terms: enough for a candidate list."""
    doc = Document(source_path="x.epub", source_format="epub")
    page = Page(number=1, width=595.0, height=842.0, blocks=[])
    for index, text in enumerate(SENTENCES):
        box = BBox(x0=0.0, y0=float(index * 20), x1=500.0, y1=float(index * 20 + 18))
        page.blocks.append(
            Block(
                id=f"b{index}",
                role=BlockRole.BODY,
                bbox=box,
                lines=[Line(bbox=box, spans=[Span(text=text, bbox=box, style=Style(size=12.0))])],
            )
        )
    doc.pages.append(page)
    return doc


def _rewrite(block: Block, text: str) -> None:
    """Replace a block's text, keeping one span: the fixture's markup is not what is under test."""
    line = block.lines[0]
    line.spans = [line.spans[0]]
    line.spans[0].text = text
    block.lines = [line]


def _epub_with_recurring_terms(tmp_path: Path) -> Path:
    """The sample EPUB's body blocks rewritten so its terms repeat, written to disk.

    The worker reads a real file, and this is the only EPUB the project builds in tests - so the
    fixture is reused and its body blocks are filled with text the candidate finder can see.
    """
    sample = tmp_path / "sample.epub"
    build_epub_fixture.build_sample_epub(sample)

    doc = read_any_document(sample)
    bodies = [block for _page, block in doc.iter_blocks() if block.role is BlockRole.BODY]
    assert len(bodies) >= len(SENTENCES), "the fixture lost body blocks; the test text needs four"
    for block, text in zip(bodies, SENTENCES, strict=False):
        _rewrite(block, text)
    return cli._write_document(doc, sample, tmp_path / "terms.epub")[0]


def _pdf_with_recurring_terms(path: Path) -> Path:
    """Two pages carrying the same four sentences: a PDF run also has terms to ask about."""
    import pymupdf

    doc = pymupdf.open()
    try:
        for _number in (1, 2):
            page = doc.new_page(width=400, height=500)
            page.insert_textbox(
                pymupdf.Rect(40, 60, 360, 300), " ".join(SENTENCES), fontsize=11, fontname="helv"
            )
        doc.save(str(path))
    finally:
        doc.close()
    return path


def _candidates(path: Path) -> list[str]:
    """The candidate phrases the run itself will offer the model, read from the same file."""
    from layoutkeep.core.terms import suggest_from_document

    return [candidate.phrase for candidate in suggest_from_document(read_any_document(path))]


class _ChatProvider:
    """The real provider chain, given the chat call the automatic glossary asks with, and a spy.

    The chain the application builds hides `_chat` under its wrappers, so this wraps the real one
    rather than replacing it: the unwrapping the builder does is then exercised, and every
    translate call is recorded with the glossary it was handed.
    """

    def __init__(self, inner, reply: str, seen: list[dict | None], chats: list[list[dict]]) -> None:
        self.inner = inner
        self._reply = reply
        self._seen = seen
        self._chats = chats

    def _chat(self, messages):
        self._chats.append(messages)
        return self._reply

    def translate(self, segments, src_lang, tgt_lang, glossary=None, on_progress=None):
        self._seen.append(glossary)
        return self.inner.translate(segments, src_lang, tgt_lang, glossary, on_progress)


def _patch_worker_provider(monkeypatch, reply, seen, chats) -> None:
    import layoutkeep.ui.worker as worker_module

    real_build = worker_module._build_provider

    def build(config):
        provider, memory, terms = real_build(config)
        return _ChatProvider(provider, reply, seen, chats), memory, terms

    monkeypatch.setattr(worker_module, "_build_provider", build)


def _patch_cli_provider(monkeypatch, reply, seen, chats) -> None:
    real_build = cli._build_provider

    def build(args):
        provider, memory = real_build(args)
        return _ChatProvider(provider, reply, seen, chats), memory

    monkeypatch.setattr(cli, "_build_provider", build)


def _job(source: Path, out: Path, **overrides) -> JobConfig:
    defaults = {
        "input_path": str(source),
        "output_path": str(out),
        "source_lang": "en",
        "target_lang": "tr",
        "provider": ProviderConfig(kind="fake"),
    }
    defaults.update(overrides)
    return JobConfig(**defaults)


def _glossary_file(out: Path) -> Path:
    """Where the run's own list lands: '<output>.glossary.json'."""
    return out.with_name(f"{out.stem}.glossary.json")


# -- the request ----------------------------------------------------------------------------------


def test_the_candidates_are_what_is_asked_about():
    """A guard for every test below: the terms they name must really be candidates."""
    from layoutkeep.core.terms import suggest_from_document

    phrases = [candidate.phrase for candidate in suggest_from_document(_document())]
    assert TERM in phrases and SECOND_TERM in phrases, phrases


def test_the_answer_becomes_the_glossary():
    calls: list[str] = []

    def ask(system: str, user: str) -> str:
        calls.append(user)
        return json.dumps({TERM: AUTO_TERM, SECOND_TERM: AUTO_TERM_2})

    glossary = build_doc_glossary(_document(), ask, source_lang="en", target_lang="tr")

    assert glossary == {TERM: AUTO_TERM, SECOND_TERM: AUTO_TERM_2}
    assert len(calls) == 1, "the document is asked about once, not once per page"


def test_a_fenced_or_chatty_answer_still_yields_terms():
    """Small models wrap JSON in fences or add a sentence; neither may lose the list."""
    for reply in (
        f'```json\n{json.dumps({TERM: AUTO_TERM})}\n```',
        f'Here is the glossary: {json.dumps({TERM: AUTO_TERM})} - hope that helps.',
        json.dumps({TERM: AUTO_TERM}),
    ):
        glossary = build_doc_glossary(
            _document(), lambda _s, _u, r=reply: r, source_lang="en", target_lang="tr"
        )
        assert glossary == {TERM: AUTO_TERM}, reply


def test_garbage_answers_do_not_invent_terms():
    for reply in ("no json here at all", "[not json", "{}", '{"a": [1, 2]}'):
        glossary = build_doc_glossary(
            _document(), lambda _s, _u, r=reply: r, source_lang="en", target_lang="tr"
        )
        assert glossary == {}, reply


def test_a_failed_call_is_an_empty_glossary_and_says_why(capsys):
    """A missing term policy must never cost a two-hour run."""

    def ask(system: str, user: str) -> str:
        raise RuntimeError("model down")

    assert build_doc_glossary(_document(), ask, source_lang="en", target_lang="tr") == {}
    assert "CALL FAILED" in capsys.readouterr().out


def test_a_term_the_model_invented_is_dropped():
    """Only the candidates were asked about; anything else is not a term of this document."""
    reply = json.dumps({TERM: AUTO_TERM, "quantum tunnelling": "kuantum tunelleme"})
    glossary = build_doc_glossary(_document(), lambda _s, _u: reply, source_lang="en", target_lang="tr")
    assert glossary == {TERM: AUTO_TERM}


def test_a_re_cased_term_keeps_the_documents_own_spelling():
    """The glossary matches a source term case-sensitively, so a re-cased key never matches."""
    reply = json.dumps({TERM.title(): AUTO_TERM})
    glossary = build_doc_glossary(_document(), lambda _s, _u: reply, source_lang="en", target_lang="tr")
    assert glossary == {TERM: AUTO_TERM}


def test_a_name_that_stays_the_same_is_kept():
    """'Leave this one alone' is a decision, not a missing answer."""
    reply = json.dumps({TERM: TERM})
    glossary = build_doc_glossary(_document(), lambda _s, _u: reply, source_lang="en", target_lang="tr")
    assert glossary == {TERM: TERM}


def test_the_request_names_both_languages_and_shows_the_document():
    calls: list[tuple[str, str]] = []

    def ask(system: str, user: str) -> str:
        calls.append((system, user))
        return "{}"

    build_doc_glossary(_document(), ask, source_lang="en", target_lang="tr")
    system, user = calls[0]

    assert "English" in user and "Turkish" in user, "a code the model has to guess a language from"
    assert TERM in user, "the candidates are not in the request"
    assert SENTENCES[0] in user, "the terms are asked about without any of the document"
    assert "omitted term is better" in user, "nothing says a guess is worse than a gap"
    assert system.strip()


# -- merging with what the user already decided ---------------------------------------------------


def test_the_users_own_glossary_wins_on_a_conflict():
    automatic = {TERM: AUTO_TERM, SECOND_TERM: AUTO_TERM_2}
    merged = merge_glossaries(automatic, {TERM: USER_TERM})
    assert merged == {TERM: USER_TERM, SECOND_TERM: AUTO_TERM_2}


def test_one_term_never_ends_up_in_the_glossary_twice():
    """Two keys for one term would fight each other inside the prompt."""
    assert merge_glossaries({TERM: AUTO_TERM}, {TERM.title(): USER_TERM}) == {TERM.title(): USER_TERM}


def test_the_list_is_written_beside_the_output(tmp_path):
    target = write_glossary({TERM: AUTO_TERM}, tmp_path / "deep" / "book.tr.glossary.json")
    assert json.loads(target.read_text(encoding="utf-8")) == {TERM: AUTO_TERM}


# -- the setting ----------------------------------------------------------------------------------


def test_the_setting_exists_and_is_off_by_default():
    spec = tunables.definition("translation.auto_glossary")
    assert spec.kind == "bool"
    assert spec.default is False
    assert tunables.get("translation.auto_glossary") is False

    # Sitting with the topic map: both are preparation of the document before it is segmented.
    neighbour = tunables.definition("translation.keyword_map_auto")
    assert (spec.section, spec.group) == (neighbour.section, neighbour.group)


# -- the application ------------------------------------------------------------------------------


def test_the_worker_translates_with_the_merged_glossary(qtbot, tmp_path, monkeypatch):
    source = _epub_with_recurring_terms(tmp_path)
    out = tmp_path / "app.tr.epub"
    candidates = _candidates(source)
    assert len(candidates) >= 2, candidates
    user_file = tmp_path / "user.json"
    user_file.write_text(json.dumps({candidates[0]: USER_TERM}), encoding="utf-8")

    seen: list[dict | None] = []
    chats: list[list[dict]] = []
    _patch_worker_provider(
        monkeypatch,
        json.dumps({candidates[0]: AUTO_TERM, candidates[1]: AUTO_TERM_2}),
        seen,
        chats,
    )

    tunables.set_value("translation.auto_glossary", True)
    try:
        worker = TranslationWorker(_job(source, out, glossary_path=str(user_file)))
        failed: list[str] = []
        worker.failed.connect(failed.append)
        worker.run()
    finally:
        tunables.set_value("translation.auto_glossary", False)

    assert not failed, failed
    expected = {candidates[0]: USER_TERM, candidates[1]: AUTO_TERM_2}
    assert json.loads(_glossary_file(out).read_text(encoding="utf-8")) == expected
    assert len(chats) == 1, "the document must be asked about once"
    assert seen and all(handed == expected for handed in seen), seen


def test_the_memory_key_carries_the_merged_glossary(qtbot, tmp_path, monkeypatch):
    """A translation stored before the term policy existed must not be served straight back.

    The chain is built a second time once the list is on disk, so the memory - keyed by model AND
    glossary - separates what the run is about to ask for from what an earlier run cached.
    """
    source = _epub_with_recurring_terms(tmp_path)
    out = tmp_path / "app-mem.tr.epub"
    candidates = _candidates(source)
    merged = {candidates[0]: AUTO_TERM}
    seen: list[dict | None] = []
    chats: list[list[dict]] = []
    _patch_worker_provider(monkeypatch, json.dumps(merged), seen, chats)
    memory_path = tmp_path / "mem.sqlite"

    tunables.set_value("translation.auto_glossary", True)
    try:
        TranslationWorker(_job(source, out, memory_path=str(memory_path))).run()
    finally:
        tunables.set_value("translation.auto_glossary", False)

    from layoutkeep.ui.worker import _glossary_fingerprint

    with sqlite3.connect(memory_path) as conn:
        stored = {row[0] for row in conn.execute("SELECT DISTINCT model FROM translations")}
    assert stored == {f"fake|gloss:{_glossary_fingerprint(merged)}"}, stored


def test_the_worker_writes_nothing_and_asks_nothing_when_the_setting_is_off(
    qtbot, tmp_path, monkeypatch
):
    """A run that asked anyway would pay a request nobody opted into."""
    source = _epub_with_recurring_terms(tmp_path)
    out = tmp_path / "app-off.tr.epub"
    seen: list[dict | None] = []
    chats: list[list[dict]] = []
    _patch_worker_provider(monkeypatch, "{}", seen, chats)

    assert tunables.get("translation.auto_glossary") is False
    worker = TranslationWorker(_job(source, out))
    worker.run()

    assert chats == [], "the model was asked with the setting off"
    assert not _glossary_file(out).exists()
    assert seen and all(handed is None for handed in seen), seen


def test_the_fitting_pass_is_handed_the_merged_glossary(qtbot, tmp_path, monkeypatch):
    """A shorter rendering asked for while fitting must obey the same terms as the first pass."""
    source = _pdf_with_recurring_terms(tmp_path / "terms.pdf")
    out = tmp_path / "fit.tr.pdf"
    candidates = _candidates(source)
    assert candidates, "the fixture PDF repeats nothing"
    seen: list[dict | None] = []
    chats: list[list[dict]] = []
    _patch_worker_provider(monkeypatch, json.dumps({candidates[0]: AUTO_TERM}), seen, chats)

    handed: list[dict | None] = []

    def spy(self, doc, segments, config, provider=None):
        # The pass is replaced by what it is given: the fit reads the glossary from this config.
        from layoutkeep.ui.worker import load_glossary_terms

        handed.append(load_glossary_terms(config.glossary_path))

    monkeypatch.setattr(TranslationWorker, "_fit_pdf_pass", spy)

    tunables.set_value("translation.auto_glossary", True)
    try:
        worker = TranslationWorker(_job(source, out))
        failed: list[str] = []
        worker.failed.connect(failed.append)
        worker.run()
    finally:
        tunables.set_value("translation.auto_glossary", False)

    assert not failed, failed
    assert handed == [{candidates[0]: AUTO_TERM}], handed


# -- the command line -----------------------------------------------------------------------------


def test_the_cli_merges_the_automatic_terms_with_the_glossary_file(tmp_path, capsys, monkeypatch):
    source = _epub_with_recurring_terms(tmp_path)
    out = tmp_path / "cli.tr.epub"
    candidates = _candidates(source)
    assert len(candidates) >= 2, candidates
    user_file = tmp_path / "user.json"
    user_file.write_text(json.dumps({candidates[0]: USER_TERM}), encoding="utf-8")

    seen: list[dict | None] = []
    chats: list[list[dict]] = []
    _patch_cli_provider(
        monkeypatch,
        json.dumps({candidates[0]: AUTO_TERM, candidates[1]: AUTO_TERM_2}),
        seen,
        chats,
    )

    tunables.set_value("translation.auto_glossary", True)
    try:
        code = cli.main(
            [
                "translate", str(source), "--from", "en", "--to", "tr", "--provider", "fake",
                "--output", str(out), "--glossary", str(user_file),
            ]
        )
    finally:
        tunables.set_value("translation.auto_glossary", False)

    printed = capsys.readouterr().out
    assert code == cli.EXIT_OK, printed
    assert "glossary  2 automatic terms (+1 from the file)" in printed, printed
    expected = {candidates[0]: USER_TERM, candidates[1]: AUTO_TERM_2}
    assert json.loads(_glossary_file(out).read_text(encoding="utf-8")) == expected
    assert all(handed == expected for handed in seen), seen
    # The check that reports which terms were honoured reads the merged list, not the file alone.
    assert "term occurrences honoured" in printed, printed


def test_the_cli_asks_nothing_when_the_setting_is_off(tmp_path, capsys, monkeypatch):
    source = _epub_with_recurring_terms(tmp_path)
    out = tmp_path / "cli-off.tr.epub"
    seen: list[dict | None] = []
    chats: list[list[dict]] = []
    _patch_cli_provider(monkeypatch, "{}", seen, chats)

    assert tunables.get("translation.auto_glossary") is False
    code = cli.main(
        [
            "translate", str(source), "--from", "en", "--to", "tr", "--provider", "fake",
            "--output", str(out),
        ]
    )

    printed = capsys.readouterr().out
    assert code == cli.EXIT_OK, printed
    assert chats == []
    assert not _glossary_file(out).exists()
    assert "automatic terms" not in printed
    assert seen and all(handed is None for handed in seen), seen
