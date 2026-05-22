"""pdfplumber-based table extraction with markdown rendering + bbox citations.

pdfplumber identifies tables by detecting rule lines and cell-text alignment,
then exposes each table's outer bbox + a 2D list of cell strings. We render
the result as a GitHub-flavored markdown table and produce one Citation per
table whose bbox spans the table's outer rectangle.

Cells with no detected text render as empty markdown cells (`| |`).
Multi-line cell content is collapsed to a single space.

pdfplumber's coordinate system matches PyMuPDF's: PDF points with origin at
the top-left of the page, so bbox values pass through unchanged.

Requires:
  - The `pdf-cite-mcp[tables]` extras (pdfplumber)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _require_table_deps() -> None:
    try:
        import pdfplumber  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "Table extraction requires the [tables] extras. Install with:\n"
            "  uv add 'pdf-cite-mcp[tables]'\n"
            "  pip install 'pdf-cite-mcp[tables]'"
        ) from e


def _clean_cell(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())


def _render_markdown(rows: list[list[str | None]]) -> str:
    """Render a 2D list of cells as a GitHub-flavored markdown table.

    If `rows` is empty or has no columns, returns an empty string. The first
    row is treated as the header.
    """
    if not rows or not rows[0]:
        return ""
    width = max(len(r) for r in rows)
    padded = [[(*r, *([None] * (width - len(r))))] for r in rows]
    # Flatten the padded tuples back to lists
    padded = [list(r[0]) if isinstance(r[0], tuple) else r for r in padded]

    header = padded[0]
    body = padded[1:]

    def fmt(cell: str | None) -> str:
        s = _clean_cell(cell)
        return s.replace("|", "\\|")  # escape pipes inside cells

    lines: list[str] = []
    lines.append("| " + " | ".join(fmt(c) for c in header) + " |")
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in body:
        lines.append("| " + " | ".join(fmt(c) for c in row) + " |")
    return "\n".join(lines)


def extract_tables_on_page(
    pdf_path: Path, page_no: int
) -> list[dict[str, Any]]:
    """Return every table detected on the page as markdown + bbox metadata.

    Each entry:
        {
            "table_index": int (0-based within this page),
            "bbox": [x0, y0, x1, y1] (PDF points),
            "rows": int,
            "cols": int,
            "markdown": str,
        }
    """
    _require_table_deps()
    import pdfplumber

    results: list[dict[str, Any]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        if page_no < 1 or page_no > len(pdf.pages):
            raise ValueError(
                f"page_no {page_no} out of range (1..{len(pdf.pages)})"
            )
        page = pdf.pages[page_no - 1]
        for idx, table in enumerate(page.find_tables()):
            rows = table.extract() or []
            bbox = tuple(round(c, 2) for c in table.bbox)
            markdown = _render_markdown(rows)
            results.append(
                {
                    "table_index": idx,
                    "bbox": list(bbox),
                    "rows": len(rows),
                    "cols": max((len(r) for r in rows), default=0),
                    "markdown": markdown,
                }
            )
    return results
