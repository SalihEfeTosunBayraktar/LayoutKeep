"""Which conversions are open, which are locked, and why.

One place decides this, because the interface, the command line and the documentation drifting
apart on the question is worse than any answer they could give. `docs/ENGINE-ARCHITECTURE.md`
holds the measurements this is based on and `tools/audit/format_matrix.py` reproduces them.

The short version of those measurements: every conversion that keeps a document in its own
format edits the original file and keeps everything. Every conversion that changes format builds
a new file from DocIR, and the builders are thin - the EPUB one writes no bold or italic at all,
the PDF one drops images that DocIR is holding. None of them fail; they return a document that is
quietly missing things, which is worse.

So the cross-format conversions are locked rather than removed. Removing them would say the
project does not do this; leaving them open says it does it well. Neither is true yet.

Qt-free on purpose: the CLI applies the same policy.
"""

from __future__ import annotations

#: Every target the interface offers. "auto" means "the source's own format".
ALL_TARGETS = ("auto", ".pdf", ".html", ".epub", ".docx", ".png", ".jpg")

#: Source formats a reader exists for.
ALL_SOURCES = (".pdf", ".epub", ".docx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".webp",
               ".bmp", ".tiff", ".lkproj")

#: The conversions that hold up. Measured, not assumed - see the module docstring.
OPEN_PAIRS: frozenset[tuple[str, str]] = frozenset({(".pdf", ".pdf")})

#: Why each locked target is locked, in one sentence a person can act on. Keyed by target
#: extension; the interface shows it on the locked row and nowhere else.
LOCK_REASONS: dict[str, str] = {
    ".epub": "EPUB_LOCK_REASON",
    ".docx": "DOCX_LOCK_REASON",
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
