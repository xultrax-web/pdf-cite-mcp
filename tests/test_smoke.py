"""Smoke test: parse a generated PDF end-to-end and verify the citation contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_cite_mcp.server import pdf_info, pdf_read_pages


def test_pdf_info_returns_pages_and_meta(sample_pdf: Path) -> None:
    result = pdf_info(str(sample_pdf))
    assert result["pages"] == 2
    assert result["has_text_layer"] is True
    assert result["scanned_pages"] == []
    assert isinstance(result["sha256"], str)
    assert len(result["sha256"]) == 64


def test_pdf_read_pages_returns_citations(sample_pdf: Path) -> None:
    result = pdf_read_pages(str(sample_pdf), [1, 2])
    assert "Hello pdf-cite-mcp" in result["content"]
    assert "Cite your sources." in result["content"]

    cites = result["citations"]
    assert len(cites) == 2
    assert cites[0]["page"] == 1
    assert cites[1]["page"] == 2

    for c in cites:
        x0, y0, x1, y1 = c["bbox"]
        assert x1 > x0 and y1 > y0
        assert c["confidence"] == 1.0
        assert isinstance(c["snippet"], str)


def test_pdf_read_pages_validates_range(sample_pdf: Path) -> None:
    with pytest.raises(ValueError, match="out of range"):
        pdf_read_pages(str(sample_pdf), [99])


def test_pdf_read_pages_cached_path_returns_same_result(sample_pdf: Path) -> None:
    """Second call must hit the cache and still return identical content."""
    first = pdf_read_pages(str(sample_pdf), [1])
    second = pdf_read_pages(str(sample_pdf), [1])
    assert first["content"] == second["content"]
    assert first["citations"] == second["citations"]
