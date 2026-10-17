"""Citation validation: a claim becomes real only when its evidence checks out.

Two checks, deliberately separate -- identity and quote:

  * **identity** -- the cited ``source_id`` exists among the inspected records;
  * **quote** -- the excerpt appears *verbatim* in that source's text.

Line locations are derived from the quote's own position rather than trusted
from the model. A claim that fails either check is dropped and the reason is
kept: an answer with fewer, verifiable claims beats one with pretty citations.
"""

from __future__ import annotations

from typing import Protocol

from models import Claim, ClaimLabel, SourceRecord, SupportingExcerpt


class DraftClaimLike(Protocol):
    """The shape a generated draft claim must have (avoids an import cycle)."""

    statement: str
    label: ClaimLabel
    source_id: str
    quote: str


def locate_quote(record: SourceRecord, quote: str) -> tuple[int, int] | None:
    """Find the quote verbatim; return its (start_line, end_line), or None."""
    position = record.content.find(quote)
    if position < 0:
        return None
    start_line = record.content.count("\n", 0, position) + 1
    end_line = record.content.count("\n", 0, position + len(quote)) + 1
    return start_line, end_line


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
        location = locate_quote(record, draft.quote)
        if location is None:
            issues.append(
                f"quote not found verbatim in {draft.source_id}: {draft.quote[:60]!r}"
            )
            continue
        start_line, end_line = location
        try:
            claim = Claim(
                statement=draft.statement,
                label=draft.label,
                excerpts=[
                    SupportingExcerpt(
                        source_id=draft.source_id,
                        quote=draft.quote,
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
