"""Tests for persistence of language and output format preferences across sessions."""

from __future__ import annotations

from layoutkeep.ui.job_setup import JobSetupWidget
from layoutkeep.ui.settings import app_settings


def test_language_and_format_persistence(qtbot):
    # 1. Oturum: Kullanıcı dil ayarlarını seçer
    widget1 = JobSetupWidget()
    qtbot.addWidget(widget1)

    widget1._source_lang.setCurrentText("de")
    widget1._target_lang.setCurrentText("es")

    # 2. Oturum: Uygulama yeniden başlatıldığında aynı dil ayarları yüklenmeli
    widget2 = JobSetupWidget()
    qtbot.addWidget(widget2)

    assert widget2._source_lang.currentText() == "de"
    assert widget2._target_lang.currentText() == "es"

    # Test sonrası varsayılana döndür / Cleanup after test
    settings = app_settings()
    settings.setValue("source_lang", "auto")
    settings.setValue("target_lang", "tr")


def test_output_folder_persistence(qtbot, tmp_path):

    settings = app_settings()
    settings.remove("output_folder")

    custom_dir = tmp_path / "custom_outputs"
    custom_dir.mkdir()

    try:
        # 1. Oturum: Çıktı klasörü seçilir ve kaydedilir
        widget1 = JobSetupWidget()
        qtbot.addWidget(widget1)
        widget1._settings.setValue("output_folder", str(custom_dir))

        # Girdi dosyası eklendiğinde çıktı dosyası bu klasör altına yerleşmeli
        input_file = tmp_path / "article.pdf"
        input_file.write_text("dummy")
        widget1._input_path.setText(str(input_file))
        widget1._update_output_path(str(input_file))

        assert str(custom_dir) in widget1._output_path.text()
        assert widget1._output_path.text() == str(custom_dir / "article.out.pdf")

        # 2. Oturum: Yeniden açıldığında aynı klasör varsayılan olmalı
        widget2 = JobSetupWidget()
        qtbot.addWidget(widget2)

        input_file2 = tmp_path / "chapter2.epub"
        input_file2.write_text("dummy")
        widget2._update_output_path(str(input_file2))

        assert widget2._output_path.text() == str(custom_dir / "chapter2.out.epub")
    finally:
        settings.remove("output_folder")

