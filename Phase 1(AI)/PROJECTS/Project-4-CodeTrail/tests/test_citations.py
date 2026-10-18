"""Citation tests: identity, verbatim quotes, and the markdown-tolerant locate."""

from generation.answer import DraftClaim
from models import ClaimLabel, SourceRecord, SourceKind
from reporting.citations import validate_claims


def _record(content: str) -> SourceRecord:
    return SourceRecord(
        source_id="src-1",
        kind=SourceKind.FILE,
        repository="https://github.com/a/b",
        snapshot_sha="a" * 40,
        url="https://example.test/file",
        content=content,
    )


def _draft(quote: str, source_id: str = "src-1") -> DraftClaim:
    return DraftClaim(
        statement="a statement",
        label=ClaimLabel.DOCUMENTED,
        source_id=source_id,
        quote=quote,
    )


def test_exact_quote_is_validated():
    record = _record("Alpha beta gamma.")
    claims, issues = validate_claims([_draft("Alpha beta")], {"src-1": record})
    assert issues == []
    assert claims[0].excerpts[0].quote == "Alpha beta"


def test_quote_missing_markdown_repairs_to_the_exact_span():
    record = _record("`LocalStack` incurs overhead on every `push`.")
    claims, issues = validate_claims(
        [_draft("LocalStack incurs overhead on every push.")], {"src-1": record}
    )
    assert issues == []
    # The stored quote is copied from the source, not from the model.
    assert claims[0].excerpts[0].quote == "`LocalStack` incurs overhead on every `push`."


def test_altered_quote_is_rejected():
    record = _record("Alpha beta gamma.")
    _, issues = validate_claims([_draft("Alpha beta gamma (altered)")], {"src-1": record})
    assert any("not found verbatim" in issue for issue in issues)


def test_paraphrased_quote_is_rejected():
    record = _record("Alpha beta gamma.")
    _, issues = validate_claims([_draft("Alpha and beta and gamma")], {"src-1": record})
    assert any("not found verbatim" in issue for issue in issues)


def test_unknown_source_id_is_rejected():
    _, issues = validate_claims([_draft("Alpha")], {})
    assert any("unknown source_id" in issue for issue in issues)
