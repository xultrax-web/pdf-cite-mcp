# pdf-cite-mcp

**Cite your sources.** A Model Context Protocol server for PDFs that returns precise `{page, bbox, snippet}` citations on every extraction.

[![PyPI](https://img.shields.io/pypi/v/pdf-cite-mcp)](https://pypi.org/project/pdf-cite-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why this exists

Every other PDF MCP returns text. This one returns text **and the rectangle on the page where it came from** — so the agent can ground every claim with a verifiable citation.

| | Other PDF MCPs | pdf-cite-mcp |
|--|--|--|
| Page-level extraction | yes | yes |
| Bounding-box citations | no | **yes** |
| OCR for scanned PDFs | some | yes |
| Table extraction | some | yes (markdown + cell cites) |
| Forms + annotations | rare | yes (v0.4) |
| Multi-document librarian | none | yes (v0.2) |
| Vision-model fallback | none | yes (v0.3) |

## Install

```bash
uvx pdf-cite-mcp
```

(`uvx` ships with [uv](https://docs.astral.sh/uv/). No clone, no manual install.)

## Quick start · Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pdf-cite": {
      "command": "uvx",
      "args": ["pdf-cite-mcp"]
    }
  }
}
```

Cursor, Claude Code, Cline, and Continue.dev use the same shape — see [docs/clients.md](docs/clients.md) (coming with v0.1.0 release).

## The citation contract

Every extraction tool returns this shape:

```json
{
  "content": "Operator-grade tolerance is ±0.5%.",
  "citations": [
    {
      "page": 5,
      "bbox": [72.0, 218.4, 540.0, 234.0],
      "snippet": "Operator-grade tolerance is ±0.5%.",
      "confidence": 0.98
    }
  ],
  "metadata": { "sha256": "...", "source": "..." }
}
```

- `page` — 1-indexed page number
- `bbox` — `[x0, y0, x1, y1]` in PDF points (1/72 inch), origin top-left
- `snippet` — the exact text inside that rectangle
- `confidence` — 1.0 for native PDF text, lower for OCR'd or vision-recovered content

## Tools (v0.1)

| Tool | What it does |
|--|--|
| `pdf_info` | pages, metadata, TOC, scanned-page detection |
| `pdf_read_pages` | paginated read with page-level citations |
| `pdf_search` | hybrid search → citations *(v0.1.x)* |
| `pdf_quote` | "where in the PDF does it say X?" → precise word-level bbox *(v0.1.x)* |
| `pdf_extract_table` | table → markdown with cell citations *(v0.1.x)* |
| `pdf_render_page` | page → PNG for vision models *(v0.1.x)* |
| `pdf_doctor` | health check on libs, OCR, cache |
| `pdf_cache_stats` / `pdf_cache_clear` | operator-grade cache ops |

## Roadmap

| Version | Wedge |
|--|--|
| **v0.1** | Citations + core extraction *(this release)* |
| v0.2 | Multi-document librarian — query across a directory of PDFs |
| v0.3 | Vision-model fallback router — VLM rescue for adversarial pages |
| v0.4 | Forms + annotations — fillable PDFs, highlights, comments |

## Environment variables

| Variable | Default | Purpose |
|--|--|--|
| `PDF_CITE_CACHE_DIR` | `~/.pdf-cite` | Override cache directory |

## Architecture

- **PyMuPDF** as the primary text+bbox engine (per-character coordinates)
- **SQLite cache** keyed by SHA-256 of file content (parse once, reuse forever)
- **Tesseract** (optional) for OCR on scanned pages
- **pdfplumber** (optional) for hard tables
- **FastMCP** transport (stdio default)

## License

MIT
