"""Pytest fixtures.

We generate the test PDF at run-time with PyMuPDF rather than committing a
binary fixture — keeps the repo lean and makes the test content explicit.
"""

from __future__ import annotations

import os
from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point each test at a fresh cache dir so we don't share state."""
    monkeypatch.setenv("PDF_CITE_CACHE_DIR", str(tmp_path / "cache"))
    # Reset the lazy cache singleton between tests.
    from pdf_cite_mcp import server

    server._cache = None


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """A small 2-page PDF with known text content for assertions."""
    doc = fitz.open()
    page1 = doc.new_page(width=595, height=842)  # A4
    page1.insert_text((72, 100), "Hello pdf-cite-mcp", fontsize=18)
    page1.insert_text(
        (72, 150),
        "Operator-grade tolerance is plus or minus 0.5 percent.",
        fontsize=12,
    )
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 100), "Page two content goes here.", fontsize=12)
    page2.insert_text((72, 130), "Cite your sources.", fontsize=12)
    out = tmp_path / "sample.pdf"
    doc.save(str(out))
    doc.close()
    return out
