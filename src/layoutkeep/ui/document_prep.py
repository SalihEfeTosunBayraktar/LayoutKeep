"""Everything that happens to a document before the translation loop starts.

Split out of TranslationWorker, which has a line budget of its own (D-017): the references pass,
the automatic glossary, the topic map, the page range and the character budgets were the bulk of
its `_run`, and they all have the same shape - read a setting, touch the document or the config,
report one status line. They live here in the order the loop needs them.

The worker keeps the Qt half: this class holds no signals and emits nothing, it reports through a
callback. It is handed the function that builds the provider chain rather than importing it, so a
test that patches `layoutkeep.ui.worker._build_provider` still sees its own chain in here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from layoutkeep.core import tunables
from layoutkeep.core.docir import Document, Segment, segments_from_document
from layoutkeep.core.timing import PhaseTimer
from layoutkeep.ui.doc_glossary import DocGlossaryBuilder
from layoutkeep.ui.job import JobConfig
from layoutkeep.ui.topic_map import TopicMapBuilder

__all__ = ["DocumentPreparer", "PreparedDocument"]


@dataclass(frozen=True)
class PreparedDocument:
    """What the loop needs from the preparation: the chain, the glossary and the segments.

    `config` is the run's config, not the one handed in: the automatic glossary writes its merged
    list to a file and points `glossary_path` at it, and the fitting pass and the write-back both
    read the terms from there. A worker that kept its own copy would translate with the merged
    terms and then ask for shortenings without them.
    """

    config: JobConfig
    provider: object
    memory: object
    glossary: dict[str, str] | None
    segments: list[Segment]
    total: int
    total_chars: int


class DocumentPreparer:
    """Turns a read document into what `_run_translation_loop` is handed.

    Reference tagging, the automatic glossary, the topic map, the page range and the character
    budgets, in one pass and in that order - each of them is a setting that changes what the
    segments look like, so the segments are built last. A run with the range holding no text
    comes back as None; which signal says so is the worker's business, not this class's.
    """

    def __init__(
        self,
        *,
        on_status: Callable[[str], None],
        build_provider: Callable[[JobConfig], tuple[object, object | None, dict[str, str] | None]],
    ) -> None:
        self._on_status = on_status
        self._build_provider = build_provider
        #: The value the topic map borrowed from the setting, put back once the segments have read
        #: the map. Held here so the worker keeps no topic-map state of its own.
        self._keyword_map_previous: str | None = None

    def prepare(
        self,
        doc: Document,
        src: Path,
        out: Path,
        config: JobConfig,
        *,
        phases: PhaseTimer,
        layout_model: bool = False,
    ) -> PreparedDocument | None:
        """Returns the run's segments and chain, or None when the range holds no text."""
        self._preserve_references(doc)
        provider, memory, glossary = self._build_provider(config)

        # Belge sözlüğü (ayar açıksa) bölümlemeden ÖNCE gelir (D-007): terim listesi bu koşunun her
        # isteğine, sığdırmasına ve bellek anahtarına girer; zincir sözlük yazıldıktan SONRA kurulur.
        if bool(tunables.get("translation.auto_glossary")):
            with phases.phase("glossary", "before the translation"):
                config, merged = DocGlossaryBuilder(on_status=self._on_status).build(
                    doc, out, provider, config
                )
                if merged:
                    glossary = merged
                    provider, memory, _ = self._build_provider(config)

        # Konu haritası (ayar açıksa) bölümlemeden ÖNCE gelir: segmentler kurulurken her blok kendi
        # anahtar kelimesini haritadan okur, yani dosya o an yerinde olmalı.
        if bool(tunables.get("translation.keyword_map_auto")):
            with phases.phase("keyword map", "before the translation"):
                self._build_topic_map(doc, out, provider)

        # Ne çevrildi, neyle: sözlük ve sağlayıcı zinciri kesinleştikten, herhangi bir yazımdan
        # önce kaydedilir (core/provenance.py); kayıt projeye ve çıktı dosyasına birlikte gider.
        self._record_provenance(doc, config, glossary_terms=glossary, memory=memory is not None,
                                 layout_model=layout_model)

        with phases.phase("segment", "segments in range"):
            segments = self._segments_in_range(doc, config)
        # The map is only needed while the segments are built; put the user's own value back so a
        # run cannot leave their settings changed.
        self._restore_topic_map_setting()
        if not segments:
            return None

        total = len(segments)
        self._fill_character_budgets(doc, src, config, phases, segments=segments, total=total)
        return PreparedDocument(
            config=config,
            provider=provider,
            memory=memory,
            glossary=glossary,
            segments=segments,
            total=total,
            total_chars=sum(len(segment.source) for segment in segments),
        )

    def _record_provenance(
        self,
        doc: Document,
        config: JobConfig,
        *,
        glossary_terms: dict[str, str] | None,
        memory: bool,
        layout_model: bool,
    ) -> None:
        """What this run is: written into the project and into the output (`core/provenance.py`).

        The command line builds its record from its own options (`cli.cmd_translate`); both call
        the same helper, so a document translated in the window and one translated on the command
        line with the same settings say the same thing about themselves.
        """
        from layoutkeep.core import provenance

        provenance.record(
            doc,
            provider_kind=config.provider.kind,
            model=config.provider.model,
            base_url=config.provider.base_url,
            source_lang=config.source_lang,
            target_lang=config.target_lang,
            reader=provenance.reader_path(doc, layout_model=layout_model),
            fit_mode=provenance.fit_mode_name(),
            glossary=glossary_terms,
            memory=memory,
        )

    def _preserve_references(self, doc: Document) -> None:
        # Kaynakça koruması (ayar açıksa) bölümlemeden ÖNCE gelir: işaretlenen blok çevrilebilir
        # sayılmaz, yani modele hiç gitmez. Aynı ayarı komut satırı da okur.
        if not tunables.get("translation.preserve_references"):
            return
        from layoutkeep.core.reference import tag_bibliography_blocks

        tagged = tag_bibliography_blocks(doc, preserve=True)
        if tagged:
            self._on_status(f"references: {tagged} bibliography blocks preserved untouched")

    def _build_topic_map(self, doc: Document, out: Path, provider) -> None:
        """Delegate to TopicMapBuilder, keeping the setting it borrowed so it can be put back.

        The map's own path is not kept: the worker assigned it and read it nowhere, and the builder
        returns the previous setting for the one thing that does need putting back.
        """
        _, previous = TopicMapBuilder(on_status=self._on_status).build(doc, out, provider)
        self._keyword_map_previous = previous

    def _restore_topic_map_setting(self) -> None:
        """Give the user's own 'Konu haritası dosyası' value back, after the segments read the map."""
        if self._keyword_map_previous is None:
            return
        tunables.set_value("translation.keyword_map_path", self._keyword_map_previous)
        self._keyword_map_previous = None

    def _segments_in_range(self, doc: Document, config: JobConfig) -> list[Segment]:
        # Belgeden segmentleri çıkarır ve aralığa göre filtreler / Extracts and filters segments
        segments = segments_from_document(doc)
        if config.page_range and doc.pages:
            from layoutkeep.core.range_helper import block_ids_for_pages, parse_page_range

            selected_pages = parse_page_range(config.page_range, len(doc.pages))
            allowed = block_ids_for_pages(doc, selected_pages)
            segments = [seg for seg in segments if seg.block_id in allowed]
        return segments

    def _fill_character_budgets(
        self,
        doc: Document,
        src: Path,
        config: JobConfig,
        phases: PhaseTimer,
        *,
        segments: list[Segment],
        total: int,
    ) -> None:
        # Karakter bütçesi çeviriden ÖNCE (D-011): modele ilk istekte 'max_len' olarak gider, yani
        # sığdırmanın tek tek düzeltmesi baştan azalır. PDF yoksa anlamsız - kutu geometrisi yok.
        prefit = str(tunables.get("translation.prefit_budget") or "")
        if src.suffix.lower() != ".pdf" or not prefit:
            return
        from layoutkeep.fitting.pdf_pass import budget_segments

        with phases.phase("budget", "per box"):
            filled = budget_segments(
                doc,
                segments,
                target_lang=config.target_lang,
                headroom=1.2 if prefit == "loose" else 1.0,
            )
        self._on_status(f"character budgets: {filled} of {total} boxes ({prefit})")
