"""Previously saved account research survives the product rename."""
import json
from contextlib import closing
from qdrant_client import QdrantClient, models
from agent.memory import FINDINGS_COLLECTION
from config import settings
from ingest.index import load_manifest, ensure_compatible, IndexConfigMismatch
from retrieval.clients import open_qdrant
from runtime import data_dir, user_workspace
import pytest


def test_old_vectors_are_reusable_without_cross_account_access(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    with user_workspace('1'):
        with closing(QdrantClient(path=str(data_dir()/'qdrant'))) as client:
            client.create_collection('codetrail_findings', vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
            client.upsert('codetrail_findings', points=[models.PointStruct(id=1, vector=[1.0, 0.0], payload={'saved':'research'})])
        for _ in range(2):
            with closing(open_qdrant()) as client:
                assert client.retrieve(FINDINGS_COLLECTION, ids=[1])[0].payload == {'saved':'research'}
                assert client.count(FINDINGS_COLLECTION, exact=True).count == 1
    with user_workspace('2'):
        with closing(open_qdrant()) as client:
            assert not client.collection_exists(FINDINGS_COLLECTION)


def test_old_manifest_still_enforces_embedding_compatibility(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    with user_workspace('1'):
        path = data_dir()/'index'/'codetrail_a_b_123.manifest.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'collection':'codetrail_a_b_123', 'embed_dim':3}))
        manifest = load_manifest('whythediff_a_b_123')
        assert manifest['collection'] == 'whythediff_a_b_123'
        with pytest.raises(IndexConfigMismatch):
            ensure_compatible(manifest, {'embed_dim':4})
    with user_workspace('2'):
        assert load_manifest('whythediff_a_b_123') is None
