"""Step 3 deliverable: turn raw article text into clean, section-tagged records.

Input:  the cached plain-text articles in data/raw/*.txt (from Step 2).
Output: in-memory `DocumentChunk` records, one per useful section.

This file is the "garbage in, garbage out" gate of the whole system. If the text
that reaches chunking still carries bibliography lines, ISBNs, and "See also"
links, no amount of clever retrieval can repair it: the noise competes with real
content for the same few slots. So this step does exactly three jobs:

  1. Split each article on its `== Heading ==` markers. That gives us (a) a
     section name to keep as a breadcrumb on every chunk, and (b) the ability to
     drop whole sections at once.
  2. Drop the sections that are pure apparatus: References, See also, External
     links, Bibliography, and friends. They contain no answer to any real
     question, but they are full of proper nouns and numbers that would score
     highly in keyword search.
  3. Normalize the remaining text and hash it. The hash is what makes Step 7's
     re-ingest idempotent: same text, same hash, skip.

It reuses the clean / hash / dedupe ideas from the Step 21 ingestion deliverable,
adapted from PDF pages to plain-text articles.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from config import RAW_DIR

# The name we give the text that appears before the first heading. Every article
# opens with a lead paragraph (the summary); it has no heading of its own, so we
# label it explicitly rather than leaving the section blank.
LEAD_SECTION = "Introduction"

# A heading line and nothing else: two or more '=' on each side, same count on
# both sides (the backreference \1 enforces that, so '== X ===' is not a match).
HEADING_RE = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$")

# Sections that are apparatus, not content. Compared lowercased and trimmed, so
# "See also" and "See Also" both match. Dropping these is the single highest
# value-for-effort cleanup in the whole pipeline.
DROP_SECTIONS = {
    "see also",
    "references",
    "notes",
    "notes and references",
    "bibliography",
    "external links",
    "further reading",
    "sources",
    "footnotes",
}


@dataclass
class DocumentChunk:
    """One section of one article.

    At this stage "chunk" means "section": a whole heading's worth of text. Step 4
    splits these further into fixed-size, overlapping chunks for embedding. We
    keep the section name on the record because it becomes the citation label the
    user sees ("K2 > Climbing history").
    """

    text: str
    source: str        # the file it came from, e.g. "k2.txt"
    section: str       # heading path, e.g. "Climbing routes and difficulties > Abruzzi Spur"
    content_hash: str = ""

    def __post_init__(self) -> None:
        # Fill the hash automatically so no caller can forget to set it.
        if not self.content_hash:
            self.content_hash = hash_text(self.text)


def hash_text(text: str) -> str:
    """Stable fingerprint of a piece of text. Used for dedupe and idempotency."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean(text: str) -> str:
    """Normalize text without flattening its paragraph structure.

    This differs from Step 21's clean() in one deliberate way. Step 21 collapsed
    *all* whitespace, newlines included, to single spaces, which is right for a
    PDF page but would squash a whole article into one enormous line. Here we
    collapse runs of spaces and tabs but keep newlines, so Step 4 can still tell
    paragraphs apart when it decides where to split.
    """
    text = text.replace("\u00a0", " ")                # non-breaking space -> space
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)  # zero-width characters
    text = re.sub(r"\x00", "", text)                  # null bytes from bad exports
    text = re.sub(r"[ \t]+", " ", text)               # collapse spaces/tabs only
    text = re.sub(r" *\n *", "\n", text)              # trim space around newlines
    text = re.sub(r"\n{3,}", "\n\n", text)            # 3+ newlines -> one blank line
    return text.strip()


def is_boilerplate(section: str) -> bool:
    """True if a section is apparatus we never want to retrieve from.

    Checks only the final segment of a breadcrumb, so a nested
    "Climbing history > See also" is still recognised as boilerplate.
    """
    leaf = section.split(">")[-1].strip().lower()
    return leaf in DROP_SECTIONS


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split article text into (breadcrumb, body) pairs.

    The heading level is encoded in the number of '=' signs: '==' is a section,
    '===' is a subsection. We keep a stack of the headings currently open and join
    it with ' > ', so a section knows where it sits in the outline, e.g.
    "Climbing routes and difficulties > Abruzzi Spur". That path is the label the
    user will see beside a citation, and it is what lets a chunk pulled from a
    subsection still make sense on its own.

    Text before the first heading becomes (LEAD_SECTION, ...).
    """
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []  # open headings, outermost first, as (level, title)
    buffer: list[str] = []
    current = LEAD_SECTION

    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            # A new heading: flush the section we were accumulating.
            sections.append((current, "\n".join(buffer)))

            level = len(match.group(1))
            title = match.group(2).strip()
            # Pop any open heading at the same or deeper level: the new heading
            # replaces it and everything below it in the outline.
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current = " > ".join(heading for _, heading in stack)
            buffer = []
        else:
            buffer.append(line)

    sections.append((current, "\n".join(buffer)))  # flush the last section
    return sections


def dedupe(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    """Drop byte-identical chunks, keeping the first occurrence.

    Two sections in one article can be identical after cleaning (a stray repeated
    paragraph, a duplicated timeline row). Inserting both wastes embedding calls
    and gives the retriever two identical hits instead of one real one.
    """
    seen: set[str] = set()
    kept: list[DocumentChunk] = []
    for chunk in chunks:
        if chunk.content_hash in seen:
            continue
        seen.add(chunk.content_hash)
        kept.append(chunk)
    return kept


def parse_document(path: Path) -> list[DocumentChunk]:
    """Parse one raw article file into clean, non-boilerplate section chunks."""
    source = path.name
    raw = path.read_text(encoding="utf-8")

    chunks: list[DocumentChunk] = []
    for title, body in split_sections(raw):
        if is_boilerplate(title):
            continue                 # drop References / See also / etc.
        body = clean(body)
        if not body:
            continue                 # drop headings with no body (empty sections)
        chunks.append(DocumentChunk(text=body, source=source, section=title))

    return dedupe(chunks)


def parse_corpus() -> list[DocumentChunk]:
    """Parse every cached article into one flat list of section chunks."""
    chunks: list[DocumentChunk] = []
    for path in sorted(RAW_DIR.glob("*.txt")):
        chunks.extend(parse_document(path))
    return chunks


def main() -> None:
    """Parse the corpus and print what cleaning actually removed."""
    paths = sorted(RAW_DIR.glob("*.txt"))
    if not paths:
        raise SystemExit(
            f"no .txt files in {RAW_DIR} - run `python -m ingest.fetch_corpus` first"
        )

    total_kept = 0
    total_dropped = 0
    print(f"{'file':<26}{'kept':>6}{'dropped':>9}{'chars':>10}")
    print("-" * 51)

    for path in paths:
        sections = split_sections(path.read_text(encoding="utf-8"))
        dropped = sum(1 for title, _ in sections if is_boilerplate(title))
        chunks = parse_document(path)

        total_kept += len(chunks)
        total_dropped += dropped
        chars = sum(len(chunk.text) for chunk in chunks)
        print(f"{path.name:<26}{len(chunks):>6}{dropped:>9}{chars:>10,}")

    print("-" * 51)
    print(
        f"{len(paths)} files -> {total_kept} sections kept, "
        f"{total_dropped} boilerplate sections dropped"
    )

    # Sanity check: show the section titles we ended up with for one article.
    print("\nsections in k2.txt:")
    for chunk in parse_document(RAW_DIR / "k2.txt"):
        print(f"  - {chunk.section}")


if __name__ == "__main__":
    main()
