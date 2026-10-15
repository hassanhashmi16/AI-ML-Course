"""Console helpers shared by the CLI entry point.

The Windows console defaults to the cp1252 code page, and this agent prints real
Unicode: em dashes from web pages, accented names, curly quotes, the occasional
emoji from a headline. Printing those raw raises `UnicodeEncodeError` and kills
the command mid-run — after the tokens are already spent.

Reconfiguring stdout with `errors="replace"` means the CLI never dies on a
character: anything the terminal cannot render shows as a placeholder instead.
Same fix Project 2 used for the same reason.
"""
from __future__ import annotations

import sys


def make_stdout_safe() -> None:
    """Stop the CLI crashing when printing characters the console cannot encode."""
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        # stdout is not a reconfigurable text stream (e.g. already redirected).
        pass
