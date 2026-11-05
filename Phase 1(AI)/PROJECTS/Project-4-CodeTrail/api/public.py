"""Public registration, private workspaces, queued jobs, and live progress."""
import asyncio
import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from api.service import InvestigationRequestIn
from api.store import AdmissionError, Store
from api.worker import Worker
from config import BASE_DIR, settings

COOKIE = 'codetrail_session'
TERMINAL = {'completed', 'failed', 'interrupted'}

def validate_id(value):
    import re
    if not re.fullmatch(r'[a-f0-9]{32}', value):
        raise HTTPException(404, 'Investigation not found')
    return value

def create_public_app(*, store=None, worker=None):
    store = store or Store()
    worker = worker or Worker(store)

    @asynccontextmanager
    async def lifespan(app):
        worker.start()
        try:
            yield
        finally:
            worker.close()

    app = FastAPI(title='CodeTrail', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    secure = settings.app_origin.startswith('https://')

    @app.middleware('http')
    async def boundary(request, call_next):
        # APP_ORIGIN, not proxy-supplied headers, determines redirects and CSRF.
        if request.headers.get('host') != httpx.URL(settings.app_origin).netloc.decode():
            return JSONResponse({'detail': 'Invalid host'}, status_code=400)
        if not store.rate_allowed(request.client.host if request.client else 'unknown'):
            return JSONResponse({'detail': 'Too many requests. Try again shortly.'}, status_code=429, headers={'Retry-After': '60'})
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            if request.headers.get('origin') != settings.app_origin:
                return JSONResponse({'detail': 'Invalid request origin'}, status_code=403)
            if request.headers.get('content-length'):
                try:
                    length = int(request.headers['content-length'])
                except ValueError:
                    return JSONResponse({'detail': 'Invalid content length'}, status_code=400)
                if length < 0 or length > 16384:
                    return JSONResponse({'detail': 'Request is too large'}, status_code=413)
            # Bound chunked bodies too, before Pydantic allocates/parses them.
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    return JSONResponse({'detail': 'Request is too large'}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
        if secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    def user(request):
        account = store.user(request.cookies.get(COOKIE))
        if not account:
            raise HTTPException(401, 'Sign in with GitHub to use CodeTrail')
        return account

    def owned(request, identifier):
        account = user(request)
        try:
            return store.job(account['id'], validate_id(identifier))
        except LookupError:
            raise HTTPException(404, 'Investigation not found') from None

    def shape(job):
        return {'thread_id': job['id'], 'status': job['status'], 'report': json.loads(job['report']) if job['report'] else None, 'error': job['error']}

    @app.get('/health')
    def health():
        if hasattr(worker, 'thread') and (worker.thread is None or not worker.thread.is_alive()):
            raise HTTPException(503, 'Investigation worker unavailable')
        return {'status': 'ok', 'public_app': True}

    @app.get('/auth/me')
    def me(request: Request):
        return {'user': store.user(request.cookies.get(COOKIE)), 'public_app': True}

    @app.get('/auth/login')
    def login():
        state, verifier = store.begin_oauth()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        params = {'client_id': settings.oauth_client_id, 'redirect_uri': settings.app_origin+'/auth/callback', 'state': state, 'scope': '', 'code_challenge': challenge, 'code_challenge_method': 'S256'}
        response = RedirectResponse('https://github.com/login/oauth/authorize?'+urlencode(params))
        response.set_cookie('codetrail_oauth', state, max_age=600, httponly=True, secure=secure, samesite='lax', path='/auth')
        return response

    @app.get('/auth/callback')
    async def callback(request: Request, code: str = '', state: str = ''):
        cookie = request.cookies.get('codetrail_oauth', '')
        if not state or len(state) > 100 or not cookie or not secrets.compare_digest(state, cookie):
            raise HTTPException(400, 'Invalid sign-in state. Please sign in again.')
        verifier = store.consume_oauth(state)
        if not verifier or not code or len(code) > 512:
            raise HTTPException(400, 'Sign-in expired. Please sign in again.')
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token_response = await client.post('https://github.com/login/oauth/access_token', headers={'Accept': 'application/json'}, data={'client_id': settings.oauth_client_id, 'client_secret': settings.oauth_client_secret.get_secret_value(), 'code': code, 'state': state, 'redirect_uri': settings.app_origin+'/auth/callback', 'code_verifier': verifier})
                token_response.raise_for_status()
                token = token_response.json().get('access_token')
                if not token:
                    raise ValueError('no access token')
                profile_response = await client.get('https://api.github.com/user', headers={'Authorization': 'Bearer '+token, 'Accept': 'application/vnd.github+json'})
                profile_response.raise_for_status()
                profile = profile_response.json()
                # The OAuth token is used only to prove identity, never persisted,
                # sent to the model, or used to read repositories.
                session = store.login(str(profile['id']), profile['login'])
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, 'GitHub sign-in failed. Please try again.') from None
        response = RedirectResponse('/', status_code=303)
        response.set_cookie(COOKIE, session, max_age=settings.session_hours*3600, httponly=True, secure=secure, samesite='lax')
        response.delete_cookie('codetrail_oauth', path='/auth')
        return response

    @app.post('/auth/logout')
    def logout(request: Request):
        store.logout(request.cookies.get(COOKIE))
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        return response

    @app.exception_handler(AdmissionError)
    async def admission_error(_request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=429, headers={'Retry-After': '60'})

    @app.post('/investigations', status_code=202)
    def start(payload: InvestigationRequestIn, request: Request):
        return shape(store.enqueue(user(request)['id'], payload.model_dump(mode='json')))

    @app.get('/investigations')
    def jobs(request: Request):
        return {'investigations': [shape(job) for job in store.jobs(user(request)['id'])]}

    @app.get('/investigations/{identifier}')
    def status(identifier: str, request: Request):
        return shape(owned(request, identifier))

    @app.post('/investigations/{identifier}/resume', status_code=202)
    def resume(identifier: str, request: Request):
        job = owned(request, identifier)
        return shape(store.enqueue(job['owner'], resume=job['id']))

    @app.get('/investigations/{identifier}/events')
    async def events(identifier: str, request: Request):
        job = owned(request, identifier)
        path = settings.data_dir / 'users' / job['owner'] / 'traces' / (job['id']+'.jsonl')
        async def stream():
            offset = 0
            while True:
                if await request.is_disconnected() or not store.user(request.cookies.get(COOKIE)):
                    return
                if path.exists():
                    # Read only complete lines; a worker may be in the middle
                    # of appending the next UTF-8 event.
                    with path.open('rb') as handle:
                        handle.seek(offset)
                        for line in handle:
                            if not line.endswith(b'\n'):
                                break
                            offset += len(line)
                            event = json.loads(line)
                            yield {'event': event['kind'], 'data': json.dumps(event)}
                current = store.job(job['owner'], job['id'])
                if current['status'] in TERMINAL:
                    # Emit final job state as well, including failure before
                    # the graph could write its first event.
                    yield {'event': 'job_finished', 'data': json.dumps({'status': current['status']})}
                    return
                await asyncio.sleep(0.3)
        return EventSourceResponse(stream(), ping=15)

    @app.get('/reports')
    def reports(request: Request):
        return {'reports': [{'name': job['id']+'.json', 'modified': datetime.fromtimestamp(job['created'], timezone.utc).isoformat(), 'size': len(job['report'])} for job in store.jobs(user(request)['id']) if job['report']]}

    @app.get('/reports/{name}')
    def report(name: str, request: Request):
        job = owned(request, name.removesuffix('.json'))
        if not name.endswith('.json') or not job['report']:
            raise HTTPException(404, 'Report not found')
        return JSONResponse(json.loads(job['report']))

    frontend = BASE_DIR / 'frontend' / 'dist'
    if frontend.exists():
        app.mount('/assets', StaticFiles(directory=frontend/'assets'), name='assets')
        @app.get('/')
        def index():
            return FileResponse(frontend/'index.html')
    return app
