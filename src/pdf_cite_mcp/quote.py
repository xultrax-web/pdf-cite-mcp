"""pdf_quote — find an exact quote in a PDF and return precise word-level citations.

The wedge of this package. Given a search string, scan every page's word
list (from extractor.WordRecord.to_dict()) for a contiguous run of words
whose normalized text matches the needle word-for-word. For each hit,
union the bboxes of the matched words to produce a tight bbox citation.

Normalization is intentionally light:
  - lowercase
  - strip common punctuation from each word's edges (.,;:!?\\")]}\\')
  - whitespace between words is ignored (we're already on word boundaries)

Out of scope for v0.1:
  - hyphenated line breaks (where one word is split across lines)
  - fuzzy matching (rapidfuzz integration is queued for v0.1.x)
  - OCR'd content where the word stream may have artifacts

A `confidence` < 1.0 should be passed when calling on OCR'd word lists.
"""

from __future__ import annotations

import string

from .citation import Citation

_EDGE_PUNCT = string.punctuation


def _normalize(word: str) -> str:
    return word.lower().strip(_EDGE_PUNCT)


def _split_needle(needle: str) -> list[str]:
    return [_normalize(w) for w in needle.split() if w.strip()]


def find_quote_in_page(
    page_no: int,
    words: list[dict],
    needle: str,
    confidence: float = 1.0,
) -> list[Citation]:
    """Return every contiguous-word match of `needle` on a single page.

    `words` is the per-page word list (with `text` and `bbox`). The result
    may contain 0, 1, or many citations — a phrase appearing twice on the
    page yields two citations.
    """
    needle_words = _split_needle(needle)
    if not needle_words:
        return []
    n = len(needle_words)
    if n > len(words):
        return []

    normalized = [_normalize(w["text"]) for w in words]
    citations: list[Citation] = []
    for i in range(len(words) - n + 1):
        if normalized[i : i + n] == needle_words:
            matched = words[i : i + n]
            x0 = min(w["bbox"][0] for w in matched)
            y0 = min(w["bbox"][1] for w in matched)
            x1 = max(w["bbox"][2] for w in matched)
            y1 = max(w["bbox"][3] for w in matched)
            snippet = " ".join(w["text"] for w in matched)
            citations.append(
                Citation(
                    page=page_no,
                    bbox=(x0, y0, x1, y1),
                    snippet=snippet,
                    confidence=confidence,
                )
            )
    return citations


def bbox_from_words(words: list[dict]) -> tuple[float, float, float, float]:
    """Compute the union bbox of a non-empty word list."""
    if not words:
        return (0.0, 0.0, 0.0, 0.0)
    x0 = min(w["bbox"][0] for w in words)
    y0 = min(w["bbox"][1] for w in words)
    x1 = max(w["bbox"][2] for w in words)
    y1 = max(w["bbox"][3] for w in words)
    return (x0, y0, x1, y1)
