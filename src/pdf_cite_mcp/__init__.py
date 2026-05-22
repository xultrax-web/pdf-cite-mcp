"""pdf-cite-mcp — Model Context Protocol server for PDFs with precise citations.

Every extraction tool returns CitedContent — a chunk of text paired with one
or more Citation records that pin each fragment to a precise page+bbox+snippet
inside the source PDF. Agents can ground every claim back to a verifiable
rectangle on a verifiable page.
"""

from .citation import Citation, CitedContent

__version__ = "0.1.0"
__all__ = ["Citation", "CitedContent", "__version__"]
