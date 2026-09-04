"""Demo: making a side-effecting tool safe to retry with an idempotency key."""

import hashlib


class InMemoryDedupe:
    """A minimal key -> result store. Stands in for a real DB's dedupe table."""

    def __init__(self):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value


def write_row(dedupe, execute, table: str, row_id) -> str:
    """Write a row, deduping retries of the same logical operation.

    `execute` is the actual side effect (INSERT, send, charge). It runs at most
    once per (table, row_id), no matter how many times write_row is called.
    """
    key = _idempotency_key(table, row_id)
    existing = dedupe.get(key)
    if existing is not None:
        return existing
    result = execute(table, row_id)
    dedupe.set(key, result)
    return result


def _idempotency_key(table: str, row_id) -> str:
    return hashlib.sha256(f"{table}:{row_id}".encode()).hexdigest()
