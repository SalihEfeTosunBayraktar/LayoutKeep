"""Runtime-adjustable parameters.

Numbers that used to be module constants and could only be changed by editing the source and
restarting. Some of them are genuinely machine-dependent - how long a cold model takes to
load, how many segments an endpoint will accept - so the right value is not something this
project can pick once for everyone.

Two rules make this safe to have:

  * **Read at use, not at import.** A call site must call `get()` when it needs the value.
    Binding it to a module-level name again would restore exactly the restart-to-apply
    behaviour this replaces.
  * **The default stays the constant.** Every tunable's default is the value the code shipped
    with, so an untouched installation behaves identically and `reset_all()` is a real escape
    hatch.

Qt-free on purpose: the CLI reads the same overrides as the desktop app, so the two cannot
drift into behaving differently on the same machine.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Which screen a tunable belongs on. `ADVANCED` entries are ones where a wrong value produces
#: quietly worse output rather than an obvious error, so they carry a warning and live behind a
#: developer section.
BASIC = "basic"
ADVANCED = "advanced"


@dataclass(frozen=True, slots=True)
class Tunable:
    key: str
    label: str
    default: Any
    #: "int" | "float" | "bool"
    kind: str
    section: str = BASIC
    minimum: float | None = None
    maximum: float | None = None
    help_text: str = ""
    #: Shown next to advanced entries. Says what goes wrong, not merely "be careful". One or two
    #: sentences: a warning that runs to a paragraph stops being read.
    warning: str = ""
    #: The measurement behind the warning - the numbers, the documents, the tool that produced them.
    #: Shown under the warning in a muted style, so the evidence survives without the row becoming
    #: an essay. `tests/test_tunables_groups.py` keeps a warning short by pointing long ones here.
    evidence: str = ""
    #: Heading this entry sits under in the dialog. Entries sharing one are shown together;
    #: an empty group means "no heading", which is how the list read before there were enough
    #: entries to need any.
    group: str = ""
    #: For a setting with a fixed set of values: (value, label) pairs, shown as a dropdown.
    choices: tuple[tuple[str, str], ...] = ()


TUNABLES: tuple[Tunable, ...] = (
    # -- basic -------------------------------------------------------------
    Tunable(
        key="translation.memory",
        label="TUNABLE_translation.memory_label",
        default=True,
        kind="bool",
        group="TRANSLATION",
        help_text="TUNABLE_translation.memory_help_text",
        warning="TUNABLE_translation.memory_warning",
    ),
    Tunable(
        key="translation.glossary_path",
        label="TUNABLE_translation.glossary_path_label",
        default="",
        kind="str",
        group="TRANSLATION",
        help_text="TUNABLE_translation.glossary_path_help_text",
    ),
    Tunable(
        key="translation.reuse_repeats",
        group="TRANSLATION",
        label="TUNABLE_translation.reuse_repeats_label",
        default=True,
        kind="bool",
        help_text="TUNABLE_translation.reuse_repeats_help_text",
    ),
    Tunable(
        key="translation.piecewise_max_pieces",
        group="TRANSLATION",
        label="TUNABLE_translation.piecewise_max_pieces_label",
        default=12,
        kind="int",
        section=ADVANCED,
        minimum=0,
        maximum=40,
        help_text="TUNABLE_translation.piecewise_max_pieces_help_text",
        warning="TUNABLE_translation.piecewise_max_pieces_warning",
    ),
    Tunable(
        key="passthrough.min_words",
        label="TUNABLE_passthrough.min_words_label",
        default=4,
        kind="int",
        section=ADVANCED,
        group="TRANSLATION",
        minimum=1,
        maximum=50,
        help_text="TUNABLE_passthrough.min_words_help_text",
        warning="TUNABLE_passthrough.min_words_warning",
    ),
    Tunable(
        key="translation.protect_romans",
        label="TUNABLE_translation.protect_romans_label",
        default=True,
        kind="bool",
        section=ADVANCED,
        group="TRANSLATION",
        help_text="TUNABLE_translation.protect_romans_help_text",
        warning="TUNABLE_translation.protect_romans_warning",
    ),

    Tunable(
        key="translation.context_max_chars",
        label="TUNABLE_translation.context_max_chars_label",
        default=400,
        kind="int",
        section=ADVANCED,
        group="PROMPT",
        minimum=0,
        maximum=20000,
        help_text="TUNABLE_translation.context_max_chars_help_text",
        warning="TUNABLE_translation.context_max_chars_warning",
    ),
    Tunable(
        key="provider.system_prompt_file",
        label="TUNABLE_provider.system_prompt_file_label",
        default="",
        kind="str",
        section=BASIC,
        group="PROMPT",
        help_text="TUNABLE_provider.system_prompt_file_help_text",
        warning="TUNABLE_provider.system_prompt_file_warning",
    ),
    Tunable(
        key="provider.system_prompt_extra",
        label="TUNABLE_provider.system_prompt_extra_label",
        default="",
        kind="str",
        section=BASIC,
        group="PROMPT",
        help_text="TUNABLE_provider.system_prompt_extra_help_text",
        warning="TUNABLE_provider.system_prompt_extra_warning",
    ),
    Tunable(
        key="translation.keyword_map_path",
        label="TUNABLE_translation.keyword_map_path_label",
        default="",
        kind="str",
        section=ADVANCED,
        group="PROMPT",
        help_text="TUNABLE_translation.keyword_map_path_help_text",
        warning="TUNABLE_translation.keyword_map_path_warning",
    ),
    Tunable(
        key="translation.keyword_map_auto",
        label="TUNABLE_translation.keyword_map_auto_label",
        default=False,
        kind="bool",
        section=ADVANCED,
        group="PROMPT",
        help_text="TUNABLE_translation.keyword_map_auto_help_text",
        warning="TUNABLE_translation.keyword_map_auto_warning",
    ),
    Tunable(
        key="translation.auto_glossary",
        label="TUNABLE_translation.auto_glossary_label",
        default=False,
        kind="bool",
        section=ADVANCED,
        group="PROMPT",
        help_text="TUNABLE_translation.auto_glossary_help_text",
        warning="TUNABLE_translation.auto_glossary_warning",
    ),
    Tunable(
        key="translation.preserve_references",
        label="TUNABLE_translation.preserve_references_label",
        default=False,
        kind="bool",
        section=ADVANCED,
        group="PROMPT",
        help_text="TUNABLE_translation.preserve_references_help_text",
        warning="TUNABLE_translation.preserve_references_warning",
    ),
    Tunable(
        key="translation.prefit_budget",
        label="TUNABLE_translation.prefit_budget_label",
        default="",
        kind="str",
        section=ADVANCED,
        group="PROMPT",
        choices=(
            ("", "TUNABLE_translation.prefit_budget_choice_off"),
            ("loose", "TUNABLE_translation.prefit_budget_choice_loose"),
            ("strict", "TUNABLE_translation.prefit_budget_choice_strict"),
        ),
        help_text="TUNABLE_translation.prefit_budget_help_text",
        warning="TUNABLE_translation.prefit_budget_warning",
    ),
    Tunable(
        key="translation.document_preamble",
        label="TUNABLE_translation.document_preamble_label",
        default="",
        kind="str",
        section=BASIC,
        group="PROMPT",
        help_text="TUNABLE_translation.document_preamble_help_text",
        warning="TUNABLE_translation.document_preamble_warning",
    ),
    Tunable(
        key="translation.workers",
        group="PROVIDER",
        label="TUNABLE_translation.workers_label",
        default=2,
        kind="int",
        minimum=1,
        maximum=32,
        help_text="TUNABLE_translation.workers_help_text",
        warning="TUNABLE_translation.workers_warning",
    ),
    Tunable(
        key="batch.adaptive_start_segments",
        label="TUNABLE_batch.adaptive_start_segments_label",
        default=1,
        kind="int",
        section=ADVANCED,
        group="PROVIDER",
        minimum=1,
        maximum=20,
        help_text="TUNABLE_batch.adaptive_start_segments_help_text",
        warning="TUNABLE_batch.adaptive_start_segments_warning",
        evidence="TUNABLE_batch.adaptive_start_segments_evidence",
    ),
    Tunable(
        key="batch.chunk_size",
        group="PROVIDER",
        label="TUNABLE_batch.chunk_size_label",
        default=20,
        kind="int",
        minimum=1,
        maximum=200,
        help_text="TUNABLE_batch.chunk_size_help_text",
    ),
    Tunable(
        key="timeout.first_batch_s",
        group="PROVIDER",
        label="TUNABLE_timeout.first_batch_s_label",
        default=240.0,
        kind="float",
        minimum=10.0,
        maximum=3600.0,
        help_text="TUNABLE_timeout.first_batch_s_help_text",
    ),
    Tunable(
        key="timeout.warm_batch_s",
        group="PROVIDER",
        label="TUNABLE_timeout.warm_batch_s_label",
        default=15.0,
        kind="float",
        minimum=5.0,
        maximum=600.0,
        help_text="TUNABLE_timeout.warm_batch_s_help_text",
    ),
    Tunable(
        key="deepl.max_texts_per_request",
        group="PROVIDER",
        label="TUNABLE_deepl.max_texts_per_request_label",
        default=40,
        kind="int",
        minimum=1,
        maximum=50,
        help_text="TUNABLE_deepl.max_texts_per_request_help_text",
    ),
    # -- advanced ----------------------------------------------------------
    Tunable(
        key="batch.adaptive_max_segments",
        label="TUNABLE_batch.adaptive_max_segments_label",
        default=20,
        kind="int",
        section=ADVANCED,
        group="PROVIDER",
        minimum=1,
        maximum=100,
        help_text="TUNABLE_batch.adaptive_max_segments_help_text",
        warning="TUNABLE_batch.adaptive_max_segments_warning",
    ),
    Tunable(
        key="http.max_retry_after_s",
        label="TUNABLE_http.max_retry_after_s_label",
        default=60.0,
        kind="float",
        section=ADVANCED,
        group="PROVIDER",
        minimum=1.0,
        maximum=600.0,
        help_text="TUNABLE_http.max_retry_after_s_help_text",
        warning="TUNABLE_http.max_retry_after_s_warning",
    ),
    # -- ek test araçları ---------------------------------------------------
    # Kurulum ekranından buraya taşındı: her çeviride karşılaştırma sayfası üretmek isteyen
    # kullanıcı sayısı az, ama seçenek orada durup asıl kararları kalabalıklaştırıyordu.
    Tunable(
        key="reader.scan_text_density",
        label="TUNABLE_reader.scan_text_density_label",
        default=1.0,
        kind="float",
        section=ADVANCED,
        group="READING",
        minimum=0.0,
        maximum=50.0,
        help_text="TUNABLE_reader.scan_text_density_help_text",
        warning="TUNABLE_reader.scan_text_density_warning",
    ),
    Tunable(
        key="reader.scan_image_coverage",
        label="TUNABLE_reader.scan_image_coverage_label",
        default=0.05,
        kind="float",
        section=ADVANCED,
        group="READING",
        minimum=0.0,
        maximum=1.0,
        help_text="TUNABLE_reader.scan_image_coverage_help_text",
        warning="TUNABLE_reader.scan_image_coverage_warning",
    ),
    Tunable(
        key="reader.scan_image_coverage_layer",
        label="TUNABLE_reader.scan_image_coverage_layer_label",
        default=0.5,
        kind="float",
        section=ADVANCED,
        group="READING",
        minimum=0.0,
        maximum=1.0,
        help_text="TUNABLE_reader.scan_image_coverage_layer_help_text",
        warning="TUNABLE_reader.scan_image_coverage_layer_warning",
    ),
    Tunable(
        key="ocr.needs_review_threshold",
        label="TUNABLE_ocr.needs_review_threshold_label",
        default=0.80,
        kind="float",
        section=ADVANCED,
        group="READING",
        minimum=0.0,
        maximum=1.0,
        help_text="TUNABLE_ocr.needs_review_threshold_help_text",
        warning="TUNABLE_ocr.needs_review_threshold_warning",
    ),
    Tunable(
        key="table.cell_overlap_ratio",
        label="TUNABLE_table.cell_overlap_ratio_label",
        default=0.35,
        kind="float",
        section=ADVANCED,
        group="TABLES",
        minimum=0.05,
        maximum=0.95,
        help_text="TUNABLE_table.cell_overlap_ratio_help_text",
        warning="TUNABLE_table.cell_overlap_ratio_warning",
    ),
    Tunable(
        key="table.row_overlap_ratio",
        label="TUNABLE_table.row_overlap_ratio_label",
        default=0.6,
        kind="float",
        section=ADVANCED,
        group="TABLES",
        minimum=0.1,
        maximum=1.0,
        help_text="TUNABLE_table.row_overlap_ratio_help_text",
        warning="TUNABLE_table.row_overlap_ratio_warning",
    ),
    Tunable(
        key="table.column_align_ratio",
        label="TUNABLE_table.column_align_ratio_label",
        default=1.2,
        kind="float",
        section=ADVANCED,
        group="TABLES",
        minimum=0.2,
        maximum=5.0,
        help_text="TUNABLE_table.column_align_ratio_help_text",
        warning="TUNABLE_table.column_align_ratio_warning",
    ),
    Tunable(
        key="table.height_similarity",
        label="TUNABLE_table.height_similarity_label",
        default=1.6,
        kind="float",
        section=ADVANCED,
        group="TABLES",
        minimum=1.0,
        maximum=5.0,
        help_text="TUNABLE_table.height_similarity_help_text",
        warning="TUNABLE_table.height_similarity_warning",
    ),
    Tunable(
        key="merge.line_gap_ratio",
        label="TUNABLE_merge.line_gap_ratio_label",
        default=0.6,
        kind="float",
        section=ADVANCED,
        group="TABLES",
        minimum=0.0,
        maximum=3.0,
        help_text="TUNABLE_merge.line_gap_ratio_help_text",
        warning="TUNABLE_merge.line_gap_ratio_warning",
    ),
    Tunable(
        key="merge.line_height_ratio",
        label="TUNABLE_merge.line_height_ratio_label",
        default=1.2,
        kind="float",
        section=ADVANCED,
        group="TABLES",
        minimum=0.8,
        maximum=2.5,
        help_text="TUNABLE_merge.line_height_ratio_help_text",
        warning="TUNABLE_merge.line_height_ratio_warning",
    ),
    Tunable(
        key="merge.rotation_eps_deg",
        label="TUNABLE_merge.rotation_eps_deg_label",
        default=0.5,
        kind="float",
        section=ADVANCED,
        group="TABLES",
        minimum=0.0,
        maximum=10.0,
        help_text="TUNABLE_merge.rotation_eps_deg_help_text",
        warning="TUNABLE_merge.rotation_eps_deg_warning",
    ),
    Tunable(
        key="fit.shorten_below_scale",
        label="TUNABLE_fit.shorten_below_scale_label",
        default=0.95,
        kind="float",
        section=ADVANCED,
        group="FITTING",
        minimum=0.0,
        maximum=1.0,
        help_text="TUNABLE_fit.shorten_below_scale_help_text",
        warning="TUNABLE_fit.shorten_below_scale_warning",
    ),

    Tunable(
        key="fitting.reflow",
        label="TUNABLE_fitting.reflow_label",
        default=False,
        kind="bool",
        section=ADVANCED,
        group="FITTING",
        help_text="TUNABLE_fitting.reflow_help_text",
        warning="TUNABLE_fitting.reflow_warning",
        evidence="TUNABLE_fitting.reflow_evidence",
    ),
    Tunable(
        key="fit.min_scale",
        label="TUNABLE_fit.min_scale_label",
        default=0.85,
        kind="float",
        section=ADVANCED,
        group="FITTING",
        minimum=0.5,
        maximum=1.0,
        help_text="TUNABLE_fit.min_scale_help_text",
        warning="TUNABLE_fit.min_scale_warning",
    ),
    Tunable(
        key="writer.inline_span_sizes",
        label="TUNABLE_writer.inline_span_sizes_label",
        default=True,
        kind="bool",
        section=ADVANCED,
        group="FITTING",
        help_text="TUNABLE_writer.inline_span_sizes_help_text",
        warning="TUNABLE_writer.inline_span_sizes_warning",
        evidence="TUNABLE_writer.inline_span_sizes_evidence",
    ),
    Tunable(
        key="fitting.batched_requests",
        label="TUNABLE_fitting.batched_requests_label",
        default=True,
        kind="bool",
        section=ADVANCED,
        group="FITTING",
        help_text="TUNABLE_fitting.batched_requests_help_text",
        warning="TUNABLE_fitting.batched_requests_warning",
    ),
    Tunable(
        key="write.grant_room_pt",
        label="TUNABLE_write.grant_room_pt_label",
        default=24.0,
        kind="float",
        section=ADVANCED,
        group="FITTING",
        minimum=0.0,
        maximum=120.0,
        help_text="TUNABLE_write.grant_room_pt_help_text",
        warning="TUNABLE_write.grant_room_pt_warning",
    ),

    Tunable(
        key="write.grant_room_right_pt",
        label="Bloğun sağındaki boş alanı kullanma sınırı (punto)",
        default=60.0,
        kind="float",
        section=ADVANCED,
        group="FITTING",
        minimum=0.0,
        maximum=400.0,
        help_text=(
            "Okuyucu bir satırın kutusunu gliflerin bittiği yere kadar ölçer; bu yüzden başlık "
            "gibi kısa satırlar kendi genişliği kadardır. Çeviri daha uzun olduğunda satır, "
            "yanındaki boş kâğıda doğru bu kadar puntoya kadar uzayabilir - yani ikinci satıra "
            "kaymak ya da küçültülmek yerine tek satır kalır. Sınır sayfanın kendi içeriğine "
            "göre ölçülür (sayfadaki en sağdaki bloğun bittiği yer); 0 kapatır."
        ),
        evidence=(
            "Ölçüm (kayıtlı koşular, model yok): sınır 0/12/24/36/48/60/200 iken "
            "tr_tck_5237 D1 = 12/9/8/8/7/7/7, arxiv_19145 D1 = 17/9/8/8/8/8/8. Kazanç 48 "
            "puntoda doyuyor, 60 biraz pay bırakıyor. L3/L4/L7/L8/L10 hiçbir sınırda artmadı."
        ),
        warning=(
            "0 yapmak eski davranışa döner: satırı kutusundan uzun olan çeviri ya ikinci satıra "
            "kayar (kutu tek satırlıksa sığmaz) ya da taban puntoya kadar küçültülüp "
            "işaretlenir. Komşusu olan satırlar etkilenmez; sınır yalnız boş kâğıda doğru "
            "büyümeye izin verir."
        ),
    ),

    Tunable(
        key="write.box_slack_pt",
        label="TUNABLE_write.box_slack_pt_label",
        default=3.0,
        kind="float",
        section=ADVANCED,
        group="FITTING",
        minimum=0.0,
        maximum=12.0,
        help_text="TUNABLE_write.box_slack_pt_help_text",
        warning="TUNABLE_write.box_slack_pt_warning",
    ),
    Tunable(
        key="redact.coverage_ratio",
        label="TUNABLE_redact.coverage_ratio_label",
        default=0.6,
        kind="float",
        section=ADVANCED,
        group="FITTING",
        minimum=0.1,
        maximum=1.0,
        help_text="TUNABLE_redact.coverage_ratio_help_text",
        warning="TUNABLE_redact.coverage_ratio_warning",
    ),
    Tunable(
        key="ui.floating_progress",
        label="TUNABLE_ui.floating_progress_label",
        default=True,
        kind="bool",
        group="INTERFACE",
        help_text="TUNABLE_ui.floating_progress_help_text",
    ),
    Tunable(
        key="preview.keep_segments",
        group="INTERFACE",
        label="TUNABLE_preview.keep_segments_label",
        default=40,
        kind="int",
        minimum=5,
        maximum=500,
        help_text="TUNABLE_preview.keep_segments_help_text",
    ),
    Tunable(
        key="output.dual_mode",
        label="TUNABLE_output.dual_mode_label",
        default="",
        kind="str",
        section=ADVANCED,
        group="TEST_TOOLS",
        choices=(
            ("", "TUNABLE_output.dual_mode_choice_off"),
            ("side", "Yan yana (kaynak solda)"),
            ("alternate", "TUNABLE_output.dual_mode_choice_alternate"),
        ),
        help_text="TUNABLE_output.dual_mode_help_text",
        warning="TUNABLE_output.dual_mode_warning",
    ),
    Tunable(
        key="output.timing_report",
        label="TUNABLE_output.timing_report_label",
        default=False,
        kind="bool",
        section=ADVANCED,
        group="TEST_TOOLS",
        help_text="TUNABLE_output.timing_report_help_text",
        warning="TUNABLE_output.timing_report_warning",
    ),
)

_BY_KEY: dict[str, Tunable] = {t.key: t for t in TUNABLES}

#: Values differing from the defaults. Empty for a fresh installation.
_overrides: dict[str, Any] = {}

#: Where overrides are stored. Environment variable first so a test run, a CI job or a
#: portable build can point it somewhere harmless.
_ENV_PATH = "LAYOUTKEEP_TUNABLES"


def definitions(section: str | None = None) -> list[Tunable]:
    if section is None:
        return list(TUNABLES)
    return [t for t in TUNABLES if t.section == section]


def definition(key: str) -> Tunable:
    return _BY_KEY[key]


def get(key: str) -> Any:
    """The value in force, override first. Call this where the value is used."""
    if key in _overrides:
        return _overrides[key]
    return _BY_KEY[key].default


def _coerce(spec: Tunable, value: Any) -> Any:
    if spec.kind == "bool":
        return bool(value)
    if spec.kind == "str":
        # A path is stored as typed (trimmed), never parsed as a number: the settings dialog
        # writes every editor's value through here, and an empty path means "no glossary".
        return str(value or "").strip()
    number = float(value)
    if spec.minimum is not None:
        number = max(spec.minimum, number)
    if spec.maximum is not None:
        number = min(spec.maximum, number)
    return round(number) if spec.kind == "int" else number


def set_value(key: str, value: Any) -> Any:
    """Override a tunable, clamped to its range. Returns the value actually stored.

    Clamping rather than raising is deliberate: this is fed by a settings dialog, and a value
    outside the range means the user wanted the extreme, not that the program should stop.
    """
    spec = _BY_KEY[key]
    coerced = _coerce(spec, value)
    if coerced == spec.default:
        _overrides.pop(key, None)
    else:
        _overrides[key] = coerced
    return coerced


def reset(key: str) -> None:
    _overrides.pop(key, None)


def reset_all() -> None:
    _overrides.clear()


def overrides() -> dict[str, Any]:
    return dict(_overrides)


def is_overridden(key: str) -> bool:
    return key in _overrides


def storage_path() -> Path:
    from_env = os.environ.get(_ENV_PATH)
    if from_env:
        return Path(from_env)
    from layoutkeep.core.paths import data_dir

    return data_dir() / "tunables.json"


def load(path: str | Path | None = None) -> None:
    """Read stored overrides. A missing or unreadable file leaves the defaults in place."""
    target = Path(path) if path else storage_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        if key in _BY_KEY:
            try:
                set_value(key, value)
            except (TypeError, ValueError):
                # A stored value that no longer makes sense for this build is dropped rather
                # than taking the whole settings file down with it.
                continue


def save(path: str | Path | None = None) -> Path:
    target = Path(path) if path else storage_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_overrides, indent=2, sort_keys=True), encoding="utf-8")
    return target
