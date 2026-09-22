"""What produced a translated document: version, provider, endpoint, settings, reader path.

WHY THIS EXISTS: an output file does not say what made it. Two runs of the same source - another
build, another model, a glossary, a reader with the layout model - are indistinguishable
afterwards, so a comparison cannot be trusted and a result cannot be reproduced. The question
"which version, with what, and with which methods was this translated?" has to be answerable from
the file itself.

The record built here is kept on the document, which is what the writers and `save_project` see:
one place to build it, one thing for every output of the run to carry. Both front-ends call the
same helper, so the command line and the window cannot answer differently.

Three rules:

  * **A fact, not a guess.** Every field is something this run really had. A provider with no
    endpoint of its own records none, rather than the URL that happened to sit in the form.
  * **No credentials.** The endpoint is stored with its userinfo and its key-like query parameters
    removed: this record travels inside a document that gets sent on.
  * **Never fail.** A packaged build has no checkout above it and a frozen executable has no
    `.git`; both are ordinary, so the commit is simply absent.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from layoutkeep import __version__
from layoutkeep.core import tunables
from layoutkeep.core.docir import Document

#: The embedded file the whole record travels under, in every format that can carry one.
FILE_NAME = "layoutkeep-provenance.json"

#: Query parameters whose value is a credential rather than a setting.
_SECRET_PARAM = re.compile(r"key|token|secret|password|passwd|pwd|auth|sig", re.IGNORECASE)

_SHA = re.compile(r"[0-9a-f]{40}")


# --------------------------------------------------------------------------------------
# The build
# --------------------------------------------------------------------------------------


def app_version() -> str:
    """The build's own version - the one `layoutkeep/__init__.py` declares and the UI shows."""
    return __version__


def git_commit() -> str | None:
    """The commit this code was built from, or None when there is no checkout to read.

    Read from `.git` rather than by running git: this is called at the end of a translation run,
    where a missing executable or an unreadable directory must not be able to fail the job. A
    linked worktree keeps its HEAD in the worktree's own git directory and its refs in the common
    one, so both are consulted.
    """
    try:
        found = _git_dirs(Path(__file__).resolve().parent)
        if found is None:
            return None
        git_dir, common_dir = found
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
        if _SHA.fullmatch(head):
            return head  # a detached HEAD states the commit itself
        if not head.startswith("ref:"):
            return None
        return _read_ref(git_dir, common_dir, head.split(":", 1)[1].strip())
    except (OSError, ValueError):
        # A packaged build unpacks into a directory with no repository above it, and a repository
        # can be unreadable. Neither is a reason to fail a run.
        return None


def _git_dirs(start: Path) -> tuple[Path, Path] | None:
    """(git directory, common directory) of the checkout containing `start`, or None."""
    for parent in (start, *start.parents):
        marker = parent / ".git"
        if marker.is_dir():
            return marker, _common_dir(marker)
        if marker.is_file():
            # A linked worktree: `.git` is a file holding "gitdir: <path>".
            text = marker.read_text(encoding="utf-8", errors="replace").strip()
            if not text.startswith("gitdir:"):
                return None
            target = Path(text.split(":", 1)[1].strip())
            if not target.is_absolute():
                target = (parent / target).resolve()
            return (target, _common_dir(target)) if target.is_dir() else None
    return None


def _common_dir(git_dir: Path) -> Path:
    """Where a worktree's shared refs and packed-refs live - itself, for an ordinary checkout."""
    pointer = git_dir / "commondir"
    if not pointer.is_file():
        return git_dir
    target = Path(pointer.read_text(encoding="utf-8", errors="replace").strip())
    return target if target.is_absolute() else (git_dir / target).resolve()


def _read_ref(git_dir: Path, common_dir: Path, ref: str) -> str | None:
    """The commit `ref` points at: the loose file when there is one, otherwise the packed refs."""
    for base in (git_dir, common_dir):
        loose = base / ref
        if loose.is_file():
            commit = loose.read_text(encoding="utf-8", errors="replace").strip()
            return commit if _SHA.fullmatch(commit) else None
        packed = base / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
                # "<sha> <ref>"; "^<sha>" lines peel a tag and are not a ref of their own.
                if line.startswith(("#", "^")):
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref and _SHA.fullmatch(parts[0]):
                    return parts[0]
    return None


# --------------------------------------------------------------------------------------
# What the run talked to
# --------------------------------------------------------------------------------------


def sanitize_endpoint(url: str) -> str:
    """`url` with its credentials removed - userinfo and key-like query parameters.

    A key is often pasted into the URL rather than into the key field, and the endpoint is
    recorded both in the output document and in the project file. The record of how a document was
    translated must not be the thing that leaks the key.
    """
    if "://" not in url:
        # Nothing this can take apart (a bare host, a path): left as it was rather than mangled
        # into a URL that was never used.
        return url
    parts = urlsplit(url)
    query = "&".join(
        pair
        for pair in parts.query.split("&")
        if pair and not _SECRET_PARAM.search(pair.split("=", 1)[0])
    )
    return urlunsplit((parts.scheme, parts.netloc.rpartition("@")[2], parts.path, query, ""))


def endpoint_for(provider_kind: str, base_url: str = "") -> str:
    """The endpoint this run talked to, or "" for a provider that has none of its own.

    The test provider and DeepL do not use the URL the form holds, so recording it would describe
    a request that never happened.
    """
    return sanitize_endpoint(base_url) if provider_kind == "openai" else ""


def model_for(provider_kind: str, model: str = "") -> str:
    """The model identity for the record.

    DeepL and the test provider translate without a model name - their identity is the provider -
    so the name left in the form would be the model of some other run.
    """
    return model if provider_kind == "openai" else provider_kind


# --------------------------------------------------------------------------------------
# How it was done
# --------------------------------------------------------------------------------------


def reader_path(
    doc: Document, *, layout_model: bool = False, layout_classifier: bool = False
) -> str:
    """How the pages were read: digital text or OCR, plus the models that helped.

    Read off the document rather than off the flags that were passed. Whether a page needed OCR is
    the reader's own decision (a text-less page is not always scanned), and that decision is the
    thing worth recording.
    """
    parts = ["ocr" if any(page.scanned for page in doc.pages) else "digital"]
    if layout_model:
        parts.append("layout")
    if layout_classifier:
        parts.append("vlm")
    return "+".join(parts)


def fit_mode_name() -> str:
    """The fitting mode in force - the one setting both front-ends read (`cli.fit_mode_from`)."""
    return "reflow" if tunables.get("fitting.reflow") else "strict"


# --------------------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------------------


def collect(
    *,
    provider_kind: str,
    model: str = "",
    base_url: str = "",
    source_lang: str = "",
    target_lang: str = "",
    reader: str = "",
    fit_mode: str = "",
    glossary: dict[str, str] | None = None,
    memory: bool = False,
) -> dict[str, Any]:
    """The record of one run: the version, what it talked to, and how it was asked to work."""
    # Imported here: `providers` is a layer above `core`, and this module is imported by the
    # writers, which the providers do not know about.
    from layoutkeep.providers.glossary import glossary_fingerprint

    return {
        "app_version": app_version(),
        "commit": git_commit(),
        "provider": provider_kind,
        "model": model_for(provider_kind, model),
        "endpoint": endpoint_for(provider_kind, base_url),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "reader": reader,
        "fit_mode": fit_mode,
        # Only what differs from the shipped defaults: an untouched installation records `{}`
        # rather than thirty numbers that say nothing about this run.
        "settings": tunables.overrides(),
        "glossary": (
            {"terms": len(glossary), "fingerprint": glossary_fingerprint(glossary)}
            if glossary
            else None
        ),
        "translation_memory": bool(memory),
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def record(doc: Document, **fields: Any) -> dict[str, Any]:
    """Build the record, keep it on the document, and return it.

    On the document because that is what the writers and `save_project` see: build it once, and
    every output of the run carries the same thing.
    """
    info = collect(**fields)
    doc.provenance = info
    return info


def of(doc: Document) -> dict[str, Any] | None:
    """The record on `doc`, or None for a document this build did not translate."""
    return getattr(doc, "provenance", None) or None


def summary(info: dict[str, Any]) -> str:
    """The one line that identifies the run: version, model, commit.

    Written into the producer and creator of a PDF, where anyone opening the file can see what
    made it without opening anything else. The whole record travels beside it.
    """
    commit = info.get("commit")
    return " · ".join(
        [
            f"LayoutKeep {info.get('app_version') or '?'}",
            str(info.get("model") or "?"),
            str(commit)[:10] if commit else "packaged build",
        ]
    )


def as_bytes(info: dict[str, Any]) -> bytes:
    """The record as the bytes an embedded file holds - indented, so it reads by eye."""
    return json.dumps(info, ensure_ascii=False, indent=1).encode("utf-8")
