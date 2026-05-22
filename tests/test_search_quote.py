"""Tests for the wedge tools: pdf_search (BM25) + pdf_quote (precise bbox)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_cite_mcp.server import pdf_quote, pdf_search


def test_pdf_quote_finds_exact_text_on_correct_page(sample_pdf: Path) -> None:
    result = pdf_quote(str(sample_pdf), "Cite your sources")
    assert result["metadata"]["matches"] >= 1
    cites = result["citations"]
    found = next((c for c in cites if c["page"] == 2), None)
    assert found is not None
    # bbox should sit near the insertion point (72, 130) on page 2
    x0, y0, x1, y1 = found["bbox"]
    assert 60 < x0 < 90
    assert 100 < y0 < 150
    assert x1 > x0 and y1 > y0
    assert "Cite" in found["snippet"]


def test_pdf_quote_case_insensitive_and_strips_edge_punct(sample_pdf: Path) -> None:
    result = pdf_quote(str(sample_pdf), "hello PDF-CITE-MCP")
    assert result["metadata"]["matches"] >= 1
    assert result["citations"][0]["page"] == 1


def test_pdf_quote_missing_text_returns_empty_citations(sample_pdf: Path) -> None:
    result = pdf_quote(str(sample_pdf), "this string does not appear anywhere")
    assert result["metadata"]["matches"] == 0
    assert result["citations"] == []
    assert "No exact match" in result["content"]


def test_pdf_quote_finds_multiple_word_phrase(sample_pdf: Path) -> None:
    result = pdf_quote(str(sample_pdf), "Page two content goes here")
    assert result["metadata"]["matches"] >= 1
    cite = result["citations"][0]
    assert cite["page"] == 2
    # Multi-word match should span wider than a single word
    x0, _, x1, _ = cite["bbox"]
    assert (x1 - x0) > 50  # several words wide


def test_pdf_search_returns_ranked_matches(sample_pdf: Path) -> None:
    result = pdf_search(str(sample_pdf), "tolerance")
    assert len(result["citations"]) >= 1
    # The word "tolerance" only appears on page 1
    assert result["citations"][0]["page"] == 1


def test_pdf_search_zero_results_returns_empty_list(sample_pdf: Path) -> None:
    result = pdf_search(str(sample_pdf), "kryptonite")
    assert result["citations"] == []
    assert "No matches" in result["content"]


def test_pdf_search_phrase_query(sample_pdf: Path) -> None:
    """FTS5 phrase searches with quotes must work."""
    result = pdf_search(str(sample_pdf), '"Cite your sources"')
    assert len(result["citations"]) >= 1
    assert result["citations"][0]["page"] == 2
