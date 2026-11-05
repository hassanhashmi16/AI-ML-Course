"""Public boundaries: identity, ownership, admission, and safe GitHub scope."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from api.public import create_public_app
from api.store import Store, AdmissionError
from api.service import InvestigationRequestIn
from config import settings
from github_source.client import get_repository
from runtime import user_workspace, data_dir, reports_dir

class IdleWorker:
    def start(self): pass
    def close(self): pass

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    monkeypatch.setattr(settings, 'app_origin', 'http://testserver')
    monkeypatch.setattr(settings, 'requests_per_minute', 1000)
    monkeypatch.setattr(settings, 'daily_user_runs', 5)
    monkeypatch.setattr(settings, 'daily_global_runs', 30)
    return Store(tmp_path/'app.sqlite')

def client_for(store, owner):
    app = create_public_app(store=store, worker=IdleWorker())
    client = TestClient(app)
    client.cookies.set('codetrail_session', store.login(owner, 'user'+owner))
    client.headers['Origin'] = settings.app_origin
    return client

PAYLOAD = {'repository': 'https://github.com/pallets/flask', 'question': 'Why this change?'}

def test_unauthenticated_and_cross_origin_posts_cannot_enqueue(store):
    with TestClient(create_public_app(store=store, worker=IdleWorker())) as client:
        assert client.post('/investigations', json=PAYLOAD).status_code == 403
        assert client.post('/investigations', json=PAYLOAD, headers={'Origin': settings.app_origin}).status_code == 401
        assert client.get('/reports').status_code == 401
    assert not store.jobs('1')

def test_account_cannot_read_resume_or_stream_another_accounts_job(store):
    job = store.enqueue('1', PAYLOAD)
    store.finish(job['id'], report={'private_to_owner': True})
    with client_for(store, '2') as client:
        assert client.get('/reports').json() == {'reports': []}
        for suffix in ['', '/events']:
            assert client.get('/investigations/'+job['id']+suffix).status_code == 404
        assert client.post('/investigations/'+job['id']+'/resume').status_code == 404
        assert client.get('/reports/'+job['id']+'.json').status_code == 404
    with client_for(store, '1') as client:
        assert client.get('/reports/'+job['id']+'.json').json() == {'private_to_owner': True}

def test_queue_admission_is_atomic_and_recovery_is_durable(store, monkeypatch):
    monkeypatch.setattr(settings, 'daily_global_runs', 1)
    def admit(owner):
        try: return store.enqueue(owner, PAYLOAD)
        except AdmissionError: return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(admit, map(str, range(1, 9))))
    assert sum(result is not None for result in results) == 1
    claimed = store.claim()
    reopened = Store(store.path)
    reopened.recover()
    assert reopened.job(claimed['owner'], claimed['id'])['status'] == 'interrupted'
    assert reopened.claim() is None

def test_user_limit_pending_limit_and_resume_are_reserved(store, monkeypatch):
    monkeypatch.setattr(settings, 'daily_user_runs', 2)
    job = store.enqueue('1', PAYLOAD)
    with pytest.raises(AdmissionError): store.enqueue('1', PAYLOAD)
    store.finish(job['id'], error='interrupted')
    resumed = store.enqueue('1', resume=job['id'])
    assert resumed['operation'] == 'resume'
    store.finish(job['id'], error='interrupted')
    with pytest.raises(AdmissionError): store.enqueue('1', resume=job['id'])

def test_private_and_internal_repositories_are_rejected():
    for private, visibility in [(True, 'private'), (False, 'internal')]:
        gh = SimpleNamespace(get_repo=lambda slug: SimpleNamespace(private=private, visibility=visibility))
        with pytest.raises(ValueError, match='public'):
            get_repository(gh, PAYLOAD['repository'])

def test_payload_caps_and_path_validation():
    for extra in [{'question':' '}, {'question':'a'*2001}, {'paths':['../secret']}, {'paths':['/etc/passwd']}, {'paths':['x'*301]}, {'pulls':[-1]}]:
        with pytest.raises(ValueError): InvestigationRequestIn(**(PAYLOAD | extra))

def test_filesystem_scopes_are_isolated_and_reset(store):
    original = data_dir()
    with user_workspace('1'):
        first = data_dir()
        assert reports_dir() == first/'reports'
    with user_workspace('2'):
        assert data_dir() != first
    assert data_dir() == original
    with pytest.raises(ValueError):
        with user_workspace('../1'): pass

def test_oauth_state_is_single_use_and_sessions_are_revocable(store):
    state, verifier = store.begin_oauth()
    assert store.consume_oauth(state) == verifier
    assert store.consume_oauth(state) is None
    token = store.login('1', 'alice')
    assert store.user(token)['login'] == 'alice'
    with store.connect() as db:
        assert db.execute('SELECT token FROM sessions').fetchone()[0] != token
    store.logout(token)
    assert store.user(token) is None

def test_rate_limit_and_payload_size(store, monkeypatch):
    monkeypatch.setattr(settings, 'requests_per_minute', 1)
    with TestClient(create_public_app(store=store, worker=IdleWorker())) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/health').status_code == 429
    monkeypatch.setattr(settings, 'requests_per_minute', 1000)
    with client_for(store, '1') as client:
        assert client.post('/investigations', content=b'x'*17000).status_code == 413

def test_live_events_are_sent_before_job_completion(store):
    """ASGI send observes a running job at the instant its event is sent."""
    app = create_public_app(store=store, worker=IdleWorker())
    token = store.login('1', 'alice')
    job = store.enqueue('1', PAYLOAD)
    store.claim()
    path = settings.data_dir/'users'/'1'/'traces'/(job['id']+'.jsonl')
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'kind':'stage_finished','stage':'tools','message':'search finished'})+'\n')
    observed = []
    async def exercise():
        first_request = True
        done = asyncio.Event()
        async def receive():
            nonlocal first_request
            if first_request:
                first_request = False
                return {'type':'http.request','body':b'', 'more_body':False}
            await done.wait()
            return {'type':'http.disconnect'}
        async def send(message):
            body = message.get('body', b'')
            if b'search finished' in body:
                observed.append(store.job('1', job['id'])['status'])
                store.finish(job['id'], report={'ok':True})
            if message['type'] == 'http.response.body' and not message.get('more_body', False): done.set()
        scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET','scheme':'http','path':'/investigations/'+job['id']+'/events','raw_path':('/investigations/'+job['id']+'/events').encode(),'query_string':b'','root_path':'','headers':[(b'host',b'testserver'),(b'cookie',('codetrail_session='+token).encode())],'client':('127.0.0.1',1234),'server':('testserver',80)}
        await asyncio.wait_for(app(scope, receive, send), 5)
    asyncio.run(exercise())
    assert observed == ['running']


def test_oauth_callback_uses_pkce_and_discards_provider_token(store, monkeypatch):
    import httpx
    original_client = httpx.AsyncClient
    seen = []
    def github(request):
        seen.append(request)
        if request.url.host == 'github.com':
            assert b'code_verifier=' in request.content
            return httpx.Response(200, json={'access_token':'identity-only-test-token'})
        return httpx.Response(200, json={'id':123, 'login':'alice'})
    monkeypatch.setattr('api.public.httpx.AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(github), **kwargs))
    with TestClient(create_public_app(store=store, worker=IdleWorker())) as client:
        login = client.get('/auth/login', follow_redirects=False)
        assert 'code_challenge=' in login.headers['location']
        assert 'scope=&' in login.headers['location']
        state = client.cookies.get('codetrail_oauth')
        assert client.get('/auth/callback?state=wrong&code=code').status_code == 400
        callback = client.get('/auth/callback', params={'state':state,'code':'code'}, follow_redirects=False)
        assert callback.status_code == 303
        assert client.get('/auth/me').json()['user']['id'] == '123'
        assert client.get('/auth/callback', params={'state':state,'code':'code'}).status_code == 400
    assert len(seen) == 2
    assert b'identity-only-test-token' not in store.path.read_bytes()


def test_worker_scopes_jobs_and_second_worker_cannot_claim(store):
    import time
    import portalocker
    from api.worker import Worker
    written = []
    class FakeService:
        def start(self, payload, *, thread_id):
            written.append(data_dir())
            return {'report': SimpleNamespace(model_dump=lambda **kwargs: {'question':payload.question})}
        def close(self): pass
    first = store.enqueue('1', PAYLOAD)
    second = store.enqueue('2', PAYLOAD)
    worker = Worker(store, service_factory=FakeService)
    worker.start()
    try:
        with pytest.raises(portalocker.exceptions.LockException):
            Worker(store, service_factory=FakeService).start()
        deadline = time.monotonic()+5
        while store.job('2', second['id'])['status'] != 'completed' and time.monotonic() < deadline:
            time.sleep(0.02)
        assert store.job('1', first['id'])['status'] == 'completed'
        assert store.job('2', second['id'])['status'] == 'completed'
        assert written == [settings.data_dir/'users'/'1', settings.data_dir/'users'/'2']
    finally:
        worker.close()


def test_overall_timeout_stops_the_job_and_keeps_it_resumable(store, monkeypatch):
    from api.worker import Worker
    job = store.enqueue('1', PAYLOAD)
    store.claim()
    class Process:
        alive = True
        terminated = False
        def start(self): pass
        def is_alive(self): return self.alive
        def join(self, timeout): pass
        def terminate(self): self.terminated = True; self.alive = False
        def close(self): pass
    process = Process()
    monkeypatch.setattr('api.worker.multiprocessing.get_context', lambda method: SimpleNamespace(Process=lambda **kwargs: process))
    monkeypatch.setattr(settings, 'max_job_seconds', 0)
    Worker(store).supervise(job)
    assert process.terminated
    assert store.job('1', job['id'])['status'] == 'interrupted'
    assert store.enqueue('1', resume=job['id'])['operation'] == 'resume'
