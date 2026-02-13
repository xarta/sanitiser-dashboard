"""
Sanitiser Dashboard — FastAPI application.

Provides a pipeline dashboard UI and logging/events API. Other services
push structured events and log data here; the dashboard renders them
as HTML pages.

Endpoints:
  GET    /                              — redirect to dashboard UI
  GET    /health                        — health check

  POST   /api/runs                      — create a new pipeline run
  GET    /api/runs                      — list all runs
  GET    /api/runs/{run_id}             — get run details
  PATCH  /api/runs/{run_id}             — update run status

  POST   /api/runs/{run_id}/events      — push pipeline event
  GET    /api/runs/{run_id}/events      — get events for a run

  POST   /api/runs/{run_id}/requests    — push request log entry
  GET    /api/runs/{run_id}/requests    — get request logs for a run

  POST   /api/runs/{run_id}/timing      — push timing data
  GET    /api/runs/{run_id}/timing      — get timing data for a run

  GET    /api/files                     — list files in data volume
  GET    /api/files/{path}              — read file content

  GET    /api/config                    — client-side deployment config
  GET    /api/info                      — service metadata

  GET    /ui/*                          — dashboard UI (static HTML)

Environment variables:
  DATA_PATH        — path to persistent data volume (default: /app/data)
  LOG_LEVEL        — logging level (default: INFO)
  CONTROL_HUB_URL  — URL to AI Control Hub for back-link in UI (optional)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from source.models import (
    CreateRunRequest,
    CreateRunResponse,
    ErrorResponse,
    EventResponse,
    FileEntry,
    FileListing,
    GenerateReportsRequest,
    GenerateReportsResponse,
    HealthResponse,
    PipelineEvent,
    RequestLog,
    RequestLogResponse,
    RunDetail,
    RunSummary,
    ServiceInfo,
    TimingEntry,
    TimingResponse,
    UpdateRunRequest,
)
from source.report_generator import generate_reports
from source.run_storage import RunStorage

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("sanitiser-dashboard")

# ===================================================================
# Configuration
# ===================================================================

DATA_PATH = Path(os.getenv("DATA_PATH", "/app/data"))
STATIC_PATH = Path(os.getenv("STATIC_PATH", "/app/static"))
CONTROL_HUB_URL = os.getenv("CONTROL_HUB_URL", "").strip()

logger.info("Configuration:")
logger.info("  DATA_PATH: %s", DATA_PATH)
logger.info("  STATIC_PATH: %s", STATIC_PATH)
logger.info("  CONTROL_HUB_URL: %s", CONTROL_HUB_URL or "(not set)")

# ===================================================================
# Initialise storage
# ===================================================================

storage = RunStorage(DATA_PATH)

# ===================================================================
# FastAPI app
# ===================================================================

app = FastAPI(
    title="sanitiser-dashboard",
    description="Pipeline dashboard and logging API for the doc-sanitiser ecosystem",
    version="1.0.0",
)

# Mount static files for UI
if STATIC_PATH.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_PATH), html=True), name="ui")
    logger.info("Mounted static UI from %s", STATIC_PATH)
else:
    logger.warning("Static path %s not found — UI will not be available", STATIC_PATH)


# ===================================================================
# Error handling
# ===================================================================

def _error_response(status: int, error: str, detail: str) -> JSONResponse:
    """Build a standard error JSON response."""
    return JSONResponse(status_code=status, content={"error": error, "detail": detail})


# ===================================================================
# Service endpoints
# ===================================================================

@app.get("/")
async def root():
    """Redirect to dashboard UI."""
    return RedirectResponse(url="/ui/")


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check — verifies data path is accessible."""
    data_ok = DATA_PATH.exists() and DATA_PATH.is_dir()
    stats = storage.get_stats()
    return HealthResponse(
        status="healthy" if data_ok else "unhealthy",
        data_path=str(DATA_PATH),
        runs_count=stats["total_runs"],
        latest_run=stats.get("latest_run"),
    )


@app.get("/api/info", response_model=ServiceInfo)
async def service_info():
    """Service metadata."""
    return ServiceInfo()


@app.get("/api/config")
async def client_config():
    """Client-side configuration — returns deployment-specific settings.

    Values come from environment variables set in the stack config,
    keeping the source code free of infrastructure-specific URLs.
    """
    config = {}
    if CONTROL_HUB_URL:
        config["control_hub_url"] = CONTROL_HUB_URL
    return config


# ===================================================================
# Run management
# ===================================================================

@app.post("/api/runs", response_model=CreateRunResponse, status_code=201)
async def create_run(body: CreateRunRequest):
    """Create a new pipeline run."""
    try:
        result = storage.create_run(body)
        logger.info("Created run %s for target %s", result.run_id, body.target)
        return result
    except Exception as exc:
        logger.exception("Error creating run")
        return _error_response(500, "internal_error", str(exc))


@app.get("/api/runs", response_model=List[RunSummary])
async def list_runs():
    """List all pipeline runs, newest first."""
    return storage.list_runs()


@app.get("/api/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str):
    """Get full details of a pipeline run."""
    try:
        return storage.get_run(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


@app.patch("/api/runs/{run_id}", response_model=RunDetail)
async def update_run(run_id: str, body: UpdateRunRequest):
    """Update a run's status."""
    try:
        result = storage.update_run(run_id, body.status, body.message, body.summary)
        logger.info("Updated run %s → %s", run_id, body.status)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    except Exception as exc:
        logger.exception("Error updating run %s", run_id)
        return _error_response(500, "internal_error", str(exc))


# ===================================================================
# Events
# ===================================================================

@app.post("/api/runs/{run_id}/events", response_model=EventResponse, status_code=201)
async def push_event(run_id: str, body: PipelineEvent):
    """Push a pipeline event to the run's event stream."""
    try:
        sequence = storage.push_event(run_id, body)
        return EventResponse(
            run_id=run_id,
            sequence=sequence,
            message=f"Event #{sequence} recorded",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


@app.get("/api/runs/{run_id}/events")
async def get_events(run_id: str):
    """Get all events for a run."""
    try:
        return storage.get_events(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


# ===================================================================
# Request logs
# ===================================================================

@app.post("/api/runs/{run_id}/requests", response_model=RequestLogResponse, status_code=201)
async def push_request(run_id: str, body: RequestLog):
    """Push an HTTP request/response log entry."""
    try:
        sequence = storage.push_request(run_id, body)
        return RequestLogResponse(
            run_id=run_id,
            sequence=sequence,
            message=f"Request #{sequence} logged",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


@app.get("/api/runs/{run_id}/requests")
async def get_requests(run_id: str):
    """Get all request logs for a run."""
    try:
        return storage.get_requests(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


# ===================================================================
# Timing
# ===================================================================

@app.post("/api/runs/{run_id}/timing", response_model=TimingResponse, status_code=201)
async def push_timing(run_id: str, body: List[TimingEntry]):
    """Push timing data for a run."""
    try:
        count = storage.push_timing(run_id, body)
        return TimingResponse(
            run_id=run_id,
            entry_count=count,
            message=f"Timing data recorded ({count} total entries)",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


@app.get("/api/runs/{run_id}/timing")
async def get_timing(run_id: str):
    """Get timing data for a run."""
    try:
        return storage.get_timing(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


# ===================================================================
# Report generation
# ===================================================================

@app.post(
    "/api/runs/{run_id}/generate-reports",
    response_model=GenerateReportsResponse,
    status_code=201,
)
async def generate_run_reports(run_id: str, body: GenerateReportsRequest):
    """Generate test-coverage report files from structured data.

    Accepts complete structured data blobs and generates 4 report files
    with identical schema and format to the doc-sanitiser originals:

    - test-coverage.md
    - test-coverage-timing.json
    - test-coverage-requests-responses.md
    - test-coverage-requests-responses.json

    Generated files are written to the run's ``reports/`` directory
    and are browsable via the file browser UI.
    """
    try:
        run_dir = storage._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")

        reports_dir = run_dir / "reports"
        generated = generate_reports(
            reports_dir,
            coverage_data=body.coverage_data,
            timing_data=body.timing_data,
            request_data=body.request_data,
        )

        logger.info(
            "Generated %d reports for run %s: %s",
            len(generated),
            run_id,
            ", ".join(generated.keys()),
        )

        return GenerateReportsResponse(
            run_id=run_id,
            generated=generated,
            message=f"Generated {len(generated)} report files",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    except Exception as exc:
        logger.exception("Error generating reports for run %s", run_id)
        return _error_response(500, "internal_error", str(exc))


# ===================================================================
# File browsing API
# ===================================================================

@app.get("/api/files")
async def list_data_files():
    """List files in the data volume root."""
    return _list_dir(DATA_PATH, "")


@app.get("/api/files/{path:path}")
async def get_data_file(path: str):
    """Read a file from the data volume, or list a subdirectory."""
    # Safety: reject path traversal
    if ".." in path:
        return _error_response(403, "forbidden", "Path traversal not allowed")

    target = (DATA_PATH / path).resolve()
    try:
        target.relative_to(DATA_PATH.resolve())
    except ValueError:
        return _error_response(403, "forbidden", "Path outside data volume")

    if not target.exists():
        return _error_response(404, "not_found", f"Not found: {path}")

    if target.is_dir():
        return _list_dir(target, path)

    # Read file content
    try:
        content = target.read_text(encoding="utf-8")
        return {"path": path, "content": content, "size": len(content)}
    except UnicodeDecodeError:
        return _error_response(400, "binary_file", f"Cannot read binary file: {path}")


def _list_dir(directory: Path, rel_path: str) -> dict:
    """List directory contents."""
    entries = []
    for item in sorted(directory.iterdir()):
        stat = item.stat()
        entries.append({
            "name": item.name,
            "path": f"{rel_path}/{item.name}".lstrip("/"),
            "type": "directory" if item.is_dir() else "file",
            "size": stat.st_size if item.is_file() else None,
            "modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        })
    return {"path": rel_path or "/", "entries": entries, "count": len(entries)}
