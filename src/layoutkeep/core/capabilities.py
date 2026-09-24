"""Which conversions are open, which are locked, and why.

One place decides this, because the interface, the command line and the documentation drifting
apart on the question is worse than any answer they could give. `docs/ENGINE-ARCHITECTURE.md`
holds the measurements this is based on, `tools/audit/format_matrix.py` reproduces them against
small synthetic fixtures, and `tools/audit/faz2_candidates.py` reproduces them against the richer
fixtures (`tests/fixtures/rich_report.*`, `rich_book.epub`) that phase 1 built specifically
because the synthetic ones had already hidden two silent styling losses and an OCR regression.

A pair is opened only once a run against the rich fixtures shows zero missing words against the
source - not a ratio close to 100%, an actual word-for-word diff with nothing on the "missing"
side. `->epub` targets add a small, correctly-localized chapter heading per page, and `docx`'s
image-bearing targets can add a page once the image is actually drawn instead of silently
dropped - both are why some word and page counts run slightly ahead of the source rather than
behind it. Additions, not losses.

Qt-free on purpose: the CLI applies the same policy.
"""

from __future__ import annotations

#: Every target the interface offers. "auto" means "the source's own format".
ALL_TARGETS = ("auto", ".pdf", ".html", ".epub", ".docx", ".png", ".jpg")

#: Source formats a reader exists for.
ALL_SOURCES = (".pdf", ".epub", ".docx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".webp",
               ".bmp", ".tiff", ".lkproj")

#: The conversions that hold up. Measured, not assumed - see the module docstring.
OPEN_PAIRS: frozenset[tuple[str, str]] = frozenset({
    (".pdf", ".pdf"),
    (".pdf", ".docx"),
    (".pdf", ".epub"),
    (".pdf", ".html"),
    (".epub", ".epub"),
    (".epub", ".docx"),
    (".epub", ".html"),
    (".epub", ".png"),
    (".docx", ".docx"),
    (".docx", ".epub"),
    (".docx", ".html"),
    (".docx", ".png"),
    (".docx", ".pdf"),
    (".png", ".docx"),
    (".lkproj", ".lkproj"),
    (".lkproj", ".epub"),
    (".lkproj", ".pdf"),
    (".lkproj", ".docx"),
    (".lkproj", ".html"),
})

#: Why each locked target is locked, in one sentence a person can act on. Keyed by target
#: extension; the interface shows it on the locked row and nowhere else.
LOCK_REASONS: dict[str, str] = {
    ".epub": "EPUB_LOCK_REASON",
    ".html": "HTML_LOCK_REASON",
    ".png": "IMAGE_LOCK_REASON",
    ".jpg": "IMAGE_LOCK_REASON",
}


def resolve_target(source_suffix: str, target: str) -> str:
    """The real target extension, with "auto" resolved against the source."""
    return source_suffix.lower() if target == "auto" else target.lower()


def is_open(source_suffix: str, target: str) -> bool:
    """Whether this conversion is enabled in this build."""
    source = source_suffix.lower()
    return (source, resolve_target(source, target)) in OPEN_PAIRS


def open_targets(source_suffix: str) -> tuple[str, ...]:
    """Targets that are open for this source, "auto" included where it resolves to one."""
    source = source_suffix.lower()
    return tuple(t for t in ALL_TARGETS if is_open(source, t))


def lock_reason_key(target: str) -> str:
    """The UI string key explaining why a target is locked, or "" if it is not locked."""
    return LOCK_REASONS.get(target.lower(), "")


#: Language pairs measured on the fixed bench (`tools/audit/bench.py`, 21 sources x 3 pages) with
#: every bar above 90: quality (MQM judge, mean), term consistency and layout (blocks drawn intact),
#: in percent, and the version the measurement belongs to. Every other pair translates, unmeasured.
MEASURED_LANGUAGE_PAIRS: dict[tuple[str, str], dict[str, str]] = {
    ("en", "tr"): {"version": "0.9.11", "quality": "94.4", "consistency": "91.3", "layout": "93.0"},
    ("tr", "en"): {"version": "0.9.11", "quality": "96.1", "consistency": "90.5", "layout": "90.4"},
}


def language_pair_measurement(source: str, target: str) -> tuple[tuple[str, str], dict[str, str]] | None:
    """The measured pair this job runs as, with its numbers; None when it has not been measured.

    An auto-detected source counts as the measured pair's source when the target is one of them:
    the document is then most likely in the other language, and saying "unmeasured" would be wrong
    far more often than right.
    """
    source, target = source.lower(), target.lower()
    if source == "auto":
        pairs = [pair for pair in MEASURED_LANGUAGE_PAIRS if pair[1] == target]
        return (pairs[0], MEASURED_LANGUAGE_PAIRS[pairs[0]]) if len(pairs) == 1 else None
    pair = (source, target)
    return (pair, MEASURED_LANGUAGE_PAIRS[pair]) if pair in MEASURED_LANGUAGE_PAIRS else None
