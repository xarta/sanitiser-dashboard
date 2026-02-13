"""Pydantic models for sanitiser-dashboard requests and responses."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ===================================================================
# Service info / health
# ===================================================================

class ServiceInfo(BaseModel):
    """Service metadata returned by GET /."""
    service: str = "sanitiser-dashboard"
    version: str = "1.0.0"
    description: str = "Pipeline dashboard and logging API for the doc-sanitiser ecosystem"


class HealthResponse(BaseModel):
    """Health check response."""
    status: str  # "healthy" or "unhealthy"
    data_path: str
    runs_count: int
    latest_run: Optional[str] = None


# ===================================================================
# Pipeline runs
# ===================================================================

class CreateRunRequest(BaseModel):
    """Request body for POST /api/runs."""
    target: str = Field(description="Target directory being sanitised")
    mode: str = Field(default="analyse", description="Pipeline mode (analyse, sanitise, etc.)")
    description: Optional[str] = Field(default=None, description="Optional run description")


class CreateRunResponse(BaseModel):
    """Response for run creation."""
    run_id: str
    target: str
    mode: str
    status: str
    created: str
    message: str


class UpdateRunRequest(BaseModel):
    """Request body for PATCH /api/runs/{run_id}."""
    status: str = Field(description="New status: running, completed, failed")
    message: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None


class RunSummary(BaseModel):
    """Summary of a pipeline run."""
    run_id: str
    target: str
    mode: str
    status: str
    created: str
    updated: Optional[str] = None
    description: Optional[str] = None
    event_count: int = 0
    request_count: int = 0


class RunDetail(BaseModel):
    """Full details of a pipeline run."""
    run_id: str
    target: str
    mode: str
    status: str
    created: str
    updated: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    event_count: int = 0
    request_count: int = 0
    timing_count: int = 0


# ===================================================================
# Events
# ===================================================================

class PipelineEvent(BaseModel):
    """A single pipeline event."""
    timestamp: Optional[str] = None  # Auto-set if not provided
    stage: Optional[int] = None
    stage_name: Optional[str] = None
    event_type: str = Field(description="stage_start, stage_end, progress, error, info")
    message: str
    data: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None


class EventResponse(BaseModel):
    """Response after pushing an event."""
    run_id: str
    sequence: int
    message: str


# ===================================================================
# Request logs
# ===================================================================

class RequestLog(BaseModel):
    """An HTTP request/response log entry."""
    timestamp: Optional[str] = None
    sequence: Optional[int] = None
    service: str = Field(description="Target service name (e.g. gitleaks-validator)")
    method: str
    url: str
    request_body: Optional[Dict[str, Any]] = None
    response_status: Optional[int] = None
    response_body: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None
    test_context: Optional[str] = None


class RequestLogResponse(BaseModel):
    """Response after pushing a request log."""
    run_id: str
    sequence: int
    message: str


# ===================================================================
# Timing
# ===================================================================

class TimingEntry(BaseModel):
    """A timing data entry for a stage or operation."""
    stage: Optional[int] = None
    stage_name: Optional[str] = None
    operation: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


class TimingResponse(BaseModel):
    """Response after pushing timing data."""
    run_id: str
    entry_count: int
    message: str


# ===================================================================
# File browsing
# ===================================================================

class FileEntry(BaseModel):
    """A file or directory entry."""
    name: str
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    modified: Optional[str] = None


class FileListing(BaseModel):
    """Directory listing response."""
    path: str
    entries: List[FileEntry]
    count: int


# ===================================================================
# Error
# ===================================================================

class GenerateReportsRequest(BaseModel):
    """Request body for POST /api/runs/{run_id}/generate-reports.

    Accepts the complete structured data needed to generate all 4
    test-coverage report files with identical schema/format to the
    doc-sanitiser originals.
    """
    coverage_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured test results for test-coverage.md",
    )
    timing_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Complete timing JSON (schema_version 2) — passed through as-is",
    )
    request_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Complete request/response JSON (schema_version 2) for .md and .json",
    )


class GenerateReportsResponse(BaseModel):
    """Response after generating reports."""
    run_id: str
    generated: Dict[str, str] = Field(
        description="Map of filename → path for each generated file",
    )
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: str
