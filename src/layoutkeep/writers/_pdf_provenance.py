"""Writing the run's provenance into the PDF's metadata, and copying it to another file.

Koşunun kaynak bilgisini PDF üst verisine yazar ve başka bir dosyaya kopyalar.
"""

from __future__ import annotations

import json

import pymupdf

from layoutkeep.core import provenance

#: Document-information keys that may be written back. `format` and `encryption` come out of
#: `pdf.metadata` too and are not settable: passing them to `set_metadata` raises.
_SETTABLE_INFO = (
    "title", "author", "subject", "keywords", "creator", "producer",
    "creationDate", "modDate", "trapped",
)


def _write_provenance(pdf: pymupdf.Document, info: dict, base: dict | None = None) -> None:
    """Put the run's record into the file: one line in producer/creator, the whole thing beside it.

    WHY THIS EXISTS: a PDF that does not say what translated it cannot be compared with another -
    the same source run twice under different settings is two files with no way to tell them apart
    afterwards (`core/provenance.py`). The line names the build, the model and the commit; the
    record beside it carries the endpoint, the reader path, the settings and the languages.

    The whole record goes in an EMBEDDED FILE rather than into the XMP stream: XMP is the source's
    own metadata (an arXiv paper's DOI and licence live there) and `set_xml_metadata` replaces that
    stream wholesale. An embedded file is added to the document instead of overwriting what the
    document already said about itself.

    `base` is the metadata to keep - the document's own by default, or another file's when a
    document is composed out of one (`copy_provenance`).
    """
    line = provenance.summary(info)
    # Merged with what the file carried: this is the only metadata this module writes, and it must
    # not be the reason a title or an author disappears from the output.
    source = pdf.metadata if base is None else base
    meta = {key: source.get(key, "") for key in _SETTABLE_INFO}
    meta["producer"] = line
    meta["creator"] = line
    pdf.set_metadata(meta)
    if provenance.FILE_NAME in pdf.embfile_names():
        # A verification round writes the document again; the record is not appended twice.
        pdf.embfile_del(provenance.FILE_NAME)
    pdf.embfile_add(
        provenance.FILE_NAME,
        provenance.as_bytes(info),
        filename=provenance.FILE_NAME,
        desc=line,
    )


def copy_provenance(source: pymupdf.Document, target: pymupdf.Document) -> None:
    """Carry a written document's record into one composed out of its pages.

    The bilingual PDF is built page by page from the source and the translated file, so it
    inherits neither the metadata nor the embedded record - and a file that does not say what
    translated it is the thing `core/provenance.py` exists to prevent. The record is read back
    from the translated file rather than passed in, so it cannot drift from what that file says.
    """
    if provenance.FILE_NAME not in source.embfile_names():
        return
    try:
        info = json.loads(source.embfile_get(provenance.FILE_NAME).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        # A record this build cannot read is not a reason to fail the composition.
        return
    if isinstance(info, dict):
        _write_provenance(target, info, base=source.metadata)
