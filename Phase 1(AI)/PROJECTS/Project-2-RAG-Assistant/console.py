"""Console helpers shared by the CLI entry points.

The Windows console defaults to the cp1252 code page, and our chunk text is real
Unicode (en dashes, accents in climbers' names). Printing that raw raises
UnicodeEncodeError and kills the command. Reconfiguring stdout with
errors="replace" means the CLI never dies on a character: anything the terminal
cannot render shows as a placeholder instead.
"""
from __future__ import annotations

import sys


def make_stdout_safe() -> None:
    """Stop CLIs crashing when printing characters the console cannot encode."""
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        # stdout is not a reconfigurable text stream (e.g. already redirected).
        pass
