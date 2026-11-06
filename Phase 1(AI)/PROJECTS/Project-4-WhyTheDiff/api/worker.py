"""Durable queue with a killable child process per investigation.

A hard timeout includes source collection, model downloads, and indexing, so
one slow request cannot hold the worker indefinitely. Each child owns and
releases its Qdrant/SQLite handles independently of the web server.
"""
import json
import logging
import multiprocessing
import threading
import time
from config import settings
from runtime import user_workspace
from api.privacy import workspace_lease, maintain_accounts


def public_failure(exc):
    """Useful failure categories without echoing provider URLs or request data."""
    kind = type(exc).__name__
    status = getattr(exc, 'status_code', None) or getattr(exc, 'status', None)
    if status == 429 or kind in {'RateLimitError', 'RateLimitExceededException'}:
        return 'The provider is rate-limiting requests. Wait a little before trying again.'
    if kind in {'TimeoutError', 'ReadTimeout', 'ConnectTimeout', 'APITimeoutError'}:
        return 'A source or AI request timed out. Try resuming the investigation.'
    if isinstance(status, int) and status >= 500:
        return 'An external service is temporarily unavailable. Please try again shortly.'
    if kind in {'OutputParserException', 'ValidationError'}:
        return 'The AI response could not be validated. Try resuming or starting a new investigation.'
    if isinstance(exc, ValueError) and str(exc) == 'only public repositories are supported':
        return 'This repository is not public. WhyTheDiff supports public GitHub repositories only.'
    return 'The investigation could not finish. Try resuming it, or start a new run.'


def execute_job(store_path, job, service_factory=None):
    from api.store import Store
    from api.service import InvestigationRequestIn, InvestigationService
    store = Store(store_path)
    with workspace_lease(store.path.parent, job['owner']), user_workspace(job['owner']):
        service = None
        try:
            service = (service_factory or InvestigationService)()
            if job['operation'] == 'resume':
                result = service.resume(job['id'])
            else:
                result = service.start(InvestigationRequestIn.model_validate(json.loads(job['payload'])), thread_id=job['id'])
            report = result.get('report')
            if report is None:
                raise RuntimeError('no report')
            store.finish(job['id'], report=report.model_dump(mode='json'))
        except Exception as exc:
            logging.getLogger(__name__).warning('Investigation %s failed (%s)', job['id'], type(exc).__name__)
            store.finish(job['id'], error=public_failure(exc))
        finally:
            if service:
                try:
                    service.close()
                except Exception:
                    logging.getLogger(__name__).warning('Investigation client cleanup failed')


class Worker:
    def __init__(self, store, service_factory=None):
        self.store = store
        self.service_factory = service_factory
        self.stop = threading.Event()
        self.thread = None
        self.lease = None

    def start(self):
        import portalocker
        self.lease = portalocker.Lock(str(self.store.path)+'.worker.lock', timeout=0)
        self.lease.acquire()
        self.store.recover()
        self.thread = threading.Thread(target=self.run, name='whythediff-worker', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
        if self.lease and (not self.thread or not self.thread.is_alive()):
            self.lease.release()

    def supervise(self, job):
        process = multiprocessing.get_context('spawn').Process(target=execute_job, args=(self.store.path, job), daemon=True)
        process.start()
        deadline = time.monotonic()+settings.max_job_seconds
        try:
            while process.is_alive():
                process.join(timeout=0.3)
                if self.stop.is_set() or time.monotonic() >= deadline:
                    process.terminate()
                    process.join(timeout=5)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=2)
                    message = 'The server stopped. Resume this investigation.' if self.stop.is_set() else 'The investigation reached its time limit. You can try resuming it.'
                    self.store.interrupt(job['id'], message)
                    return
            if self.store.job(job['owner'], job['id'])['status'] == 'running':
                self.store.interrupt(job['id'], 'The worker process stopped. Try resuming this investigation.')
        finally:
            process.close()

    def run(self):
        next_maintenance = 0
        while not self.stop.is_set():
            if time.monotonic() >= next_maintenance:
                try:
                    maintain_accounts(self.store)
                except Exception:
                    logging.getLogger(__name__).warning('Account maintenance deferred')
                next_maintenance = time.monotonic()+3600
            job = self.store.claim()
            if not job:
                self.stop.wait(0.5)
                continue
            try:
                if self.service_factory is not None:
                    # Deterministic fixtures avoid spawning test-local factories.
                    execute_job(self.store.path, job, self.service_factory)
                else:
                    self.supervise(job)
            except Exception:
                self.store.interrupt(job['id'], 'The worker could not finish. Try resuming this investigation.')
