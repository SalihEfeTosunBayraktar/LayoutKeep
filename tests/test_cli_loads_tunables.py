"""The command line reads the stored settings, as the application does.

Only `ui/app.py` called `tunables.load()`, so every CLI run - and every bench arm, which drives the
CLI through `translate_book.py` - translated with the defaults whatever the settings file said. The
bench's `--set translation.auto_glossary=true` never reached a translation (found by the tr-layout
agent, D-020), so arms B0, B1 and C differed in code, not in settings.
"""

from __future__ import annotations

import json

import pytest

from layoutkeep import cli
from layoutkeep.core import tunables


def test_the_cli_reads_the_settings_file(tmp_path, monkeypatch):
    stored = tmp_path / "tunables.json"
    stored.write_text(json.dumps({"translation.auto_glossary": True}), encoding="utf-8")
    monkeypatch.setenv("LAYOUTKEEP_TUNABLES", str(stored))
    tunables.reset_all()
    try:
        with pytest.raises(SystemExit):
            cli.main(["--no-such-option"])
        assert tunables.get("translation.auto_glossary") is True
    finally:
        tunables.reset_all()
