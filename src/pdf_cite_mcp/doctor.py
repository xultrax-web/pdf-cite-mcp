"""pdf_doctor — operator-grade health check.

Verifies the install is functional, the cache directory is writable, the
optional extras (OCR + tables) are present, and surfaces installation
hints when something's missing.

The returned dict's `healthy` field is True iff `issues` is empty — agents
can use it as a quick boolean before assuming any tool will work.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from . import __version__
from .cache import cache_dir


def _safe_import(module_name: str) -> tuple[bool, str]:
    """Try to import a module; return (ok, version_string_or_reason)."""
    try:
        mod = __import__(module_name)
    except ImportError as e:
        return False, f"not installed ({e})"
    version = getattr(mod, "__version__", None) or getattr(mod, "VERSION", None) or "unknown"
    return True, str(version)


def run_doctor() -> dict[str, Any]:
    """Run every health check and return a structured report."""
    report: dict[str, Any] = {
        "pdf_cite_mcp_version": __version__,
        "python": {
            "version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "deps": {},
        "ocr": {},
        "tables": {},
        "cache": {},
        "issues": [],
    }

    for pkg in ("mcp", "pydantic", "httpx"):
        ok, info = _safe_import(pkg)
        report["deps"][pkg] = info
        if not ok:
            report["issues"].append(f"required dep missing: {pkg}")

    # PyMuPDF has a quirky version exposure
    try:
        import fitz  # type: ignore[import-untyped]

        report["deps"]["pymupdf"] = getattr(fitz, "__version__", None) or getattr(
            fitz, "version", "unknown"
        )
        if isinstance(report["deps"]["pymupdf"], tuple):
            report["deps"]["pymupdf"] = report["deps"]["pymupdf"][0]
    except ImportError:
        report["deps"]["pymupdf"] = "not installed"
        report["issues"].append("PyMuPDF missing — pdf-cite-mcp cannot parse PDFs")

    # OCR extras
    try:
        import pytesseract

        report["ocr"]["pytesseract"] = pytesseract.__version__
        try:
            report["ocr"]["tesseract_binary"] = str(pytesseract.get_tesseract_version())
            report["ocr"]["available"] = True
        except Exception as e:  # TesseractNotFoundError + others
            report["ocr"]["tesseract_binary"] = f"not found ({type(e).__name__})"
            report["ocr"]["available"] = False
            report["issues"].append(
                "OCR unavailable — install the `tesseract` binary "
                "(brew install tesseract / apt install tesseract-ocr / "
                "choco install tesseract)"
            )
    except ImportError:
        report["ocr"]["pytesseract"] = "not installed"
        report["ocr"]["available"] = False
        report["issues"].append("OCR extras not installed — `uv add 'pdf-cite-mcp[ocr]'`")

    # Tables extras
    ok, info = _safe_import("pdfplumber")
    report["tables"]["pdfplumber"] = info
    report["tables"]["available"] = ok
    if not ok:
        report["issues"].append("Table extras not installed — `uv add 'pdf-cite-mcp[tables]'`")

    # Cache directory
    cdir = cache_dir()
    report["cache"]["dir"] = str(cdir)
    report["cache"]["exists"] = cdir.exists()
    report["cache"]["writable"] = False
    if cdir.exists():
        try:
            probe = cdir / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            report["cache"]["writable"] = True
        except OSError as e:
            report["issues"].append(f"Cache directory not writable: {e}")

        total = sum(f.stat().st_size for f in cdir.rglob("*") if f.is_file())
        report["cache"]["total_size_bytes"] = total
    else:
        report["issues"].append(f"Cache directory does not exist: {cdir}")

    report["healthy"] = len(report["issues"]) == 0
    return report
