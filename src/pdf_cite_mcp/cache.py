"""SHA-256-keyed SQLite cache for parsed PDF content.

PDFs are expensive to parse (especially with OCR or large page counts). We
cache parsed pages by the content hash of the source file, so the same PDF
served from different paths or copies is only parsed once.

Schema:
  documents (sha256 PK, source, pages, title, author, has_text_layer, parsed_at)
  pages     (sha256, page_no, text, words_json, parsed_at)  PK (sha256, page_no)

SQLite ACID semantics handle atomic per-row writes. The cache directory is
created lazily; the DB file is created on first connect.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CACHE_DIR = Path.home() / ".pdf-cite"


def cache_dir() -> Path:
    override = os.environ.get("PDF_CITE_CACHE_DIR")
    p = Path(override) if override else DEFAULT_CACHE_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256_file(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    sha256          TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    pages           INTEGER NOT NULL,
    title           TEXT,
    author          TEXT,
    has_text_layer  INTEGER NOT NULL DEFAULT 1,
    parsed_at       REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    sha256      TEXT NOT NULL,
    page_no     INTEGER NOT NULL,
    text        TEXT NOT NULL,
    words_json  TEXT NOT NULL,
    parsed_at   REAL NOT NULL,
    PRIMARY KEY (sha256, page_no)
);
CREATE INDEX IF NOT EXISTS idx_pages_sha ON pages(sha256);
"""


@dataclass
class CachedDocument:
    sha256: str
    source: str
    pages: int
    title: str | None
    author: str | None
    has_text_layer: bool
    parsed_at: float


@dataclass
class CachedPage:
    sha256: str
    page_no: int
    text: str
    words: list[dict]
    parsed_at: float


class Cache:
    def __init__(self, dir_: Path | None = None) -> None:
        self.dir = dir_ or cache_dir()
        self.db_path = self.dir / "cache.sqlite3"
        with self._connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=30.0)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def upsert_document(self, doc: CachedDocument) -> None:
        with self._connect() as con:
            con.execute(
                """INSERT INTO documents
                       (sha256, source, pages, title, author, has_text_layer, parsed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(sha256) DO UPDATE SET
                       source         = excluded.source,
                       pages          = excluded.pages,
                       title          = excluded.title,
                       author         = excluded.author,
                       has_text_layer = excluded.has_text_layer,
                       parsed_at      = excluded.parsed_at""",
                (
                    doc.sha256,
                    doc.source,
                    doc.pages,
                    doc.title,
                    doc.author,
                    1 if doc.has_text_layer else 0,
                    doc.parsed_at,
                ),
            )

    def get_document(self, sha256: str) -> CachedDocument | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM documents WHERE sha256 = ?", (sha256,)
            ).fetchone()
        if not row:
            return None
        return CachedDocument(
            sha256=row["sha256"],
            source=row["source"],
            pages=row["pages"],
            title=row["title"],
            author=row["author"],
            has_text_layer=bool(row["has_text_layer"]),
            parsed_at=row["parsed_at"],
        )

    def upsert_page(
        self, sha256: str, page_no: int, text: str, words: list[dict]
    ) -> None:
        with self._connect() as con:
            con.execute(
                """INSERT INTO pages (sha256, page_no, text, words_json, parsed_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(sha256, page_no) DO UPDATE SET
                       text       = excluded.text,
                       words_json = excluded.words_json,
                       parsed_at  = excluded.parsed_at""",
                (
                    sha256,
                    page_no,
                    text,
                    json.dumps(words, separators=(",", ":")),
                    time.time(),
                ),
            )

    def get_page(self, sha256: str, page_no: int) -> CachedPage | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM pages WHERE sha256 = ? AND page_no = ?",
                (sha256, page_no),
            ).fetchone()
        if not row:
            return None
        return CachedPage(
            sha256=row["sha256"],
            page_no=row["page_no"],
            text=row["text"],
            words=json.loads(row["words_json"]),
            parsed_at=row["parsed_at"],
        )

    def clear_document(self, sha256: str) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM pages WHERE sha256 = ?", (sha256,))
            con.execute("DELETE FROM documents WHERE sha256 = ?", (sha256,))

    def clear_all(self) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM pages")
            con.execute("DELETE FROM documents")

    def stats(self) -> dict:
        with self._connect() as con:
            docs = con.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
            pages = con.execute("SELECT COUNT(*) AS n FROM pages").fetchone()["n"]
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "documents": docs,
            "pages": pages,
            "db_size_bytes": size,
            "db_path": str(self.db_path),
        }
