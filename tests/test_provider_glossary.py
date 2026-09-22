"""Unit tests for Glossary - no network."""

from __future__ import annotations

import json

from layoutkeep.core.docir import Segment
from layoutkeep.providers.glossary import Glossary


def test_load_json(tmp_path):
    path = tmp_path / "glossary.json"
    path.write_text(json.dumps({"server": "serveur", "client": "client"}), encoding="utf-8")
    glossary = Glossary.load(path)
    assert glossary.terms == {"server": "serveur", "client": "client"}


def test_terms_in_matches_whole_word_only():
    glossary = Glossary({"run": "courir"})
    assert glossary.terms_in("Please run this") == [("run", "courir")]
    assert glossary.terms_in("The runway is closed") == []
    assert glossary.terms_in("running fast") == []


def test_terms_in_is_case_aware():
    glossary = Glossary({"Server": "Serveur"})
    assert glossary.terms_in("The Server is up") == [("Server", "Serveur")]
    assert glossary.terms_in("the server is up") == []


def test_verify_marks_needs_review_when_term_missing_from_target():
    glossary = Glossary({"server": "serveur"})
    segments = [Segment(block_id="b1", source="Restart the server", target="Redemarrer maintenant")]

    checked, report = glossary.verify(segments)

    assert checked[0].needs_review is True
    assert report == {"checked": 1, "honoured": 0}


def test_verify_passes_when_term_honoured():
    glossary = Glossary({"server": "serveur"})
    segments = [Segment(block_id="b1", source="Restart the server", target="Redemarrer le serveur")]

    checked, report = glossary.verify(segments)

    assert checked[0].needs_review is False
    assert report == {"checked": 1, "honoured": 1}


def test_verify_matches_term_inside_inline_style_marker():
    """A glossary term sitting inside a <0>...</0> marked run must still be found."""
    glossary = Glossary({"server": "serveur"})
    segments = [
        Segment(
            block_id="b1",
            source="Restart the <0>server</0> now",
            target="Redemarrer le <0>serveur</0> maintenant",
        )
    ]

    checked, report = glossary.verify(segments)

    assert checked[0].needs_review is False
    assert report == {"checked": 1, "honoured": 1}


def test_verify_ignores_segments_without_glossary_terms():
    glossary = Glossary({"server": "serveur"})
    segments = [Segment(block_id="b1", source="Hello world", target="Bonjour le monde")]

    checked, report = glossary.verify(segments)

    assert checked[0].needs_review is False
    assert report == {"checked": 0, "honoured": 0}


def _honoured(term: str, target: str) -> bool:
    glossary = Glossary({"buffer": term})
    checked, _report = glossary.verify(
        [Segment(block_id="b1", source="The buffer is full", target=target)]
    )
    return checked[0].needs_review is False


def test_verify_accepts_the_target_term_with_a_suffix():
    """Agglutinative targets inflect the term: 'tampon' is honoured by 'tamponun', 'tamponlar'."""
    assert _honoured("tampon", "Bu tamponun boyutu sabit")
    assert _honoured("tampon", "Tamponlar dolu")


def test_verify_accepts_the_target_term_at_a_sentence_start():
    assert _honoured("tampon", "Tampon dolu")
    assert _honoured("ilke", "İlke basit")


def test_verify_accepts_a_softened_final_consonant():
    """Turkish softens a final p/ç/t/k before a vowel: 'ışık' -> 'ışığın', 'kitap' -> 'kitabı'."""
    assert _honoured("ışık", "ışığın hızı")
    assert _honoured("kitap", "kitabı okudum")


def test_verify_still_flags_a_term_that_is_not_there():
    assert not _honoured("tampon", "Arabellek dolu")
    # The term must start a word: a match inside another word is not the term.
    assert not _honoured("tampon", "Karttampon yok")
