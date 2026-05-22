"""The Citation contract — the wedge of pdf-cite-mcp.

Every extraction tool returns a CitedContent: a body of text plus one or more
Citation records pinning each fragment to a precise page+bbox+snippet inside
the source PDF.

Coordinate system: PDF points (1/72 inch). PyMuPDF (fitz) returns bboxes
in this system by default, with origin at the top-left of each page.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    """A precise pointer into a PDF: page + rectangle + the text it contains.

    `confidence` is 1.0 for native PDF text and < 1.0 for OCR'd or
    vision-recovered content. Downstream agents can use it to decide
    whether to trust the citation or surface it as "approximate".
    """

    page: int = Field(..., ge=1, description="1-indexed page number")
    bbox: tuple[float, float, float, float] = Field(
        ...,
        description="(x0, y0, x1, y1) in PDF points, origin top-left",
    )
    snippet: str = Field(..., description="The exact text inside that rectangle")
    confidence: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator("bbox")
    @classmethod
    def _bbox_well_ordered(
        cls, v: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = v
        if x1 < x0 or y1 < y0:
            raise ValueError("bbox must satisfy x0<=x1 and y0<=y1")
        return v


class CitedContent(BaseModel):
    """An extraction response: text body + the citations that ground it.

    Most pdf-cite-mcp tools wrap their output in this shape. The agent reads
    `content` for the answer; the `citations` field lets the agent or the
    user verify the answer against the underlying PDF.
    """

    content: str
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
