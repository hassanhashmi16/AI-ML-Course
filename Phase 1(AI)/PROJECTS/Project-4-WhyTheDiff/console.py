"""Console helpers shared by CLIs and checks.

Model output can contain characters a legacy Windows console (cp1252) cannot
encode -- a smart quote or non-breaking hyphen would otherwise crash a print
after the work succeeded. Reconfiguring the streams to UTF-8 with replacement
keeps command output from failing on punctuation.
"""

from __future__ import annotations

import sys


def make_stdout_safe() -> None:
    """Best-effort UTF-8 console output for model-generated text."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
