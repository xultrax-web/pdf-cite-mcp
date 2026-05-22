"""Tests for PHASE D: pdf_doctor + cache ops + SSRF-safe URL fetch.

URL safety tests are deliberately offline — they verify the pre-network
validation pipeline (scheme allowlist + private-IP rejection) without
ever opening a socket beyond DNS resolution of public-facing names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_cite_mcp.server import (
    pdf_cache_clear,
    pdf_cache_stats,
    pdf_doctor,
    pdf_info,
)
from pdf_cite_mcp.url_fetch import UnsafeURLError, is_url_safe, safe_download


# ─── doctor ──────────────────────────────────────────────────────────


def test_pdf_doctor_returns_structured_report() -> None:
    report = pdf_doctor()
    assert "pdf_cite_mcp_version" in report
    assert "python" in report
    assert "deps" in report
    assert "ocr" in report
    assert "tables" in report
    assert "cache" in report
    assert "issues" in report
    assert "healthy" in report
    assert isinstance(report["healthy"], bool)


def test_pdf_doctor_reports_writable_cache() -> None:
    report = pdf_doctor()
    assert report["cache"]["exists"] is True
    assert report["cache"]["writable"] is True


def test_pdf_doctor_reports_tables_extra(sample_pdf: Path) -> None:
    # The dev env has tables extras installed (uv sync --all-extras).
    report = pdf_doctor()
    assert report["tables"]["available"] is True


# ─── cache ops ────────────────────────────────────────────────────────


def test_pdf_cache_stats_starts_empty() -> None:
    stats = pdf_cache_stats()
    assert stats["documents"] == 0
    assert stats["pages"] == 0


def test_pdf_cache_stats_reflects_parsed_documents(sample_pdf: Path) -> None:
    pdf_info(str(sample_pdf))  # triggers parse + cache
    stats = pdf_cache_stats()
    assert stats["documents"] == 1
    assert stats["pages"] == 2


def test_pdf_cache_clear_removes_everything(sample_pdf: Path) -> None:
    pdf_info(str(sample_pdf))
    pdf_cache_clear()
    stats = pdf_cache_stats()
    assert stats["documents"] == 0
    assert stats["pages"] == 0


def test_pdf_cache_clear_by_sha256(sample_pdf: Path) -> None:
    info = pdf_info(str(sample_pdf))
    pdf_cache_clear(info["sha256"])
    stats = pdf_cache_stats()
    assert stats["documents"] == 0


# ─── url_fetch · SSRF pipeline ───────────────────────────────────────


def test_url_safety_rejects_non_http_scheme() -> None:
    safe, reason = is_url_safe("ftp://example.com/foo.pdf")
    assert safe is False
    assert "scheme" in reason.lower()


def test_url_safety_rejects_file_scheme() -> None:
    safe, reason = is_url_safe("file:///etc/passwd")
    assert safe is False


def test_url_safety_rejects_loopback() -> None:
    safe, reason = is_url_safe("http://127.0.0.1/foo.pdf")
    assert safe is False
    assert "non-public" in reason.lower() or "loopback" in reason.lower()


def test_url_safety_rejects_private_network() -> None:
    safe, _ = is_url_safe("http://10.0.0.1/foo.pdf")
    assert safe is False


def test_url_safety_rejects_link_local() -> None:
    safe, _ = is_url_safe("http://169.254.169.254/latest/meta-data/")
    assert safe is False


def test_url_safety_rejects_localhost_name() -> None:
    """`localhost` resolves to 127.0.0.1 — must be rejected."""
    safe, _ = is_url_safe("http://localhost:8080/foo.pdf")
    assert safe is False


def test_safe_download_raises_on_unsafe_url(tmp_path: Path) -> None:
    with pytest.raises(UnsafeURLError):
        safe_download("http://127.0.0.1/foo.pdf", tmp_path)


def test_safe_download_raises_on_unsupported_scheme(tmp_path: Path) -> None:
    with pytest.raises(UnsafeURLError):
        safe_download("ftp://example.com/foo.pdf", tmp_path)
