"""Allow `python -m pdf_cite_mcp` to invoke the CLI."""

import sys

from .cli import main

sys.exit(main())
