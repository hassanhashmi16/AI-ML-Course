"""Account erasure with durable intent and a lease shared with job processes."""
import hashlib
import logging
import shutil
import time
from pathlib import Path

import portalocker

from api.store import AccountBusy
from config import settings


def workspace_lease(root: Path, owner: str):
    if not owner.isascii() or not owner.isdecimal():
        raise ValueError('invalid account id')
    directory = root / '.workspace-locks'
    directory.mkdir(parents=True, exist_ok=True)
    # Keep the lock outside the erased directory, including after releasing it.
    # Unlinking it could let two processes lock different inodes for one owner.
    name = hashlib.sha256(owner.encode()).hexdigest()+'.lock'
    return portalocker.Lock(directory / name, timeout=0)


def erase_workspace(root: Path, owner: str):
    """Only erase one validated direct child of the configured users directory."""
    if not owner.isascii() or not owner.isdecimal():
        raise ValueError('invalid account id')
    root = root.resolve()
    users = root / 'users'
    target = users / owner
    # Validate absolute targets before recursive deletion, including junctions.
    if users.resolve() != users or target.resolve() != target:
        raise ValueError('refusing redirected account storage')
    if not target.is_relative_to(root) or target.parent != users:
        raise ValueError('account storage escaped its root')
    if target.exists():
        shutil.rmtree(target)


def delete_account(store, owner, *, session_token):
    try:
        with workspace_lease(store.path.parent, owner):
            store.request_deletion(owner, session_token=session_token)
            # Failure leaves a tombstone. Sessions remain revoked and login is
            # blocked until the worker completes cleanup, including after restart.
            try:
                erase_workspace(store.path.parent, owner)
            except (OSError, ValueError):
                logging.getLogger(__name__).warning('Account cleanup pending')
                return False
            store.finish_deletion(owner)
            return True
    except portalocker.exceptions.LockException:
        raise AccountBusy('Your investigation is still releasing its files. Try again shortly.') from None


def maintain_accounts(store):
    """Called between jobs; retention is opt-in and pending erasure always retries."""
    with store.connect() as db:
        db.execute('DELETE FROM usage WHERE created < ?', (time.time()-86400,))
    before = time.time()-settings.retention_days*86400
    candidates = set(store.pending_deletions())
    if settings.retention_days:
        candidates.update(store.inactive_accounts(before))
    for owner in candidates:
        try:
            with workspace_lease(store.path.parent, owner):
                if owner not in store.pending_deletions():
                    if not store.request_deletion(owner, inactive_before=before):
                        continue
                erase_workspace(store.path.parent, owner)
                store.finish_deletion(owner)
        except (OSError, ValueError, portalocker.exceptions.LockException):
            logging.getLogger(__name__).warning('Scheduled account cleanup deferred')
