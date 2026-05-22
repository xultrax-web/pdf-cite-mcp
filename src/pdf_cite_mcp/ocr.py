"""Tesseract-based OCR for scanned PDF pages.

Renders a PDF page to a high-DPI raster via PyMuPDF and passes it to
pytesseract.image_to_data() to recover word-level text + bboxes. Tesseract
returns bboxes in IMAGE pixel coordinates; we scale them back to PDF points
(1/72 inch) using the render DPI so the citations land in the same
coordinate system as native-text extractions — agents see one consistent
coordinate space whether the source was native or OCR'd.

Per-word `confidence` is normalized to [0.0, 1.0] from Tesseract's [0, 100]
scale and flows into Citation.confidence so downstream consumers can tell
when a claim is grounded in OCR'd vs native text.

Requires:
  - The system `tesseract` binary on PATH (the `pdf_doctor` tool in
    PHASE D verifies this and surfaces installation hints)
  - The `pdf-cite-mcp[ocr]` extras (pytesseract + Pillow)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

OCR_DPI = 200  # quality/speed compromise for typical text-heavy PDFs


def _require_ocr_deps() -> None:
    """Surface a clear error early when the optional extras aren't installed."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "OCR support requires the [ocr] extras. Install with:\n"
            "  uv add 'pdf-cite-mcp[ocr]'\n"
            "  pip install 'pdf-cite-mcp[ocr]'"
        ) from e


def ocr_page(pdf_path: Path, page_no: int, dpi: int = OCR_DPI) -> dict[str, Any]:
    """OCR a single page. Returns text + words with bbox + per-word confidence.

    Args:
        pdf_path: Path to the PDF file.
        page_no: 1-indexed page number.
        dpi: Render DPI for OCR. 200 is the operator-grade default; 300+
            gives sharper recognition at the cost of 2-4x more CPU.

    Returns a dict shaped like the native extractor's PageContent:
        {
            "page_no": int,
            "text": str (joined OCR'd words),
            "words": [{"text", "bbox", "confidence", "line", "block"}, ...],
            "width": float (PDF points),
            "height": float (PDF points),
            "dpi": int (the render DPI used)
        }
    """
    _require_ocr_deps()
    import fitz  # type: ignore[import-untyped]
    import pytesseract
    from PIL import Image

    doc = fitz.open(str(pdf_path))
    try:
        if page_no < 1 or page_no > doc.page_count:
            raise ValueError(
                f"page_no {page_no} out of range (1..{doc.page_count})"
            )
        page = doc[page_no - 1]
        rect = page.rect
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        data = pytesseract.image_to_data(
            img, output_type=pytesseract.Output.DICT
        )
    finally:
        doc.close()

    words: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for i, raw_text in enumerate(data["text"]):
        if not raw_text or not raw_text.strip():
            continue
        conf = data["conf"][i]
        try:
            conf_int = int(conf)
        except (ValueError, TypeError):
            continue
        if conf_int < 0:
            continue
        confidence = conf_int / 100.0

        left_px = data["left"][i]
        top_px = data["top"][i]
        w_px = data["width"][i]
        h_px = data["height"][i]
        x0 = left_px / scale
        y0 = top_px / scale
        x1 = (left_px + w_px) / scale
        y1 = (top_px + h_px) / scale

        words.append(
            {
                "text": raw_text,
                "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                "confidence": round(confidence, 2),
                "line": int(data["line_num"][i]),
                "block": int(data["block_num"][i]),
            }
        )
        text_parts.append(raw_text)

    return {
        "page_no": page_no,
        "text": " ".join(text_parts),
        "words": words,
        "width": float(rect.width),
        "height": float(rect.height),
        "dpi": dpi,
    }


def is_tesseract_available() -> bool:
    """True if the tesseract binary can be found by pytesseract. Used by
    pdf_doctor + test skips."""
    try:
        import pytesseract
    except ImportError:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except (pytesseract.TesseractNotFoundError, Exception):
        return False
