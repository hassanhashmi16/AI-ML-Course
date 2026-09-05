"""Unit tests for the Step 21 ingestion pipeline. No network calls."""

import ingest
from ingest import DocumentChunk


def test_clean_normalizes_non_breaking_spaces():
    assert ingest.clean("hello\u00a0world") == "hello world"


def test_clean_strips_zero_width_and_control_chars():
    assert ingest.clean("\x00a\u200bb\u200dc") == "abc"


def test_clean_collapses_whitespace():
    assert ingest.clean("a\n\n  b\t c") == "a b c"


def test_dedupe_collapses_identical_chunks():
    chunks = [
        DocumentChunk(text="same text", source="a", page=1),
        DocumentChunk(text="same text", source="a", page=2),
        DocumentChunk(text="different", source="a", page=3),
    ]
    result = ingest.dedupe(chunks)
    assert [c.page for c in result] == [1, 3]


def test_parse_attaches_source_and_page_metadata():
    def fake_extractor(path):
        return [
            (1, "first page text"),
            (2, "second page text"),
        ]

    chunks = ingest.parse("dir/report.pdf", extractor=fake_extractor)
    assert [c.page for c in chunks] == [1, 2]
    assert all(c.source == "report.pdf" for c in chunks)
    assert all(c.content_hash for c in chunks)


def test_parse_cleans_before_attaching():
    def fake_extractor(path):
        return [(1, "a\u00a0b\u00a0c")]

    chunks = ingest.parse("x.pdf", extractor=fake_extractor)
    assert chunks[0].text == "a b c"


def test_reingest_skips_unchanged_file(tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("hello")
    state = {str(p): ingest.file_hash(str(p))}

    added, skipped, old = ingest.reingest(str(p), state)
    assert (added, skipped, old) == (0, 1, None)


def test_reingest_returns_old_hash_for_delete_on_change(tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("v1")
    state = {str(p): "stale-hash"}  # forces a change

    added, skipped, old = ingest.reingest(
        str(p), state, extractor=lambda path: [(1, "v1 content")]
    )
    assert added == 1
    assert skipped == 0
    assert old == "stale-hash"  # caller deletes old chunks by this id
    assert state[str(p)] == ingest.file_hash(str(p))
