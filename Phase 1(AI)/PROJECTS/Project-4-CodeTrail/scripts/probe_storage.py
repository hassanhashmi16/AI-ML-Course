"""Disposable storage probe: --init once, then --verify after a host restart.

Does not access accounts, provider APIs, or existing research. Leaves its small
fixture under DATA_DIR/.storage-probe so persistence can be verified later.
Never treats a successful local test as proof of a cloud bucket's behavior.
"""
import argparse
import os
import sqlite3
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portalocker
from qdrant_client import QdrantClient, models
from config import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--init', action='store_true')
    mode.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    root = settings.data_dir.resolve()/'.storage-probe'
    if root.resolve() != root:
        raise ValueError('refusing redirected probe directory')
    if args.init:
        root.mkdir(parents=True, exist_ok=False)
        with (root/'marker').open('x') as handle:
            handle.write(uuid.uuid4().hex)
            handle.flush()
            os.fsync(handle.fileno())
        with sqlite3.connect(root/'probe.sqlite', timeout=10) as db:
            db.execute('CREATE TABLE writes (id INTEGER PRIMARY KEY)')
        def write(number):
            with sqlite3.connect(root/'probe.sqlite', timeout=10) as db:
                db.execute('INSERT INTO writes VALUES (?)', (number,))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, range(12)))
        client = QdrantClient(path=str(root/'vectors'))
        try:
            client.create_collection('probe', vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
            client.upsert('probe', points=[models.PointStruct(id=1, vector=[1.0,0.0], payload={'fixture':'storage-probe'})], wait=True)
        finally:
            client.close()
    if len((root/'marker').read_text()) != 32:
        raise ValueError('probe marker missing or invalid')
    with sqlite3.connect(root/'probe.sqlite', timeout=10) as db:
        if db.execute('SELECT count(*) FROM writes').fetchone()[0] != 12:
            raise ValueError('SQLite writes did not survive')
    with portalocker.Lock(root/'probe.lock', timeout=0):
        try:
            with portalocker.Lock(root/'probe.lock', timeout=0):
                raise RuntimeError('filesystem did not enforce the exclusive lock')
        except portalocker.exceptions.LockException:
            pass
    client = QdrantClient(path=str(root/'vectors'))
    try:
        points = client.retrieve('probe', ids=[1])
        if not points or points[0].payload != {'fixture':'storage-probe'}:
            raise ValueError('Qdrant data did not survive')
    finally:
        client.close()
    print('Storage probe passed: marker, concurrent SQLite writes, exclusive lock, Qdrant reopen.')
    if args.init:
        print('Now restart the host and run --verify against the same storage mount.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Storage probe FAILED ('+type(exc).__name__+'). Do not open public traffic until resolved.', file=sys.stderr)
        raise SystemExit(1)
