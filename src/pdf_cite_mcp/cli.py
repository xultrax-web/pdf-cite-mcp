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

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
