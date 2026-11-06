"""Read pre-rename research without rewriting reports or duplicating vectors.

These legacy storage identifiers are intentional compatibility references;
new collections and manifests use the current product name.
"""
from qdrant_client.models import CreateAlias, CreateAliasOperation

LEGACY_PREFIX = 'codetrail_'
CURRENT_PREFIX = 'whythediff_'


def legacy_collection_name(name: str) -> str:
    return LEGACY_PREFIX+name[len(CURRENT_PREFIX):] if name.startswith(CURRENT_PREFIX) else name


def expose_legacy_collections(client):
    names = {item.name for item in client.get_collections().collections}
    operations = []
    for name in names:
        if name.startswith(LEGACY_PREFIX):
            alias = CURRENT_PREFIX+name[len(LEGACY_PREFIX):]
            if not client.collection_exists(alias):
                operations.append(CreateAliasOperation(create_alias=CreateAlias(collection_name=name, alias_name=alias)))
    if operations:
        client.update_collection_aliases(change_aliases_operations=operations)
