"""Runtime-adjustable parameters and the dialog that edits them.

The point of this feature is that a change applies without restarting, which means the call
sites have to read the value when they use it. A test that only checks the registry would
pass even if every call site had bound its value at import time again - so these go through
the real functions.
"""

from __future__ import annotations

import pytest

from layoutkeep.core import tunables


@pytest.fixture(autouse=True)
def _clean_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUTKEEP_TUNABLES", str(tmp_path / "tunables.json"))
    tunables.reset_all()
    yield
    tunables.reset_all()


def test_defaults_match_the_constants_the_code_shipped_with():
    """An untouched installation must behave exactly as it did before this existed."""
    from layoutkeep.providers import batching, passthrough

    assert tunables.get("batch.adaptive_max_segments") == batching.DEFAULT_ADAPTIVE_MAX_SEGMENTS
    assert tunables.get("passthrough.min_words") == passthrough.MIN_WORDS
    assert tunables.get("timeout.warm_batch_s") == batching.WARM_BATCH_BASE_TIMEOUT_S


def test_a_change_reaches_the_batching_ceiling_without_a_restart():
    from layoutkeep.providers.batching import AdaptiveBatchSize

    assert AdaptiveBatchSize()._max == 20
    tunables.set_value("batch.adaptive_max_segments", 5)
    assert AdaptiveBatchSize()._max == 5, "the value was bound at import time"


def test_a_change_reaches_passthrough_detection_without_a_restart():
    from layoutkeep.core.docir import Segment
    from layoutkeep.providers.passthrough import is_passthrough

    segment = Segment(block_id="b", source="One two three")
    segment.target = "One two three"
    assert not is_passthrough(segment), "three words is below the default threshold"

    tunables.set_value("passthrough.min_words", 2)
    assert is_passthrough(segment), "the new threshold was not read at use time"


def test_a_change_reaches_the_batch_timeout_without_a_restart():
    from layoutkeep.providers.batching import batch_timeout

    before = batch_timeout(1000, is_first=False, chars_per_second=100)
    tunables.set_value("timeout.warm_batch_s", 300.0)
    after = batch_timeout(1000, is_first=False, chars_per_second=100)
    assert after > before


def test_values_are_clamped_rather_than_rejected():
    """This is fed by a spin box; an extreme means the user wanted the extreme."""
    spec = tunables.definition("fit.min_scale")
    assert tunables.set_value("fit.min_scale", 0.01) == spec.minimum
    assert tunables.set_value("fit.min_scale", 99.0) == spec.maximum


def test_setting_a_value_back_to_its_default_stops_being_an_override():
    tunables.set_value("passthrough.min_words", 9)
    assert tunables.is_overridden("passthrough.min_words")

    tunables.set_value("passthrough.min_words", tunables.definition("passthrough.min_words").default)
    assert not tunables.is_overridden("passthrough.min_words")


def test_overrides_survive_a_save_and_load():
    tunables.set_value("batch.chunk_size", 7)
    path = tunables.save()
    tunables.reset_all()
    assert tunables.get("batch.chunk_size") == 20

    tunables.load(path)
    assert tunables.get("batch.chunk_size") == 7


def test_an_unreadable_settings_file_leaves_the_defaults_alone(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    tunables.load(broken)

    assert tunables.get("batch.chunk_size") == 20


def test_a_stored_key_this_build_no_longer_has_is_ignored(tmp_path):
    stale = tmp_path / "stale.json"
    stale.write_text('{"gone.key": 5, "batch.chunk_size": 9}', encoding="utf-8")

    tunables.load(stale)

    assert tunables.get("batch.chunk_size") == 9


def test_every_advanced_entry_says_what_breaks():
    """"Be careful" is not a warning. Each one has to name the consequence."""
    for spec in tunables.definitions(tunables.ADVANCED):
        assert spec.warning, f"{spec.key} has no warning"
        assert len(spec.warning) > 40, f"{spec.key}: warning too vague"


def test_the_dialog_edits_every_tunable(qtbot):
    from layoutkeep.ui.tweaks_dialog import TweaksDialog

    dialog = TweaksDialog()
    qtbot.addWidget(dialog)

    assert set(dialog._editors) == {t.key for t in tunables.TUNABLES}


def test_applying_the_dialog_takes_effect_immediately(qtbot):
    from layoutkeep.providers.batching import AdaptiveBatchSize
    from layoutkeep.ui.tweaks_dialog import TweaksDialog

    dialog = TweaksDialog()
    qtbot.addWidget(dialog)

    dialog._editors["batch.adaptive_max_segments"].setValue(5)
    dialog.apply_values()

    assert AdaptiveBatchSize()._max == 5
    assert tunables.storage_path().exists()


def test_restoring_defaults_clears_everything(qtbot):
    from layoutkeep.ui.tweaks_dialog import TweaksDialog

    tunables.set_value("batch.chunk_size", 3)
    dialog = TweaksDialog()
    qtbot.addWidget(dialog)

    dialog._reset_all()

    assert tunables.overrides() == {}
    assert dialog._editors["batch.chunk_size"].value() == 20


def test_the_new_layout_settings_default_to_the_constants_they_replaced():
    """Same rule as the older ones: an untouched installation reads exactly as it did before."""
    from layoutkeep.fitting.fit import MIN_SCALE

    assert tunables.get("fit.min_scale") == MIN_SCALE
    assert tunables.get("table.cell_overlap_ratio") == 0.35
    assert tunables.get("table.row_overlap_ratio") == 0.6
    assert tunables.get("table.column_align_ratio") == 1.2
    assert tunables.get("table.height_similarity") == 1.6
    assert tunables.get("merge.line_gap_ratio") == 0.6
    assert tunables.get("merge.line_height_ratio") == 1.2
    assert tunables.get("merge.rotation_eps_deg") == 0.5
    assert tunables.get("redact.coverage_ratio") == 0.6


def test_the_smallest_font_scale_setting_actually_reaches_the_fitting_stage():
    """It was registered, editable in the dialog, and read by nothing at all: `fit_segment` bound
    it as a default argument, which Python evaluates once at import. Changing it did nothing."""
    from layoutkeep.fitting.fit import min_scale_setting

    assert min_scale_setting() == 0.85
    tunables.set_value("fit.min_scale", 0.6)
    assert min_scale_setting() == 0.6


def test_the_table_settings_reach_the_reader():
    """The reader must look the value up when it uses it. Had it bound the constant at import -
    which is what every one of these replaced - both readings below would be the same."""
    from layoutkeep.core.docir import BBox, Block, BlockRole
    from layoutkeep.readers.pdf_reader import _similar_height

    short = Block(id="a", role=BlockRole.BODY, bbox=BBox(0, 0, 50, 10))
    tall = Block(id="b", role=BlockRole.BODY, bbox=BBox(60, 0, 110, 30))  # three times as tall

    assert not _similar_height(short, tall)  # default 1.6 says these are different things
    tunables.set_value("table.height_similarity", 4.0)
    assert _similar_height(short, tall)
