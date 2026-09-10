"""Widget tests for the job setup screen."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from layoutkeep.ui.job import JobConfig, ProviderConfig
from layoutkeep.ui.job_setup import JobSetupWidget
from layoutkeep.ui.settings import app_settings


def test_every_provider_kind_is_offered_in_the_profile_list(qtbot):
    """The list the user picks from has to hold every provider the app can actually run.

    DeepL was finished, wired into the worker and the CLI, and reachable from neither: the
    setup screen's kind dropdown was created but never added to a layout, and the settings
    dialog offered only "openai" and "fake". The kind now lives on the profile, and this is
    the list of profiles.
    """
    widget = JobSetupWidget()
    qtbot.addWidget(widget)

    combo = widget._provider_profile_combo
    kinds = {p.kind for p in combo.profiles()}

    assert "openai" in kinds
    assert "deepl" in kinds


def test_emits_job_config_with_selected_values(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUTKEEP_DEV_PROVIDERS", "1")
    widget = JobSetupWidget()
    qtbot.addWidget(widget)

    input_path = tmp_path / "book.epub"
    input_path.write_text("x")
    output_path = tmp_path / "book.out.epub"

    widget._input_path.setText(str(input_path))
    widget._output_path.setText(str(output_path))
    widget._target_lang.setCurrentText("de")
    combo = widget._provider_profile_combo
    fake = next(p for p in combo.profiles() if p.kind == "fake")
    combo.select_profile(fake.name)

    received: list[JobConfig] = []
    widget.job_ready.connect(received.append)
    widget._start_btn.click()

    assert len(received) == 1
    config = received[0]
    assert config.input_path == str(input_path)
    assert config.output_path == str(output_path)
    assert config.target_lang == "de"
    assert config.provider.kind == "fake"


def test_fake_provider_selection_ignores_openai_settings(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUTKEEP_DEV_PROVIDERS", "1")
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    input_path = tmp_path / "book.epub"
    input_path.write_text("x")
    widget._input_path.setText(str(input_path))
    widget._output_path.setText(str(tmp_path / "book.out.epub"))
    combo = widget._provider_profile_combo
    fake = next(p for p in combo.profiles() if p.kind == "fake")
    combo.select_profile(fake.name)
    assert widget._provider_config.kind == "fake"

    received: list[JobConfig] = []
    widget.job_ready.connect(received.append)
    widget._start_btn.click()

    assert received[0].provider.kind == "fake"


def test_browsing_input_prefills_output_path(qtbot, tmp_path, monkeypatch):
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    src = tmp_path / "book.epub"
    src.write_text("x")

    monkeypatch.setattr(
        "layoutkeep.ui.job_setup.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(src), ""),
    )
    widget._browse_input()

    assert widget._input_path.text() == str(src)
    assert widget._output_path.text() == str(src.with_name("book.out.epub"))


# -- validation: a job that cannot succeed must never start a worker thread --------------


def test_start_with_no_input_file_is_refused(qtbot, monkeypatch):
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    widget._output_path.setText("out.epub")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    received: list[JobConfig] = []
    widget.job_ready.connect(received.append)
    widget._start_btn.click()

    assert not received


def test_start_with_nonexistent_input_file_is_refused(qtbot, tmp_path, monkeypatch):
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    widget._input_path.setText(str(tmp_path / "missing.epub"))
    widget._output_path.setText(str(tmp_path / "out.epub"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    received: list[JobConfig] = []
    widget.job_ready.connect(received.append)
    widget._start_btn.click()

    assert not received


def test_start_with_openai_provider_and_no_model_is_refused(qtbot, tmp_path, monkeypatch):
    """This is the GUI counterpart of cli.py's "--model is required for the openai provider" -
    the GUI must fail the same way instead of starting a job that cannot work."""
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    input_path = tmp_path / "book.epub"
    input_path.write_text("x")
    widget._input_path.setText(str(input_path))
    widget._output_path.setText(str(tmp_path / "out.epub"))
    widget._provider_config = ProviderConfig(kind="openai", base_url="http://x", model="")

    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a: warnings.append(a[-1]) or QMessageBox.StandardButton.Ok
    )

    received: list[JobConfig] = []
    widget.job_ready.connect(received.append)
    widget._start_btn.click()

    assert not received
    assert warnings and "model" in warnings[0].lower()


def test_start_with_openai_provider_and_model_succeeds(qtbot, tmp_path):
    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    input_path = tmp_path / "book.epub"
    input_path.write_text("x")
    widget._input_path.setText(str(input_path))
    widget._output_path.setText(str(tmp_path / "out.epub"))
    widget._provider_config = ProviderConfig(kind="openai", base_url="http://x", model="llama-3")

    received: list[JobConfig] = []
    widget.job_ready.connect(received.append)
    widget._start_btn.click()

    assert len(received) == 1
    assert received[0].provider.model == "llama-3"


def test_browsing_output_sets_and_persists_folder(qtbot, tmp_path, monkeypatch):

    settings = app_settings()
    settings.remove("output_folder")

    widget = JobSetupWidget()
    qtbot.addWidget(widget)

    src = tmp_path / "book.epub"
    src.write_text("x")
    widget._input_path.setText(str(src))

    chosen_dir = tmp_path / "my_outputs"
    chosen_dir.mkdir()

    monkeypatch.setattr(
        "layoutkeep.ui.job_setup.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(chosen_dir),
    )

    try:
        widget._browse_output()

        assert widget._settings.value("output_folder") == str(chosen_dir)
        assert widget._output_path.text() == str(chosen_dir / "book.out.epub")
    finally:
        settings.remove("output_folder")


def test_the_test_provider_is_out_of_the_list_unless_a_developer_asks(qtbot, monkeypatch):
    """It does not translate - it prefixes the source with a language tag - so a user who
    picks it sees what looks like a broken translation. Development runs still need it, so it
    comes back with the environment variable rather than disappearing altogether."""
    monkeypatch.delenv("LAYOUTKEEP_DEV_PROVIDERS", raising=False)
    plain = JobSetupWidget()
    qtbot.addWidget(plain)
    combo = plain._provider_profile_combo
    assert "fake" not in {p.kind for p in combo.profiles()}

    monkeypatch.setenv("LAYOUTKEEP_DEV_PROVIDERS", "1")
    dev = JobSetupWidget()
    qtbot.addWidget(dev)
    dev_combo = dev._provider_profile_combo
    assert "fake" in {p.kind for p in dev_combo.profiles()}


def test_fake_provider_selectable_from_profile_combo_in_gui(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("LAYOUTKEEP_DEV_PROVIDERS", "1")
    widget = JobSetupWidget()
    qtbot.addWidget(widget)

    src = tmp_path / "book.epub"
    src.write_text("dummy")
    widget._input_path.setText(str(src))
    widget._output_path.setText(str(tmp_path / "book.out.epub"))

    # Profil listesinde Fake / Test sağlayıcı bulunmalı ve seçilebilmeli
    combo = widget._provider_profile_combo
    fake = next((p for p in combo.profiles() if p.kind == "fake"), None)
    assert fake is not None, "Test / Sahte Çevirici profili listede bulunamadı!"

    # Önce başka bir uç noktaya, sonra test sağlayıcısına geçişi sına
    other = next(p for p in combo.profiles() if p.kind != "fake")
    combo.select_profile(other.name)
    combo.select_profile(fake.name)
    assert widget._provider_config.kind == "fake"

    # Çeviri başlatıldığında model uyarısı vermeden fake provider ile başlamalı
    received: list[JobConfig] = []
    widget.job_ready.connect(received.append)
    widget._start_btn.click()

    assert len(received) == 1
    assert received[0].provider.kind == "fake"

    # Test sonrası varsayılan aktif profile dön
    from layoutkeep.ui.provider_profile import ProviderProfileStore
    ProviderProfileStore().set_active_profile_name("LM Studio (1234)")




def test_deepl_profile_narrows_the_language_pickers(qtbot):
    """DeepL refuses anything outside its own list with an HTTP 400 that fails the whole job,
    so offering Persian beside French is offering a choice that cannot work."""
    from layoutkeep.providers.deepl import SUPPORTED_LANGUAGES

    widget = JobSetupWidget()
    qtbot.addWidget(widget)
    combo = widget._provider_profile_combo

    combo.select_profile(next(p.name for p in combo.profiles() if p.kind == "openai"))
    wide = {widget._target_lang.itemData(i) for i in range(widget._target_lang.count())}
    assert "fa" in wide, "a local model is not narrowed"

    combo.select_profile(next(p.name for p in combo.profiles() if p.kind == "deepl"))
    narrow = {widget._target_lang.itemData(i) for i in range(widget._target_lang.count())}

    assert narrow < wide
    assert narrow <= SUPPORTED_LANGUAGES
    assert "fa" not in narrow and "tr" in narrow and "en" in narrow
    # Auto-detect survives on the source side; DeepL detects when the field is omitted.
    assert widget._source_lang.itemData(0) == "auto"
