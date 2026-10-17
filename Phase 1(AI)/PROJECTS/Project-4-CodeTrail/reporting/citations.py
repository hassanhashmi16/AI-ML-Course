"""Citation validation: a claim becomes real only when its evidence checks out.

Two checks, deliberately separate -- identity and quote:

  * **identity** -- the cited ``source_id`` exists among the inspected records;
  * **quote** -- the excerpt appears *verbatim* in that source's text.

Locating is exact first. A model quote that differs only by dropped markdown
backticks and collapsed whitespace is located tolerantly, and the quote that
gets stored is then **the exact source span**, not the model's rendering.
Wording changes still fail: a paraphrase or an altered quote has no span.

Line locations are derived from the quote's own position rather than trusted
from the model. A claim that fails either check is dropped and the reason is
kept: an answer with fewer, verifiable claims beats one with pretty citations.
"""

from __future__ import annotations

import re
from typing import Protocol

from models import Claim, ClaimLabel, SourceRecord, SupportingExcerpt


class DraftClaimLike(Protocol):
    """The shape a generated draft claim must have (avoids an import cycle)."""

    statement: str
    label: ClaimLabel
    source_id: str
    quote: str


def _line_range(text: str, start: int, length: int) -> tuple[int, int]:
    """1-based line numbers covering ``text[start:start+length]``."""
    start_line = text.count("\n", 0, start) + 1
    end_line = text.count("\n", 0, start + length) + 1
    return start_line, end_line


def _locate_tolerant(content: str, quote: str) -> tuple[int, int, str] | None:
    """Locate a quote ignoring markdown backticks and whitespace runs.

    Returns ``(start, end, exact_text)`` into the original content, so the
    stored quote is copied from the source rather than from the model.
    """
    normalized_chars: list[str] = []
    index_map: list[int] = []  # normalized position -> original position
    previous_space = False
    for index, char in enumerate(content):
        if char == "`":
            continue
        if char.isspace():
            if previous_space:
                continue
            normalized_chars.append(" ")
            index_map.append(index)
            previous_space = True
            continue
        normalized_chars.append(char)
        index_map.append(index)
        previous_space = False

    needle = re.sub(r"\s+", " ", quote.replace("`", "")).strip()
    if not needle:
        return None
    position = "".join(normalized_chars).find(needle)
    if position < 0:
        return None
    start = index_map[position]
    end = index_map[position + len(needle) - 1] + 1
    return start, end, content[start:end]


def locate_quote(record: SourceRecord, quote: str) -> tuple[int, int, str] | None:
    """Find the quote; return ``(start_line, end_line, exact_quote)`` or None."""
    position = record.content.find(quote)
    if position >= 0:
        start_line, end_line = _line_range(record.content, position, len(quote))
        return start_line, end_line, quote
    tolerant = _locate_tolerant(record.content, quote)
    if tolerant is None:
        return None
    start, end, exact = tolerant
    start_line, end_line = _line_range(record.content, start, end - start)
    return start_line, end_line, exact


def validate_claims(
    drafts: list[DraftClaimLike],
    records: dict[str, SourceRecord],
) -> tuple[list[Claim], list[str]]:
    """Convert draft claims into validated ``Claim`` objects; return (claims, issues).

    Issues name exactly what failed, so the caller can downgrade the report
    and tell the reader why rather than quietly losing a claim.
    """
    claims: list[Claim] = []
    issues: list[str] = []
    for draft in drafts:
        record = records.get(draft.source_id)
        if record is None:
            issues.append(f"unknown source_id: {draft.source_id}")
            continue
        located = locate_quote(record, draft.quote)
        if located is None:
            issues.append(
                f"quote not found verbatim in {draft.source_id}: {draft.quote[:60]!r}"
            )
            continue
        start_line, end_line, exact_quote = located
        try:
            claim = Claim(
                statement=draft.statement,
                label=draft.label,
                excerpts=[
                    SupportingExcerpt(
                        source_id=draft.source_id,
                        quote=exact_quote,
                        start_line=start_line,
                        end_line=end_line,
                    )
                ],
            )
        except ValueError as exc:  # e.g. an "unknown" label carrying a quote
            issues.append(f"rejected claim citing {draft.source_id}: {exc}")
            continue
        claims.append(claim)
    return claims, issues
