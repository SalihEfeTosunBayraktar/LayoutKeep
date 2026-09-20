"""The fit mode is a setting, and both front ends read the same one.

They did not: the application was pinned to `FitMode.STRICT`, so the reflow path (which removes the
whole "did not fit" flag class) was unreachable from the GUI, while the CLI could reflow. These
tests pin the wiring, not the fitting itself.
"""

from __future__ import annotations

from layoutkeep.core import tunables
from layoutkeep.fitting import FitMode


def test_the_setting_exists_and_defaults_to_strict():
    """Strict by default: reflow removed D1 entirely on a journal and cost an L7 on a form."""
    assert tunables.get("fitting.reflow") is False


class _Args:
    def __init__(self, fit_mode=None):
        self.fit_mode = fit_mode


def test_the_flag_wins_when_it_is_given(monkeypatch):
    from layoutkeep import cli

    monkeypatch.setattr(cli.tunables, "get", lambda key: False)

    assert cli.fit_mode_from(_Args("reflow")) is FitMode.REFLOW
    assert cli.fit_mode_from(_Args("strict")) is FitMode.STRICT


def test_without_a_flag_the_setting_decides(monkeypatch):
    from layoutkeep import cli

    monkeypatch.setattr(cli.tunables, "get", lambda key: True)
    assert cli.fit_mode_from(_Args()) is FitMode.REFLOW

    monkeypatch.setattr(cli.tunables, "get", lambda key: False)
    assert cli.fit_mode_from(_Args()) is FitMode.STRICT


def test_the_application_follows_the_setting(monkeypatch):
    """`ui.worker` asks the same registry; a hard-coded mode would show up here."""
    from layoutkeep.ui import worker

    source = worker.__file__
    text = open(source, encoding="utf-8").read()

    assert 'tunables.get("fitting.reflow")' in text, "the worker pins the fit mode again"
