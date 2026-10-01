"""Step 4 deliverable: split sections into embeddable, self-describing chunks.

Input:  the section records from Step 3 (`ingest/parse.py`).
Output: `Chunk` records, each small enough to embed, overlapping its neighbours,
        and carrying the section breadcrumb in its own text.

Why chunking is a real decision and not a formality: a chunk is the unit of
retrieval. Too big and the embedding averages several ideas into a blur, so the
match is vague and the LLM gets more noise than signal. Too small and the chunk
loses the context that made it meaningful. Step 22's lesson is that bad chunking
silently degrades everything downstream: the pipeline runs, the answers just get
quietly worse.

Two choices here:

  * Structure first. We only ever cut inside a section, never across one, because
    a section is a coherent topic. Cutting between "Height" and "Geology" would
    produce a chunk that is half of each and good for neither.
  * Overlap. Adjacent chunks share ~15% of their text, so a sentence that lands
    on a boundary is still fully present in one of them.

And one thing we prepend: the section breadcrumb. Every chunk starts with its
path, e.g. "K2 > Climbing history > Winter expeditions". That costs a few tokens
and makes the chunk self-describing: useful for retrieval (the heading words
help match topical queries) and essential for the citation the user sees.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from config import CHUNK_OVERLAP_TOKENS, CHUNK_TOKENS, RAW_DIR
from ingest.parse import DocumentChunk, parse_corpus, parse_document

# Coarse-to-fine. We try to break the text at the first separator present; if a
# resulting piece is still too big, we recurse to the next one. Paragraphs come
# before sentences, sentences before clauses, and words are the last resort
# before a blind character cut.
SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]

# Rough English average. See count_tokens() for why an estimate is fine here.
CHARS_PER_TOKEN = 4


def count_tokens(text: str) -> int:
    """Estimate the token count of a piece of text.

    This is an approximation on purpose. Chunk boundaries are approximate anyway
    (nobody can tell a 500-token chunk from a 520-token one), and every model's
    tokenizer differs, so paying for exactness here buys nothing. English prose
    runs about 4 characters per token, within ~10%. If a model ever needs exact
    counts, this one function is the only thing to replace.
    """
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class Chunk:
    """One embeddable piece of a section.

    `text` is what gets embedded AND what the user eventually sees as a source,
    so it includes the breadcrumb line. `index` is the position within its
    section, which lets callers reassemble neighbours or grow context later.
    """

    text: str
    source: str        # "k2.txt"
    section: str       # "Climbing history > Winter expeditions"
    index: int         # 0-based position within the section
    tokens: int
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                self.text.encode("utf-8")
            ).hexdigest()


def _hard_cut(text: str, target: int) -> list[str]:
    """Last resort: slice by characters when no separator can break the text.

    Only reachable for pathological input (a wall of text with no punctuation or
    spaces). It guarantees termination and that no piece exceeds the target.
    """
    size = max(1, target * CHARS_PER_TOKEN)
    return [text[i : i + size] for i in range(0, len(text), size)]


def _split_recursive(text: str, separators: list[str], target: int) -> list[str]:
    """Break text into pieces that each fit within `target` tokens.

    Walks the separator list coarse-to-fine. The separator is re-attached to each
    piece as we split so no characters are lost.
    """
    if count_tokens(text) <= target:
        return [text]  # already small enough: this is a leaf

    if not separators:
        return _hard_cut(text, target)  # no separators left: brute force

    sep, rest = separators[0], separators[1:]
    parts = text.split(sep)

    if len(parts) == 1:
        # This separator does not occur; fall through to a finer one.
        return _split_recursive(text, rest, target)

    pieces: list[str] = []
    for i, part in enumerate(parts):
        # Put the separator back on everything but the final part.
        piece = part + sep if i < len(parts) - 1 else part
        if not piece:
            continue
        if count_tokens(piece) <= target:
            pieces.append(piece)
        else:
            pieces.extend(_split_recursive(piece, rest, target))
    return pieces


def _tail_text(text: str, overlap: int) -> str:
    """Return roughly `overlap` tokens from the end of `text`.

    We slice characters, not separator-pieces, because a single piece can already
    be as large as the whole target: overlap has to be able to cut *inside* one.
    (An earlier version only reused whole pieces, so on big sections, where every
    piece was ~target-sized, the overlap silently came out empty.) The cut is
    nudged to the next word boundary so the new chunk does not start mid-word.
    """
    chars = overlap * CHARS_PER_TOKEN
    if chars <= 0:
        return ""
    tail = text[-chars:]
    boundary = tail.find(" ")
    if boundary != -1:
        tail = tail[boundary + 1 :]
    return tail.rstrip() + " "


def _pack(pieces: list[str], target: int, overlap: int) -> list[str]:
    """Greedily pack pieces into chunks, carrying an overlap into each new chunk."""
    chunks: list[str] = []
    current = ""
    current_tokens = 0

    for piece in pieces:
        piece_tokens = count_tokens(piece)
        if current and current_tokens + piece_tokens > target:
            # Current chunk is full: close it, then seed the next one with the
            # tail of this one so a sentence on the boundary survives in both.
            chunks.append(current.strip())
            current = _tail_text(current, overlap)
            current_tokens = count_tokens(current)
        current += piece
        current_tokens += piece_tokens

    if current.strip():
        chunks.append(current.strip())

    return [chunk for chunk in chunks if chunk]


def split_text(text: str, target: int, overlap: int) -> list[str]:
    """Public entry point: text -> list of overlapping, size-bounded pieces."""
    return _pack(_split_recursive(text, SEPARATORS, target), target, overlap)


def chunk_section(section: DocumentChunk) -> list[Chunk]:
    """Split one section into chunks, each stamped with the section breadcrumb.

    The breadcrumb is added *after* splitting, not before, so its tokens never
    count toward the size decision and it can never be cut in half.
    """
    chunks: list[Chunk] = []
    for index, piece in enumerate(
        split_text(section.text, CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS)
    ):
        text = f"{section.section}\n{piece}".strip()
        chunks.append(
            Chunk(
                text=text,
                source=section.source,
                section=section.section,
                index=index,
                tokens=count_tokens(text),
            )
        )
    return chunks


def chunk_corpus() -> list[Chunk]:
    """Parse the whole corpus (Step 3) and chunk every section."""
    chunks: list[Chunk] = []
    for section in parse_corpus():
        chunks.extend(chunk_section(section))
    return chunks


def main() -> None:
    """Chunk the corpus and print the size distribution we ended up with."""
    sections = parse_corpus()

    chunks: list[Chunk] = []
    split_sections = 0
    for section in sections:
        produced = chunk_section(section)
        if len(produced) > 1:
            split_sections += 1
        chunks.extend(produced)

    tokens = [chunk.tokens for chunk in chunks]
    print(f"{len(sections)} sections -> {len(chunks)} chunks")
    print(f"sections that needed splitting: {split_sections}")
    print(
        f"tokens per chunk: min {min(tokens)}  avg {sum(tokens) // len(tokens)}  "
        f"max {max(tokens)}  (target {CHUNK_TOKENS})"
    )

    # Show one real chunk end to end, so the breadcrumb + overlap are visible.
    sample = None
    for section in parse_document(RAW_DIR / "k2.txt"):
        if "Winter expeditions" in section.section:
            sample = chunk_section(section)[0]
            break

    if sample:
        print("\nsample chunk (k2.txt):")
        print(f"  section: {sample.section}")
        print(f"  tokens:  {sample.tokens}")
        print(f"  text:    {sample.text[:220]}...")

    # Prove the overlap is real: the end of one chunk must reappear at the start
    # of the next. The overlap window is CHUNK_OVERLAP_TOKENS long, so a short
    # probe taken from the end of chunk 0 should be found inside chunk 1.
    for section in parse_document(RAW_DIR / "k2.txt"):
        produced = chunk_section(section)
        if len(produced) >= 2:
            probe = produced[0].text[-60:].strip()
            print(f"\noverlap check ({section.section}):")
            print(f"  chunk 0 ends with: ...{probe}")
            print(f"  found inside chunk 1? {probe in produced[1].text}")
            break


if __name__ == "__main__":
    main()
