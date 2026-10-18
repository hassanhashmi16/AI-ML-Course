"""FastAPI service around the proven investigation runner (Step 17).

Endpoints:

    GET  /health
    POST /investigations                     -> run one investigation
    GET  /investigations/{thread_id}         -> status + report
    GET  /investigations/{thread_id}/events  -> SSE replay of the stage log
    POST /investigations/{thread_id}/resume  -> continue an interrupted run
    GET  /reports/{name}                     -> a saved report JSON

The endpoints are synchronous on purpose: FastAPI runs them in its threadpool,
so blocking SDK work never touches the event loop. One active investigation at
a time is enforced by the service; a second request gets 409.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.service import InvestigationRequestIn, InvestigationService, RunBusy
from config import settings


def _public(record: dict) -> dict:
    """The public shape: same Report contract the CLI saves."""
    report = record.get("report")
    return {
        "thread_id": record["thread_id"],
        "status": record["status"],
        "report": report.model_dump(mode="json") if report is not None else None,
        "report_path": record.get("report_path"),
        "error": record.get("error"),
    }


def create_app(service: InvestigationService | None = None) -> FastAPI:
    """Build the app; a fixture service can be injected for tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.service is None:
            app.state.service = InvestigationService()
        try:
            yield
        finally:
            app.state.service.close()

    app = FastAPI(title="CodeTrail", version="0.1.0", lifespan=lifespan)
    app.state.service = service

    def service_of(request: Request) -> InvestigationService:
        return request.app.state.service

    @app.exception_handler(RunBusy)
    async def _busy(_request: Request, exc: RunBusy):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/health")
    def health(request: Request) -> dict:
        service = service_of(request)
        return {
            "status": "ok",
            "busy": service.busy,
            "embedding_provider": settings.embed_provider,
        }

    @app.post("/investigations")
    def investigate(payload: InvestigationRequestIn, request: Request) -> dict:
        try:
            record = service_of(request).start(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _public(record)

    @app.get("/investigations/{thread_id}")
    def investigation(thread_id: str, request: Request) -> dict:
        try:
            record = service_of(request).status(thread_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="investigation not found") from exc
        return _public(record)

    @app.get("/investigations/{thread_id}/events")
    async def events(thread_id: str):
        path = settings.data_dir / "traces" / f"{thread_id}.jsonl"
        if not path.exists():
            raise HTTPException(status_code=404, detail="no events for this thread")
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

        async def stream():
            for line in lines:
                event = json.loads(line)
                yield {"event": event["kind"], "data": line}

        return EventSourceResponse(stream())

    @app.post("/investigations/{thread_id}/resume")
    def resume(thread_id: str, request: Request) -> dict:
        try:
            record = service_of(request).resume(thread_id)
        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail="no checkpoint for this thread"
            ) from exc
        return _public(record)

    @app.get("/reports")
    def list_reports() -> dict:
        files = sorted(
            settings.reports_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:100]
        return {
            "reports": [
                {
                    "name": path.name,
                    "modified": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "size": path.stat().st_size,
                }
                for path in files
            ]
        }

    @app.get("/reports/{name}")
    def report_file(name: str):
        if "/" in name or "\\" in name or not name.endswith(".json"):
            raise HTTPException(status_code=400, detail="invalid report name")
        path: Path = settings.reports_dir / name
        if not path.exists():
            raise HTTPException(status_code=404, detail="report not found")
        return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))

    return app


app = create_app()
