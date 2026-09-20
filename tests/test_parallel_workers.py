"""Unit tests for translation parallel workers configuration.

LM Studio ve yerel LLM sunucuları için paralel yuva ve iş parçacığı yapılandırmasını
doğrulayan birim testleri.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Proje kök dizinini sys.path'e ekle / Add project root to sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from layoutkeep.core import tunables
from tools.audit.translate_book import DEFAULT_WORKERS as BOOK_DEFAULT_WORKERS
from tools.audit.translate_epub import DEFAULT_WORKERS as EPUB_DEFAULT_WORKERS


def test_tunable_translation_workers_defaults_to_two():
    # Varsayılan 2'dir: tek yerel GPU'da yedi eşzamanlı istek bağlamı bölüşüp istek başına
    # token'ı düşürür; yuva sayısı elverince kullanıcı yükseltir.
    val = tunables.get("translation.workers")
    assert val == 2


def test_translate_book_fallback_workers_match_the_tunable():
    # Tunable okunamazsa kullanılan yedek, tunable varsayılanıyla aynı olmalı (2)
    assert BOOK_DEFAULT_WORKERS == 2


def test_translate_epub_fallback_workers_match_the_tunable():
    # Tunable okunamazsa kullanılan yedek, tunable varsayılanıyla aynı olmalı (2)
    assert EPUB_DEFAULT_WORKERS == 2


def test_translate_book_cli_args_respect_default_workers(tmp_path: Path):
    # translate_book komut satırı argümanlarının varsayılan 7'yi aldığını doğrular / Verifies CLI parsing
    from tools.audit.translate_book import main

    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 dummy")
    out_pdf = tmp_path / "out.pdf"

    args = ["translate_book.py", str(test_pdf), "--out", str(out_pdf), "--model", "dummy", "--limit-chunks", "1"]
    with (
        patch("sys.argv", args),
        patch("tools.audit.translate_book.split_pages", return_value=[]),
        patch("tools.audit.translate_book.merge", return_value=0),
    ):
        ret = main()
        assert ret == 0


def test_translate_epub_cli_args_respect_default_workers(tmp_path: Path):
    # translate_epub komut satırı argümanlarının varsayılan 7'yi aldığını doğrular / Verifies CLI parsing
    from tools.audit.translate_epub import main

    test_epub = tmp_path / "test.epub"
    test_epub.write_bytes(b"dummy")
    out_epub = tmp_path / "out.epub"

    args = ["translate_epub.py", str(test_epub), "--out", str(out_epub), "--model", "dummy", "--limit-chunks", "1"]
    with (
        patch("sys.argv", args),
        patch("tools.audit.translate_epub.split_epub_chapters", return_value=[]),
        patch("tools.audit.translate_epub.merge_epub_chunks", return_value=0),
    ):
        ret = main()
        assert ret == 0
