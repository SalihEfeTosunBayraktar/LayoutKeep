"""The layout model is used whenever it is installed, by the CLI and the desktop worker alike.

It used to be off unless `--layout-detector` was given, and the desktop worker never used it:
every result of the translation campaign was measured with it, and a user got the reading without.
"""

from __future__ import annotations

import argparse

import pytest

from layoutkeep import cli
from layoutkeep.ocr import layout_detector
from layoutkeep.ui import worker


def _args(*argv: str) -> argparse.Namespace:
    return cli.build_parser().parse_args(["translate", "in.pdf", "--to", "tr", *argv])


def test_an_installed_model_is_used_without_asking(monkeypatch) -> None:
    sentinel = object()
    monkeypatch.setattr(layout_detector, "load_detector", lambda: sentinel)
    assert cli._layout_detector(_args()) is sentinel


def test_no_layout_detector_reads_without_it(monkeypatch) -> None:
    monkeypatch.setattr(layout_detector, "load_detector", lambda: object())
    assert cli._layout_detector(_args("--no-layout-detector")) is None


def test_a_missing_model_is_no_error_unless_it_was_required(monkeypatch) -> None:
    monkeypatch.setattr(layout_detector, "load_detector", lambda: None)
    assert cli._layout_detector(_args()) is None
    with pytest.raises(SystemExit):
        cli._layout_detector(_args("--layout-detector"))


def test_the_desktop_worker_reads_with_the_installed_model(monkeypatch, tmp_path) -> None:
    sentinel = object()
    seen = {}
    monkeypatch.setattr(layout_detector, "load_detector", lambda: sentinel)

    def read_any_document(path, *, classifier=None, layout=None):
        seen["layout"] = layout
        return "doc"

    monkeypatch.setattr("layoutkeep.writers.converter.read_any_document", read_any_document)
    assert worker._read_document(tmp_path / "in.pdf") == "doc"
    assert seen["layout"] is sentinel
