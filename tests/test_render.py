"""Tests for PHASE E: pdf_render_page (PDF → PNG for vision)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from pdf_cite_mcp.server import pdf_render_page


def test_pdf_render_page_returns_valid_png(sample_pdf: Path) -> None:
    result = pdf_render_page(str(sample_pdf), 1)
    assert result["page"] == 1
    assert result["dpi"] == 150
    assert result["format"] == "png"
    assert result["width_px"] > 0
    assert result["height_px"] > 0
    # PNG magic bytes
    data = base64.b64decode(result["data_base64"])
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_pdf_render_page_citation_spans_full_page(sample_pdf: Path) -> None:
    result = pdf_render_page(str(sample_pdf), 1)
    cite = result["citation"]
    assert cite["page"] == 1
    x0, y0, x1, y1 = cite["bbox"]
    # Full page bbox: from origin to page dimensions
    assert x0 == 0.0
    assert y0 == 0.0
    assert x1 == result["width_pt"]
    assert y1 == result["height_pt"]


def test_pdf_render_page_dpi_scales_raster(sample_pdf: Path) -> None:
    """Double the DPI ≈ double the pixel dimensions."""
    low = pdf_render_page(str(sample_pdf), 1, dpi=75)
    high = pdf_render_page(str(sample_pdf), 1, dpi=300)
    assert high["width_px"] > low["width_px"] * 3.5
    assert high["height_px"] > low["height_px"] * 3.5


def test_pdf_render_page_rejects_out_of_range(sample_pdf: Path) -> None:
    with pytest.raises(ValueError, match="out of range"):
        pdf_render_page(str(sample_pdf), 99)


def test_pdf_render_page_a4_dimensions(sample_pdf: Path) -> None:
    """The sample fixture pages are A4 (595 x 842 points)."""
    result = pdf_render_page(str(sample_pdf), 1)
    assert result["width_pt"] == pytest.approx(595, abs=2)
    assert result["height_pt"] == pytest.approx(842, abs=2)
