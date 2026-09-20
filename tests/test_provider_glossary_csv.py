"""Glossary files: JSON, and the spreadsheet a term list usually starts as."""

from __future__ import annotations

import json

import pytest

from layoutkeep.providers.glossary import Glossary


def test_json_is_still_the_primary_format(tmp_path):
    path = tmp_path / "g.json"
    path.write_text(json.dumps({"Report": "Rapor"}), encoding="utf-8")

    assert Glossary.load(path).terms == {"Report": "Rapor"}


def test_a_comma_separated_file_is_read(tmp_path):
    path = tmp_path / "g.csv"
    path.write_text("Report,Rapor\nDraft,Taslak\n", encoding="utf-8")

    assert Glossary.load(path).terms == {"Report": "Rapor", "Draft": "Taslak"}


def test_a_tab_separated_file_with_a_header_is_read(tmp_path):
    path = tmp_path / "g.tsv"
    path.write_text("source\ttarget\nReport\tRapor\n", encoding="utf-8")

    assert Glossary.load(path).terms == {"Report": "Rapor"}


def test_a_semicolon_separated_file_is_read(tmp_path):
    path = tmp_path / "g.csv"
    path.write_text("Report;Rapor\n", encoding="utf-8")

    assert Glossary.load(path).terms == {"Report": "Rapor"}


def test_rows_without_a_term_are_skipped(tmp_path):
    path = tmp_path / "g.csv"
    path.write_text("Report,Rapor\n,\nOnlyOne\n", encoding="utf-8")

    assert Glossary.load(path).terms == {"Report": "Rapor"}


def test_a_json_array_is_refused_with_a_clear_message(tmp_path):
    path = tmp_path / "g.json"
    path.write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(TypeError):
        Glossary.load(path)
