"""CLI entry point for pdf-cite-mcp.

Invoked with no args (or `serve`), runs the MCP server over stdio so MCP
clients can spawn it. The other sub-commands are operator-grade convenience
tools — `info`, `read`, and (in upcoming phases) `quote`, `doctor`, etc.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    p = argparse.ArgumentParser(
        prog="pdf-cite-mcp",
        description="MCP server for PDFs with precise page+bbox citations.",
    )
    p.add_argument("--version", action="version", version=f"pdf-cite-mcp {__version__}")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("serve", help="Run MCP server over stdio (default if no command)")

    info = sub.add_parser("info", help="Print PDF info as JSON")
    info.add_argument("file")

    read = sub.add_parser("read", help="Read pages and print cited content as JSON")
    read.add_argument("file")
    read.add_argument(
        "pages",
        help="Comma-separated 1-indexed page numbers (e.g. '1,3,5')",
    )

    search = sub.add_parser("search", help="BM25 search a PDF and print cited matches")
    search.add_argument("file")
    search.add_argument("query", help="FTS5 query string")
    search.add_argument("-k", type=int, default=5, help="Max results (default 5)")

    quote = sub.add_parser(
        "quote",
        help="Find an exact quote in a PDF and print precise bbox citations",
    )
    quote.add_argument("file")
    quote.add_argument("text", help="The phrase to locate")

    ocr = sub.add_parser("ocr", help="OCR specified pages and print cited text")
    ocr.add_argument("file")
    ocr.add_argument(
        "pages", help="Comma-separated 1-indexed page numbers (e.g. '1,3,5')"
    )
    ocr.add_argument("--dpi", type=int, default=200, help="Render DPI (default 200)")

    tables = sub.add_parser(
        "tables",
        help="Extract every table on a page as markdown + bbox citations",
    )
    tables.add_argument("file")
    tables.add_argument("page", type=int, help="1-indexed page number")

    render = sub.add_parser(
        "render",
        help="Render a PDF page to PNG (base64) for vision models",
    )
    render.add_argument("file")
    render.add_argument("page", type=int)
    render.add_argument("--dpi", type=int, default=150, help="Render DPI (default 150)")
    render.add_argument(
        "--out",
        help="Optional output PNG path; when set, writes the decoded image and omits data_base64",
    )

    sub.add_parser("doctor", help="Health check: Python, deps, OCR, tables, cache")
    sub.add_parser("cache-stats", help="Cache stats: doc count, page count, size")
    cache_clear = sub.add_parser(
        "cache-clear", help="Clear cache (all docs unless --sha256 given)"
    )
    cache_clear.add_argument(
        "--sha256", help="Clear only the document with this sha256"
    )

    args = p.parse_args()

    if args.cmd is None or args.cmd == "serve":
        from .server import run_stdio

        run_stdio()
        return 0

    if args.cmd == "info":
        from .server import pdf_info

        _print_json(pdf_info(args.file))
        return 0

    if args.cmd == "read":
        from .server import pdf_read_pages

        page_list = [int(x) for x in args.pages.split(",") if x.strip()]
        _print_json(pdf_read_pages(args.file, page_list))
        return 0

    if args.cmd == "search":
        from .server import pdf_search

        _print_json(pdf_search(args.file, args.query, args.k))
        return 0

    if args.cmd == "quote":
        from .server import pdf_quote

        _print_json(pdf_quote(args.file, args.text))
        return 0

    if args.cmd == "ocr":
        from .server import pdf_ocr_pages

        page_list = [int(x) for x in args.pages.split(",") if x.strip()]
        _print_json(pdf_ocr_pages(args.file, page_list, args.dpi))
        return 0

    if args.cmd == "tables":
        from .server import pdf_extract_tables

        _print_json(pdf_extract_tables(args.file, args.page))
        return 0

    if args.cmd == "render":
        import base64
        from pathlib import Path as _P

        from .server import pdf_render_page

        result = pdf_render_page(args.file, args.page, args.dpi)
        if args.out:
            out_path = _P(args.out).expanduser()
            out_path.write_bytes(base64.b64decode(result["data_base64"]))
            del result["data_base64"]
            result["out"] = str(out_path)
        _print_json(result)
        return 0

    if args.cmd == "doctor":
        from .server import pdf_doctor

        _print_json(pdf_doctor())
        return 0

    if args.cmd == "cache-stats":
        from .server import pdf_cache_stats

        _print_json(pdf_cache_stats())
        return 0

    if args.cmd == "cache-clear":
        from .server import pdf_cache_clear

        _print_json(pdf_cache_clear(args.sha256))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
