"""Tests for PHASE C tools: pdf_ocr_pages + pdf_extract_tables.

OCR tests skip automatically when the system `tesseract` binary isn't on
PATH (common in CI before the apt-install step runs). Tables tests use
pdfplumber + a small generated table fixture, no system deps required.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest

from pdf_cite_mcp.ocr import is_tesseract_available
from pdf_cite_mcp.server import pdf_extract_tables, pdf_ocr_pages


@pytest.fixture
def table_pdf(tmp_path: Path) -> Path:
    """A small PDF whose page 1 has a clean rule-lined table that pdfplumber
    will detect. Uses PyMuPDF's draw_line to lay down a 3x3 grid."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Coordinates: a 3-column 3-row table from (72, 200) to (450, 350)
    rows = [200.0, 250.0, 300.0, 350.0]
    cols = [72.0, 200.0, 325.0, 450.0]
    for y in rows:
        page.draw_line((cols[0], y), (cols[-1], y))
    for x in cols:
        page.draw_line((x, rows[0]), (x, rows[-1]))
    # Cell text — center each in its cell-ish
    cells = [
        ["Owner", "Code", "Country"],
        ["Maersk", "MAEU", "Denmark"],
        ["Textainer", "TEXU", "Bermuda"],
    ]
    for r, row in enumerate(cells):
        for c, val in enumerate(row):
            page.insert_text((cols[c] + 6, rows[r] + 30), val, fontsize=11)
    out = tmp_path / "table.pdf"
    doc.save(str(out))
    doc.close()
    return out


def test_pdf_extract_tables_detects_rule_lined_table(table_pdf: Path) -> None:
    result = pdf_extract_tables(str(table_pdf), 1)
    assert result["metadata"]["tables"] >= 1
    assert "Maersk" in result["content"]
    assert "MAEU" in result["content"]
    # Markdown rendering should include the pipe-separator row
    assert "|" in result["content"]
    assert "---" in result["content"]


def test_pdf_extract_tables_returns_bbox_citation(table_pdf: Path) -> None:
    result = pdf_extract_tables(str(table_pdf), 1)
    cites = result["citations"]
    assert len(cites) >= 1
    cite = cites[0]
    x0, y0, x1, y1 = cite["bbox"]
    # The table is roughly from (72, 200) to (450, 350) in our fixture.
    assert 60 < x0 < 90
    assert 180 < y0 < 220
    assert 430 < x1 < 470
    assert 330 < y1 < 370


def test_pdf_extract_tables_zero_when_no_table(sample_pdf: Path) -> None:
    """The sample_pdf fixture has no rule lines — pdfplumber finds nothing."""
    result = pdf_extract_tables(str(sample_pdf), 1)
    assert result["metadata"]["tables"] == 0
    assert result["citations"] == []
    assert "No tables detected" in result["content"]


@pytest.mark.skipif(
    not is_tesseract_available(),
    reason="tesseract binary not on PATH — CI installs it before running this",
)
def test_pdf_ocr_pages_returns_text_and_confidence(sample_pdf: Path) -> None:
    result = pdf_ocr_pages(str(sample_pdf), [1])
    cites = result["citations"]
    assert len(cites) == 1
    cite = cites[0]
    assert cite["page"] == 1
    assert 0.0 <= cite["confidence"] <= 1.0
    # The fixture has the text "Hello pdf-cite-mcp" on page 1 — OCR should
    # surface at least the word "Hello" (case-insensitive match against the
    # joined OCR text).
    assert "hello" in result["content"].lower()
