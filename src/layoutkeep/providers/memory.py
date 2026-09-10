"""SQLite-backed translation memory.

Stores segment translations keyed by a hash of (source text, source language, target
language, model identity) so that a translation produced by one model is never served
back for a different model. This is what lets repeated running headers/footers in a book
get translated once and reused for every later occurrence.

Layout-blind (D2): only knows `Segment`, no knowledge of the document's visual layout.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from layoutkeep.core.docir import Segment


def _key(source: str, src_lang: str, tgt_lang: str, model: str) -> str:
    payload = f"{source}\x00{src_lang}\x00{tgt_lang}\x00{model}".encode()
    return hashlib.sha256(payload).hexdigest()


class TranslationMemory:
    """Look up and store translations by (source, src_lang, tgt_lang, model) hash.

    The database file is created on first use. WAL mode is enabled so two processes (e.g.
    the GUI and a background worker) can read/write concurrently without corrupting it.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                src_lang TEXT NOT NULL,
                tgt_lang TEXT NOT NULL,
                model TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        self.hits = 0
        self.misses = 0

    def close(self) -> None:
        self._conn.close()

    def get(self, segment: Segment, src_lang: str, tgt_lang: str, model: str) -> Segment | None:
        """Return a copy of `segment` with `target`/`from_memory` filled in, or None on a miss."""
        key = _key(segment.source, src_lang, tgt_lang, model)
        row = self._conn.execute(
            "SELECT target FROM translations WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return Segment(
            block_id=segment.block_id,
            source=segment.source,
            target=row[0],
            context_before=segment.context_before,
            context_after=segment.context_after,
            max_len=segment.max_len,
            confidence=segment.confidence,
            needs_review=False,
            from_memory=True,
        )

    def put(self, segment: Segment, src_lang: str, tgt_lang: str, model: str) -> None:
        """Store `segment.target` for later reuse. No-op if the segment has no target text."""
        if not segment.target:
            return
        key = _key(segment.source, src_lang, tgt_lang, model)
        self._conn.execute(
            "INSERT OR REPLACE INTO translations (key, source, target, src_lang, tgt_lang, model) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key, segment.source, segment.target, src_lang, tgt_lang, model),
        )
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        entries = self._conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        return {"hits": self.hits, "misses": self.misses, "entries": entries}
