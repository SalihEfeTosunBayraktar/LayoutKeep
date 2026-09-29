"""Unit tests for EPUB chapter chunking and reassembly.

EPUB bölümlerini parçalara ayırma ve çeviri sonrası birleştirme mantığını doğrulayan birim testleri.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

# Proje kök dizinini sys.path'e ekle / Add project root to sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fixtures.build_epub_fixture import build_sample_epub

from layoutkeep.core.docir import load_project
from tools.audit.translate_epub import merge_epub_chunks, split_epub_chapters


def test_split_epub_chapters_creates_valid_lkproj(tmp_path: Path):
    # EPUB bölümlerinin geçerli .lkproj dosyalarına parçalandığını doğrular / Verifies chunking into .lkproj
    src_epub = tmp_path / "sample.epub"
    build_sample_epub(src_epub)

    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    chunks = split_epub_chapters(src_epub, work_dir, chapters_per_chunk=1)
    # sample.epub 2 bölüm (chap1, chap2) içerir / sample.epub has 2 chapters
    assert len(chunks) == 2
    for _index, path in chunks:
        assert path.exists()
        chunk_doc = load_project(path)
        assert len(chunk_doc.pages) == 1
        assert chunk_doc.source_format == "epub"


def test_merge_epub_chunks_creates_output_epub(tmp_path: Path):
    # Çevrilen parçaların eksiksiz bir EPUB dosyasına birleştirildiğini doğrular / Verifies merging into single EPUB
    src_epub = tmp_path / "sample.epub"
    build_sample_epub(src_epub)

    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    chunks = split_epub_chapters(src_epub, work_dir, chapters_per_chunk=1)
    out_paths = [p for _, p in chunks]

    out_epub = tmp_path / "merged.epub"
    merged_count = merge_epub_chunks(out_paths, src_epub, out_epub)

    assert merged_count == 2
    assert out_epub.exists()
    assert out_epub.with_suffix(".lkproj").exists()

    # Birleştirilen EPUB geçerli bir zip olmalı ve bölümleri içermeli / Merged file must be a valid zip
    with zipfile.ZipFile(out_epub) as zf:
        namelist = zf.namelist()
        assert "OEBPS/content.opf" in namelist
        assert "OEBPS/chap1.xhtml" in namelist
        assert "OEBPS/chap2.xhtml" in namelist
