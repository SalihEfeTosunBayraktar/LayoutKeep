"""The packaged application has to carry its OCR weights.

rapidocr downloads its models into its own package directory the first time it runs. A one-file
build has no such directory, so the shipped application reached for models that were not there
and went to the network - which fails outright for anyone offline, while the README promises
image translation. The weights are packaged now, and this pins that the engine looks where the
spec puts them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from layoutkeep.ocr.engine import bundled_model_params


def test_a_development_run_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """No bundle, no override: the library's own resolution is correct outside a build."""
    monkeypatch.delattr("sys._MEIPASS", raising=False)

    assert bundled_model_params() == {}


def test_the_packaged_weights_are_found_and_named_by_stage(tmp_path: Path) -> None:
    models = tmp_path / "rapidocr" / "models"
    models.mkdir(parents=True)
    for name in (
        "PP-OCRv6_det_small.onnx",
        "PP-OCRv6_rec_small.onnx",
        "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    ):
        (models / name).write_bytes(b"")

    params = bundled_model_params(tmp_path)

    # Matched on the stage, not the architecture: rapidocr renames its models between versions.
    assert params["Det.model_path"].endswith("PP-OCRv6_det_small.onnx")
    assert params["Rec.model_path"].endswith("PP-OCRv6_rec_small.onnx")
    assert params["Cls.model_path"].endswith("ch_ppocr_mobile_v2.0_cls_mobile.onnx")


def test_a_bundle_without_weights_falls_back_rather_than_pointing_at_nothing(
    tmp_path: Path,
) -> None:
    """Handing rapidocr a path to a file that is not there would be worse than not helping."""
    assert bundled_model_params(tmp_path) == {}


def test_the_spec_packages_the_weights() -> None:
    """The engine looking in the right place is only half of it; the build has to put them
    there, and that is one line in a file nothing else tests."""
    spec = (Path(__file__).resolve().parent.parent / "packaging" / "layoutkeep_onefile.spec").read_text(
        encoding="utf-8"
    )

    assert 'rapidocr/models' in spec
    assert 'config.yaml' in spec
