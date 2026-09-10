"""Tests for model catalog, vendor classification and model selector widget.

Model sınıflandırma, üretici gruplama ve model seçici bileşeni testleri.
"""

from __future__ import annotations

from layoutkeep.ui.model_catalog import (
    ALL_VENDORS,
    OTHER_VENDOR,
    ModelSelectorWidget,
    classify_vendor,
    group_and_filter_models,
)


def test_classify_vendor():
    # Üretici tespiti doğrulanır / Verifies vendor classification
    assert classify_vendor("meta-llama/Llama-3.2-3B-Instruct") == "Meta / Llama"
    assert classify_vendor("llama3.2:latest") == "Meta / Llama"
    assert classify_vendor("codellama:7b") == "Meta / Llama"

    assert classify_vendor("Qwen/Qwen2.5-7B-Instruct") == "Alibaba / Qwen"
    assert classify_vendor("qwen2.5-coder:14b") == "Alibaba / Qwen"
    assert classify_vendor("qwq:latest") == "Alibaba / Qwen"

    assert classify_vendor("deepseek-ai/DeepSeek-R1-Distill-Qwen-14B") == "DeepSeek"
    assert classify_vendor("deepseek-coder-v2:16b") == "DeepSeek"

    assert classify_vendor("mistralai/Mistral-7B-Instruct-v0.3") == "Mistral AI"
    assert classify_vendor("mixtral:8x7b") == "Mistral AI"
    assert classify_vendor("codestral:latest") == "Mistral AI"

    assert classify_vendor("google/gemma-2-9b-it") == "Google / Gemma"
    assert classify_vendor("gemma2:2b") == "Google / Gemma"

    assert classify_vendor("microsoft/Phi-3.5-mini-instruct") == "Microsoft / Phi"
    assert classify_vendor("phi3:mini") == "Microsoft / Phi"

    assert classify_vendor("gpt-4o-mini") == "OpenAI"
    assert classify_vendor("o1-preview") == "OpenAI"

    assert classify_vendor("claude-3-5-sonnet") == "Anthropic / Claude"
    assert classify_vendor("command-r:latest") == "Cohere"
    assert classify_vendor("unknown-custom-model-v1") == OTHER_VENDOR


def test_group_and_filter_models():
    # Model gruplama ve filtreleme test edilir / Tests grouping and filtering
    models = [
        "llama-3.2-1b",
        "llama-3.2-3b",
        "qwen2.5-7b",
        "deepseek-r1-14b",
        "my-special-model",
    ]

    # Filtresiz gruplama
    grouped = group_and_filter_models(models)
    assert "Meta / Llama" in grouped
    assert grouped["Meta / Llama"] == ["llama-3.2-1b", "llama-3.2-3b"]
    assert "Alibaba / Qwen" in grouped
    assert grouped["Alibaba / Qwen"] == ["qwen2.5-7b"]
    assert "DeepSeek" in grouped
    assert OTHER_VENDOR in grouped

    # Arama filtresi
    search_res = group_and_filter_models(models, search="llama")
    assert len(search_res) == 1
    assert "Meta / Llama" in search_res
    assert len(search_res["Meta / Llama"]) == 2

    # Üretici filtresi
    vendor_res = group_and_filter_models(models, vendor="DeepSeek")
    assert list(vendor_res.keys()) == ["DeepSeek"]
    assert vendor_res["DeepSeek"] == ["deepseek-r1-14b"]

    # Hem arama hem üretici
    both_res = group_and_filter_models(models, search="3b", vendor="Meta / Llama")
    assert both_res["Meta / Llama"] == ["llama-3.2-3b"]


def test_model_selector_widget_interaction(qtbot):
    # Model seçici arayüz bileşeninin etkileşimleri test edilir / Tests widget interactions
    widget = ModelSelectorWidget()
    qtbot.addWidget(widget)

    test_models = [
        "llama-3.2-1b",
        "llama-3.2-3b",
        "qwen2.5-7b",
        "deepseek-r1:14b",
        "custom-model-x",
    ]
    widget.set_models(test_models)
    assert widget.all_models() == test_models

    # Arama kutusuna metin yazma
    widget._search_input.setText("qwen")
    assert widget.currentText() == "qwen2.5-7b"

    # Üretici filtresi seçme
    widget._search_input.clear()
    idx_meta = widget._vendor_combo.findText("Meta / Llama")
    assert idx_meta >= 0
    widget._vendor_combo.setCurrentIndex(idx_meta)
    assert "llama" in widget.currentText()

    # Filtreyi temizleme
    widget._vendor_combo.setCurrentText(ALL_VENDORS)

    # Manuel model adı yazma (editable combo)
    widget.setEditText("my-custom-endpoint-model")
    assert widget.currentText() == "my-custom-endpoint-model"

    # addItem ve clear
    widget.clear()
    assert widget.all_models() == []
    assert widget.currentText() == ""

    widget.addItem("llama-3.1-8b")
    assert widget.currentText() == "llama-3.1-8b"
    assert "llama-3.1-8b" in widget.all_models()


def test_model_selector_widget_signals(qtbot):
    # Model seçimi sinyal yayılımı test edilir / Tests model change signal
    widget = ModelSelectorWidget()
    qtbot.addWidget(widget)

    received: list[str] = []
    widget.model_changed.connect(received.append)

    widget.addItem("model-alpha")
    assert "model-alpha" in received
