"""Tests for multiple provider profiles listing, selection, and persistence across app restarts."""

from __future__ import annotations

from layoutkeep.ui.job_setup import JobSetupWidget
from layoutkeep.ui.provider_profile import ProviderProfile, ProviderProfileStore


def test_provider_profile_store_crud():
    store = ProviderProfileStore()
    p1 = ProviderProfile(name="Ollama Yerel", base_url="http://localhost:11434/v1", model="qwen2.5")
    p2 = ProviderProfile(name="Uzak Sunucu", base_url="http://192.168.1.50:8000/v1", model="deepseek")

    store.upsert_profile(p1)
    store.upsert_profile(p2)

    profiles = store.list_profiles()
    names = [p.name for p in profiles]
    assert "Ollama Yerel" in names
    assert "Uzak Sunucu" in names

    assert store.get_active_profile_name() == "Uzak Sunucu"
    store.set_active_profile_name("Ollama Yerel")
    assert store.get_active_profile_name() == "Ollama Yerel"


def test_job_setup_profile_selection_and_persistence(qtbot):
    store = ProviderProfileStore()
    store.upsert_profile(
        ProviderProfile(name="Ozel Model 1", base_url="http://localhost:1234/v1", model="model-a")
    )
    store.upsert_profile(
        ProviderProfile(name="Ozel Model 2", base_url="http://localhost:1234/v1", model="model-b")
    )

    # 1. Oturum / Session 1
    widget1 = JobSetupWidget()
    qtbot.addWidget(widget1)

    widget1._provider_profile_combo.select_profile("Ozel Model 2")
    assert widget1._provider_config.model == "model-b"
    assert store.get_active_profile_name() == "Ozel Model 2"

    # 2. Oturum (uygulama yeniden açıldığında) / Session 2 after reopen
    widget2 = JobSetupWidget()
    qtbot.addWidget(widget2)
    assert widget2._provider_profile_combo.currentText() == "Ozel Model 2"
    assert widget2._provider_config.model == "model-b"
