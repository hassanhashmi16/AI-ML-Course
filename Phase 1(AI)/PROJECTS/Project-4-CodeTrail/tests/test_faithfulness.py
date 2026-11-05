import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from eval.score_faithfulness import sample_data, score_directory
from models import Report

def test_unknown_is_not_assigned_perfect_faithfulness():
    assert sample_data(SimpleNamespace(claims=[]), {}) is None

def test_missing_or_changed_evidence_is_not_silently_scored():
    import pytest
    excerpt = SimpleNamespace(source_id='missing', quote='verbatim')
    report = SimpleNamespace(claims=[SimpleNamespace(excerpts=[excerpt])])
    with pytest.raises(ValueError): sample_data(report, {})
    with pytest.raises(ValueError): sample_data(report, {'missing':SimpleNamespace(content='changed')})
