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
