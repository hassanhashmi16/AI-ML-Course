"""Durable sessions, job ownership, queue admission, and usage reservations.

SQLite transactions serialize admission, so simultaneous requests cannot spend
the same remaining quota. This deployment has exactly one worker process.
"""
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from config import settings

class AdmissionError(ValueError):
    pass

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

class Store:
    def __init__(self, path=None):
        self.path = path or settings.data_dir / "app.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, login TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth (state TEXT PRIMARY KEY, verifier TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL,
              operation TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, report TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS usage (owner TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS rates (key TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner, created);
            CREATE INDEX IF NOT EXISTS usage_time ON usage(created);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def login(self, owner, login):
        if not owner.isascii() or not owner.isdecimal():
            raise ValueError("invalid GitHub identity")
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (owner, login))
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (digest(token), owner, time.time()+settings.session_hours*3600))
        return token

    def user(self, token):
        if not token:
            return None
        with self.connect() as db:
            row = db.execute("SELECT users.* FROM users JOIN sessions ON users.id=sessions.owner WHERE token=? AND expires>?", (digest(token), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (digest(token or ""),))

    def begin_oauth(self):
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        with self.connect() as db:
            db.execute("DELETE FROM oauth WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO oauth VALUES (?, ?, ?)", (digest(state), verifier, time.time()+600))
        return state, verifier

    def consume_oauth(self, state):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT verifier FROM oauth WHERE state=? AND expires>?", (digest(state), time.time())).fetchone()
            db.execute("DELETE FROM oauth WHERE state=?", (digest(state),))
        return row[0] if row else None

    def rate_allowed(self, ip):
        window = int(time.time() // 60)
        key = digest(ip)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM rates WHERE window < ?", (window-1,))
            row = db.execute("SELECT window,count FROM rates WHERE key=?", (key,)).fetchone()
            count = row[1]+1 if row and row[0] == window else 1
            db.execute("INSERT OR REPLACE INTO rates VALUES (?, ?, ?)", (key, window, count))
        return count <= settings.requests_per_minute

    def enqueue(self, owner, payload=None, *, resume=None):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= settings.max_queued_runs:
                raise AdmissionError("The queue is full. Try again later.")
            if db.execute("SELECT 1 FROM jobs WHERE owner=? AND status IN ('queued','running')", (owner,)).fetchone():
                raise AdmissionError("You already have an investigation queued or running.")
            db.execute("DELETE FROM usage WHERE created < ?", (now-86400,))
            global_count, user_count = db.execute("SELECT count(*),coalesce(sum(owner=?),0) FROM usage", (owner,)).fetchone()
            if global_count >= settings.daily_global_runs or user_count >= settings.daily_user_runs:
                raise AdmissionError("The daily investigation limit has been reached. Try again later.")
            if resume:
                row = db.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (resume, owner)).fetchone()
                if not row:
                    raise LookupError(resume)
                if row['status'] not in {'failed', 'interrupted'}:
                    raise AdmissionError("Only an interrupted or failed investigation can be resumed.")
                identifier = resume
                db.execute("UPDATE jobs SET operation='resume',status='queued',created=?,error=NULL WHERE id=?", (now, identifier))
            else:
                identifier = uuid.uuid4().hex
                db.execute("INSERT INTO jobs VALUES (?, ?, ?, 'start','queued', ?, NULL, NULL)", (identifier, owner, json.dumps(payload), now))
            db.execute("INSERT INTO usage VALUES (?, ?)", (owner, now))
        return self.job(owner, identifier)

    def job(self, owner, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND owner=?", (identifier, owner)).fetchone()
        if not row:
            raise LookupError(identifier)
        return dict(row)

    def jobs(self, owner):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 100", (owner,))]

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='interrupted',error='The server restarted. Resume this investigation.' WHERE status='running'")

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (row['id'],))
        return dict(row) if row else None

    def finish(self, identifier, *, report=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,report=?,error=? WHERE id=?", ('failed' if error else 'completed', json.dumps(report) if report else None, error, identifier))

    def interrupt(self, identifier, message):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='interrupted',error=? WHERE id=? AND status='running'", (message, identifier))
