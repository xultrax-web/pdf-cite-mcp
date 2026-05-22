# pdf-cite-mcp

**Cite your sources.** A Model Context Protocol server for PDFs that returns precise `{page, bbox, snippet}` citations on every extraction.

[![PyPI](https://img.shields.io/pypi/v/pdf-cite-mcp)](https://pypi.org/project/pdf-cite-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why this exists

Most PDF extraction returns text. **pdf-cite-mcp returns text AND the rectangle on the page where it came from.** Every tool's response includes `{page, bbox, snippet, confidence}` citations so an agent can ground every claim in a verifiable region — and a human can double-click to confirm in two seconds.

Built for grounded answers across the hard cases:

- **Bbox citations on every tool.** Not a special mode — the contract is the data model. Even BM25 search results return with the page+bbox of the matched snippet.
- **Tesseract OCR with per-word confidence.** Scanned PDFs are first-class. `pdf_info` detects pages with no text layer; `pdf_ocr_pages` renders them at configurable DPI and returns citations whose `confidence` reflects Tesseract's per-word score.
- **Hybrid BM25 search via SQLite FTS5.** Phrase queries, boolean ops, prefix matching. Each result carries a citation.
- **Table extraction via pdfplumber.** Detected tables become markdown with bbox citations spanning the table region.
- **Vision-ready raster.** `pdf_render_page` returns a base64 PNG for vision-capable agents — for charts, figures, layout, signatures.
- **SSRF-safe URL fetch.** `file_path` accepts `http(s)://` URLs; private-IP rejection + redirect blocking + content-type allowlist + 50 MB size cap before any bytes hit disk.

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

## VS Code (Copilot Chat)

VS Code has native MCP support read by GitHub Copilot Chat. Add `.vscode/mcp.json` (workspace) or edit `mcp.json` via User Settings:

```json
{
  "servers": {
    "pdf-cite": {
      "type": "stdio",
      "command": "uvx",
      "args": ["pdf-cite-mcp"]
    }
  }
}
```

> **Two VS Code paths.** Cline is a third-party AI extension with its own MCP server UI — use the Cline-format snippet for that. Copilot Chat is VS Code's native chat that reads `.vscode/mcp.json` directly. Pick whichever matches your assistant.

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
| `pdf_search` | BM25 via SQLite FTS5 · phrase / boolean / prefix · citations |
| `pdf_quote` | exact phrase → word-union bbox citation · the killer tool |
| `pdf_extract_tables` | tables → markdown with bbox citations |
| `pdf_ocr_pages` | Tesseract OCR with per-word confidence |
| `pdf_render_page` | page → base64 PNG for vision models |
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
