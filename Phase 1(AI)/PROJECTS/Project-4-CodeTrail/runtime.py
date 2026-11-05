"""Request/worker-local storage scope; CLI runs retain their existing paths."""
from contextlib import contextmanager
from contextvars import ContextVar
from config import settings

_owner = ContextVar("codetrail_owner", default=None)

def data_dir():
    owner = _owner.get()
    return settings.data_dir / "users" / owner if owner else settings.data_dir

def reports_dir():
    return data_dir() / "reports" if _owner.get() else settings.reports_dir

@contextmanager
def user_workspace(owner: str):
    if not owner.isascii() or not owner.isdecimal():
        raise ValueError("invalid account id")
    token = _owner.set(owner)
    try:
        yield
    finally:
        _owner.reset(token)
