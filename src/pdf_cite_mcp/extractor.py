"""PyMuPDF (fitz) wrapper that produces text + per-word bounding boxes.

PyMuPDF returns word-level rectangles from `page.get_text("words")`, where
each word is a tuple `(x0, y0, x1, y1, word, block_no, line_no, word_no)`.

A page is considered "scanned" if its native text layer holds fewer than
10 characters — that triggers OCR (in pdf-cite-mcp v0.1.x).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-untyped]


@dataclass
class WordRecord:
    text: str
    bbox: tuple[float, float, float, float]
    line_no: int
    block_no: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bbox": [round(c, 2) for c in self.bbox],
            "line": self.line_no,
            "block": self.block_no,
        }


@dataclass
class PageContent:
    page_no: int  # 1-indexed
    text: str
    words: list[WordRecord]
    width: float
    height: float


@dataclass
class DocumentMeta:
    pages: int
    title: str | None
    author: str | None
    subject: str | None
    creator: str | None
    has_text_layer: bool
    scanned_pages: list[int]  # 1-indexed pages with < 10 chars of native text
    toc: list[dict[str, Any]]  # [{level, title, page}]


def open_pdf(path: Path) -> fitz.Document:
    return fitz.open(str(path))


def extract_meta(doc: fitz.Document) -> DocumentMeta:
    meta = doc.metadata or {}
    scanned: list[int] = []
    pages_total = doc.page_count
    for i in range(pages_total):
        page = doc[i]
        if len(page.get_text("text").strip()) < 10:
            scanned.append(i + 1)
    has_text_layer = len(scanned) < pages_total

    toc_raw = doc.get_toc(simple=True)  # [[level, title, page], ...]
    toc: list[dict[str, Any]] = [
        {"level": lvl, "title": title, "page": page} for lvl, title, page in toc_raw
    ]

    return DocumentMeta(
        pages=pages_total,
        title=meta.get("title") or None,
        author=meta.get("author") or None,
        subject=meta.get("subject") or None,
        creator=meta.get("creator") or None,
        has_text_layer=has_text_layer,
        scanned_pages=scanned,
        toc=toc,
    )


def extract_page(doc: fitz.Document, page_no: int) -> PageContent:
    """Extract text + per-word bboxes from one page. `page_no` is 1-indexed."""
    if page_no < 1 or page_no > doc.page_count:
        raise ValueError(f"page_no {page_no} out of range (1..{doc.page_count})")
    page = doc[page_no - 1]
    rect = page.rect
    text = page.get_text("text")
    raw_words = page.get_text("words")
    words: list[WordRecord] = []
    for x0, y0, x1, y1, w, block, line, _ in raw_words:
        words.append(
            WordRecord(
                text=w,
                bbox=(float(x0), float(y0), float(x1), float(y1)),
                line_no=int(line),
                block_no=int(block),
            )
        )
    return PageContent(
        page_no=page_no,
        text=text,
        words=words,
        width=float(rect.width),
        height=float(rect.height),
    )
