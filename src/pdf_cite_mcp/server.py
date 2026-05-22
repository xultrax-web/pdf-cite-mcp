"""FastMCP server for pdf-cite-mcp.

Each tool returns either a structured response dict or a CitedContent payload
(via .to_dict()). Tools are exposed both over MCP stdio transport (the default
`pdf-cite-mcp serve` mode) and as Python callables for tests + CLI sub-commands.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .cache import Cache, CachedDocument, sha256_file
from .citation import Citation, CitedContent
from .extractor import extract_meta, extract_page, open_pdf
from .quote import bbox_from_words, find_quote_in_page

mcp = FastMCP("pdf-cite-mcp")
_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache


def _resolve_pdf(file_path: str) -> Path:
    if file_path.startswith(("http://", "https://")):
        from .cache import cache_dir
        from .url_fetch import safe_download

        return safe_download(file_path, cache_dir())
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"PDF not found: {p}")
    if not p.is_file():
        raise ValueError(f"Not a file: {p}")
    return p


def _parse_and_cache(path: Path) -> tuple[str, CachedDocument]:
    """Parse a PDF (if not already cached) and return (sha256, document)."""
    sha = sha256_file(path)
    cache = get_cache()
    cached = cache.get_document(sha)
    if cached is not None:
        return sha, cached

    doc = open_pdf(path)
    meta = extract_meta(doc)
    cached_doc = CachedDocument(
        sha256=sha,
        source=str(path),
        pages=meta.pages,
        title=meta.title,
        author=meta.author,
        has_text_layer=meta.has_text_layer,
        parsed_at=time.time(),
    )
    cache.upsert_document(cached_doc)
    for page_no in range(1, meta.pages + 1):
        page = extract_page(doc, page_no)
        cache.upsert_page(
            sha,
            page_no,
            page.text,
            [w.to_dict() for w in page.words],
        )
    doc.close()
    return sha, cached_doc


@mcp.tool()
def pdf_info(file_path: str) -> dict[str, Any]:
    """Return pages, metadata, TOC, and scanned-page detection for a PDF.

    Use this first when working with an unfamiliar PDF — it tells you the
    page count, table of contents, and whether OCR will be needed.

    Args:
        file_path: Absolute path to the PDF (`~` expansion is supported).
    """
    path = _resolve_pdf(file_path)
    sha, _ = _parse_and_cache(path)
    doc = open_pdf(path)
    meta = extract_meta(doc)
    doc.close()
    return {
        "sha256": sha,
        "source": str(path),
        "pages": meta.pages,
        "title": meta.title,
        "author": meta.author,
        "subject": meta.subject,
        "creator": meta.creator,
        "has_text_layer": meta.has_text_layer,
        "scanned_pages": meta.scanned_pages,
        "toc": meta.toc,
    }


@mcp.tool()
def pdf_read_pages(file_path: str, pages: list[int]) -> dict[str, Any]:
    """Read specific pages from a PDF and return cited content.

    Each requested page produces one Citation whose bbox spans the page's
    text region and whose `snippet` is a leading excerpt. For word-level
    precision, use `pdf_quote` (v0.1.x).

    Args:
        file_path: Path to the PDF.
        pages: 1-indexed page numbers to read.
    """
    path = _resolve_pdf(file_path)
    sha, cached = _parse_and_cache(path)
    cache = get_cache()
    chunks: list[str] = []
    cites: list[Citation] = []
    for page_no in pages:
        if page_no < 1 or page_no > cached.pages:
            raise ValueError(f"page {page_no} out of range (1..{cached.pages})")
        cp = cache.get_page(sha, page_no)
        if cp is None:
            doc = open_pdf(path)
            pc = extract_page(doc, page_no)
            doc.close()
            words = [w.to_dict() for w in pc.words]
            cache.upsert_page(sha, page_no, pc.text, words)
            text = pc.text
        else:
            text = cp.text
            words = cp.words

        chunks.append(f"--- Page {page_no} ---\n{text}")

        if words:
            x0 = min(w["bbox"][0] for w in words)
            y0 = min(w["bbox"][1] for w in words)
            x1 = max(w["bbox"][2] for w in words)
            y1 = max(w["bbox"][3] for w in words)
            bbox: tuple[float, float, float, float] = (x0, y0, x1, y1)
        else:
            bbox = (0.0, 0.0, 0.0, 0.0)

        snippet = text.strip().splitlines()[0] if text.strip() else ""
        snippet = snippet[:200]

        cites.append(
            Citation(
                page=page_no,
                bbox=bbox,
                snippet=snippet,
                confidence=1.0 if cached.has_text_layer else 0.0,
            )
        )

    result = CitedContent(
        content="\n\n".join(chunks),
        citations=cites,
        metadata={"sha256": sha, "source": str(path)},
    )
    return result.to_dict()


@mcp.tool()
def pdf_search(file_path: str, query: str, k: int = 5) -> dict[str, Any]:
    """Search a PDF with BM25 ranking and return cited matches.

    Each result is a page-level citation — for word-level precision on a
    specific quote, follow up with `pdf_quote`.

    Args:
        file_path: Path to the PDF.
        query: FTS5 query. Supports `"phrase searches"`, boolean
            `AND` / `OR` / `NOT`, and prefix matching like `oper*`.
            Bare terms are AND'd together.
        k: Max number of pages to return (default 5).
    """
    path = _resolve_pdf(file_path)
    sha, _ = _parse_and_cache(path)
    cache = get_cache()
    rows = cache.search_fts(sha, query, k)

    cites: list[Citation] = []
    summary_chunks: list[str] = []
    for r in rows:
        page_no = r["page_no"]
        cp = cache.get_page(sha, page_no)
        bbox = bbox_from_words(cp.words) if cp else (0.0, 0.0, 0.0, 0.0)
        snip = (r["snip"] or "").strip() or (cp.text[:160] if cp else "")
        cites.append(
            Citation(
                page=page_no,
                bbox=bbox,
                snippet=snip,
                confidence=1.0,
            )
        )
        summary_chunks.append(f"[page {page_no} · bm25 {r['rank']:.2f}] {snip}")

    result = CitedContent(
        content="\n".join(summary_chunks) if summary_chunks else "No matches.",
        citations=cites,
        metadata={"sha256": sha, "source": str(path), "query": query, "k": k},
    )
    return result.to_dict()


@mcp.tool()
def pdf_quote(file_path: str, quote: str) -> dict[str, Any]:
    """Find an exact quote in a PDF and return precise word-level citations.

    The killer tool: returns ALL occurrences of `quote` in the document with
    tight word-union bboxes. Use this when an agent needs to ground a
    specific claim back to a verifiable rectangle on a verifiable page.

    Matching is case-insensitive and tolerates edge punctuation per word
    (e.g. trailing commas, periods, quotes). Whitespace between words is
    normalized. Hyphenated line breaks and fuzzy matches are out of scope
    for v0.1 — rapidfuzz integration is queued for v0.1.x.

    Args:
        file_path: Path to the PDF.
        quote: The exact phrase to find. Multi-word quotes are matched as
            a contiguous sequence of words.
    """
    path = _resolve_pdf(file_path)
    sha, cached = _parse_and_cache(path)
    cache = get_cache()
    confidence = 1.0 if cached.has_text_layer else 0.0

    all_cites: list[Citation] = []
    for page_no in range(1, cached.pages + 1):
        cp = cache.get_page(sha, page_no)
        if cp is None:
            continue
        all_cites.extend(
            find_quote_in_page(page_no, cp.words, quote, confidence=confidence)
        )

    if all_cites:
        content = "\n".join(f"[page {c.page}] {c.snippet}" for c in all_cites)
    else:
        content = "No exact match found. Try `pdf_search` for ranked relevance."

    result = CitedContent(
        content=content,
        citations=all_cites,
        metadata={
            "sha256": sha,
            "source": str(path),
            "quote": quote,
            "matches": len(all_cites),
        },
    )
    return result.to_dict()


@mcp.tool()
def pdf_ocr_pages(
    file_path: str, pages: list[int], dpi: int = 200
) -> dict[str, Any]:
    """OCR specified pages of a PDF and return cited content.

    Use for pages flagged in `pdf_info`'s `scanned_pages` field. Per-word
    Tesseract confidence flows into each Citation so an agent can tell
    high-confidence OCR'd grounding from low-confidence guesses.

    Args:
        file_path: Path to the PDF.
        pages: 1-indexed page numbers to OCR.
        dpi: Render DPI (default 200). 300+ for sharper text at 2-4x CPU.

    Requires the `pdf-cite-mcp[ocr]` extras and the system `tesseract`
    binary on PATH (verified by `pdf_doctor` in PHASE D).
    """
    from .ocr import ocr_page

    path = _resolve_pdf(file_path)
    sha, _ = _parse_and_cache(path)

    cites: list[Citation] = []
    chunks: list[str] = []
    for page_no in pages:
        ocr_result = ocr_page(path, page_no, dpi=dpi)
        words = ocr_result["words"]
        if words:
            x0 = min(w["bbox"][0] for w in words)
            y0 = min(w["bbox"][1] for w in words)
            x1 = max(w["bbox"][2] for w in words)
            y1 = max(w["bbox"][3] for w in words)
            bbox: tuple[float, float, float, float] = (x0, y0, x1, y1)
            mean_conf = sum(w["confidence"] for w in words) / len(words)
        else:
            bbox = (0.0, 0.0, 0.0, 0.0)
            mean_conf = 0.0

        snippet = ocr_result["text"][:200]
        chunks.append(f"--- Page {page_no} (OCR @ {dpi} DPI) ---\n{ocr_result['text']}")
        cites.append(
            Citation(
                page=page_no,
                bbox=bbox,
                snippet=snippet,
                confidence=round(mean_conf, 2),
            )
        )

    result = CitedContent(
        content="\n\n".join(chunks),
        citations=cites,
        metadata={"sha256": sha, "source": str(path), "dpi": dpi},
    )
    return result.to_dict()


@mcp.tool()
def pdf_extract_tables(file_path: str, page: int) -> dict[str, Any]:
    """Extract every table on a page as markdown + bbox citations.

    Each detected table becomes a markdown block (GitHub-flavored) and a
    Citation whose bbox spans the table's outer rectangle. Tables that
    pdfplumber can't detect (e.g. no rule lines + irregular spacing) won't
    appear — fall back to `pdf_quote` for the values you need.

    Args:
        file_path: Path to the PDF.
        page: 1-indexed page number to scan for tables.

    Requires the `pdf-cite-mcp[tables]` extras (pdfplumber).
    """
    from .tables import extract_tables_on_page

    path = _resolve_pdf(file_path)
    sha, _ = _parse_and_cache(path)

    tables = extract_tables_on_page(path, page)
    cites: list[Citation] = []
    chunks: list[str] = []
    for t in tables:
        bbox: tuple[float, float, float, float] = (
            t["bbox"][0],
            t["bbox"][1],
            t["bbox"][2],
            t["bbox"][3],
        )
        snippet = (
            t["markdown"].splitlines()[0][:200]
            if t["markdown"]
            else f"table {t['table_index']}"
        )
        cites.append(
            Citation(
                page=page,
                bbox=bbox,
                snippet=snippet,
                confidence=1.0,
            )
        )
        chunks.append(
            f"### Table {t['table_index']} · {t['rows']}x{t['cols']} on page {page}\n\n"
            + t["markdown"]
        )

    if not tables:
        content = f"No tables detected on page {page}."
    else:
        content = "\n\n".join(chunks)

    result = CitedContent(
        content=content,
        citations=cites,
        metadata={
            "sha256": sha,
            "source": str(path),
            "page": page,
            "tables": len(tables),
        },
    )
    return result.to_dict()


@mcp.tool()
def pdf_render_page(file_path: str, page: int, dpi: int = 150) -> dict[str, Any]:
    """Render a PDF page to a PNG image (base64) for vision models.

    Use when text extraction can't carry what the agent needs to see —
    charts, figures, layout, handwritten annotations, signatures. The
    image is returned as a base64-encoded PNG string; MCP clients with
    vision can decode and attach it to a follow-up prompt.

    Args:
        file_path: Path or http(s) URL to the PDF.
        page: 1-indexed page number.
        dpi: Render DPI (default 150). 200-300 sharpens text inside charts
            at 2-4x output size.

    Returns:
        {
            "page", "dpi",
            "width_px", "height_px",      // raster dimensions
            "width_pt", "height_pt",      // page size in PDF points
            "format": "png",
            "data_base64": str,           // the PNG bytes, base64-encoded
            "citation": { page, bbox=full-page, snippet, confidence }
        }
    """
    import base64

    import fitz  # type: ignore[import-untyped]

    path = _resolve_pdf(file_path)
    sha, cached = _parse_and_cache(path)
    if page < 1 or page > cached.pages:
        raise ValueError(f"page {page} out of range (1..{cached.pages})")

    doc = fitz.open(str(path))
    try:
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        rect = doc[page - 1].rect
        pix = doc[page - 1].get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pix.tobytes("png")
        width_px = pix.width
        height_px = pix.height
    finally:
        doc.close()

    citation = Citation(
        page=page,
        bbox=(0.0, 0.0, float(rect.width), float(rect.height)),
        snippet=f"page {page} rendered at {dpi} DPI",
        confidence=1.0,
    )

    return {
        "page": page,
        "dpi": dpi,
        "width_px": width_px,
        "height_px": height_px,
        "width_pt": float(rect.width),
        "height_pt": float(rect.height),
        "format": "png",
        "data_base64": base64.b64encode(png_bytes).decode("ascii"),
        "citation": citation.model_dump(mode="json"),
        "metadata": {"sha256": sha, "source": str(path)},
    }


@mcp.tool()
def pdf_doctor() -> dict[str, Any]:
    """Operator-grade health check.

    Reports Python + dependency versions, OCR + table extras availability,
    cache directory state (path, writable, size), and a list of any issues.
    The `healthy` boolean is True iff no issues were found.

    Run this first when MCP tools fail unexpectedly — most problems
    (missing extras, no tesseract on PATH, unwritable cache dir) surface
    here with an actionable hint.
    """
    from .doctor import run_doctor

    return run_doctor()


@mcp.tool()
def pdf_cache_stats() -> dict[str, Any]:
    """Return cache stats: document count, page count, DB file size + path."""
    return get_cache().stats()


@mcp.tool()
def pdf_cache_clear(sha256: str | None = None) -> dict[str, Any]:
    """Clear cache entries.

    Args:
        sha256: When provided, clear only that document's cached pages.
            When None, clear EVERY cached document (use with care; next
            parse re-extracts from source PDFs).
    """
    cache = get_cache()
    if sha256:
        cache.clear_document(sha256)
        return {"cleared": "document", "sha256": sha256}
    cache.clear_all()
    return {"cleared": "all"}


def run_stdio() -> None:
    """Entry point for stdio MCP transport."""
    mcp.run()


if __name__ == "__main__":
    run_stdio()
