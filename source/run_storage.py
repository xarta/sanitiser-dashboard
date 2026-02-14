"""Run storage — manages pipeline run data on the filesystem.

Data layout:
  /app/data/runs/{run_id}/
    meta.json       — run metadata
    events.jsonl    — event stream
    requests.jsonl  — HTTP request/response logs
    timing.json     — timing data
    reports/        — stage output reports
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from source.models import (
    CreateRunRequest,
    CreateRunResponse,
    PipelineEvent,
    RequestLog,
    RunDetail,
    RunSummary,
    TimingEntry,
)

logger = logging.getLogger(__name__)


class RunStorage:
    """Manages pipeline run data persistence."""

    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.runs_path = data_path / "runs"
        self.runs_path.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    def _now_iso(self) -> str:
        """Current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def _generate_run_id(self) -> str:
        """Generate a run ID from current timestamp."""
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    def _run_dir(self, run_id: str) -> Path:
        """Get the directory for a run."""
        return self.runs_path / run_id

    def _read_meta(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Read run metadata."""
        meta_path = self._run_dir(run_id) / "meta.json"
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text())

    def _write_meta(self, run_id: str, meta: Dict[str, Any]) -> None:
        """Write run metadata."""
        meta_path = self._run_dir(run_id) / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))

    def _count_lines(self, path: Path) -> int:
        """Count lines in a JSONL file."""
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text().splitlines() if line.strip())

    def _append_jsonl(self, path: Path, data: Dict[str, Any]) -> int:
        """Append a JSON object as a line to a JSONL file. Returns sequence number."""
        count = self._count_lines(path)
        sequence = count + 1
        with open(path, "a") as f:
            f.write(json.dumps(data) + "\n")
        return sequence

    def _read_jsonl(self, path: Path) -> List[Dict[str, Any]]:
        """Read all entries from a JSONL file."""
        if not path.exists():
            return []
        entries = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    # ---------------------------------------------------------------
    # Run lifecycle
    # ---------------------------------------------------------------

    def create_run(self, request: CreateRunRequest) -> CreateRunResponse:
        """Create a new pipeline run."""
        run_id = self._generate_run_id()
        run_dir = self._run_dir(run_id)

        # Handle duplicate run IDs (unlikely but possible)
        counter = 1
        while run_dir.exists():
            run_id = f"{self._generate_run_id()}-{counter}"
            run_dir = self._run_dir(run_id)
            counter += 1

        run_dir.mkdir(parents=True)
        (run_dir / "reports").mkdir()

        now = self._now_iso()
        meta = {
            "run_id": run_id,
            "target": request.target,
            "mode": request.mode,
            "status": "created",
            "created": now,
            "updated": now,
            "description": request.description,
            "summary": None,
        }
        self._write_meta(run_id, meta)

        return CreateRunResponse(
            run_id=run_id,
            target=request.target,
            mode=request.mode,
            status="created",
            created=now,
            message=f"Run {run_id} created",
        )

    def update_run(self, run_id: str, status: str, message: Optional[str] = None,
                   summary: Optional[Dict[str, Any]] = None) -> RunDetail:
        """Update a run's status."""
        meta = self._read_meta(run_id)
        if meta is None:
            raise FileNotFoundError(f"Run not found: {run_id}")

        meta["status"] = status
        meta["updated"] = self._now_iso()
        if message:
            meta["status_message"] = message
        if summary:
            meta["summary"] = summary

        self._write_meta(run_id, meta)
        return self._to_detail(run_id, meta)

    def get_run(self, run_id: str) -> RunDetail:
        """Get full details of a run."""
        meta = self._read_meta(run_id)
        if meta is None:
            raise FileNotFoundError(f"Run not found: {run_id}")
        return self._to_detail(run_id, meta)

    def list_runs(self) -> List[RunSummary]:
        """List all runs, newest first."""
        runs = []
        if not self.runs_path.exists():
            return runs

        for run_dir in sorted(self.runs_path.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            meta = self._read_meta(run_dir.name)
            if meta is None:
                continue
            runs.append(self._to_summary(run_dir.name, meta))

        return runs

    def _to_summary(self, run_id: str, meta: Dict[str, Any]) -> RunSummary:
        """Convert metadata to RunSummary."""
        run_dir = self._run_dir(run_id)
        return RunSummary(
            run_id=run_id,
            target=meta.get("target", ""),
            mode=meta.get("mode", ""),
            status=meta.get("status", "unknown"),
            created=meta.get("created", ""),
            updated=meta.get("updated"),
            description=meta.get("description"),
            event_count=self._count_lines(run_dir / "events.jsonl"),
            request_count=self._count_lines(run_dir / "requests.jsonl"),
        )

    def _to_detail(self, run_id: str, meta: Dict[str, Any]) -> RunDetail:
        """Convert metadata to RunDetail."""
        run_dir = self._run_dir(run_id)
        timing_path = run_dir / "timing.json"
        timing_count = 0
        if timing_path.exists():
            try:
                timing_data = json.loads(timing_path.read_text())
                timing_count = len(timing_data) if isinstance(timing_data, list) else 1
            except (json.JSONDecodeError, OSError):
                pass

        return RunDetail(
            run_id=run_id,
            target=meta.get("target", ""),
            mode=meta.get("mode", ""),
            status=meta.get("status", "unknown"),
            created=meta.get("created", ""),
            updated=meta.get("updated"),
            description=meta.get("description"),
            summary=meta.get("summary"),
            event_count=self._count_lines(run_dir / "events.jsonl"),
            request_count=self._count_lines(run_dir / "requests.jsonl"),
            timing_count=timing_count,
        )

    # ---------------------------------------------------------------
    # Events
    # ---------------------------------------------------------------

    def push_event(self, run_id: str, event: PipelineEvent) -> int:
        """Append an event to the run's event stream. Returns sequence number."""
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")

        data = event.model_dump()
        if not data.get("timestamp"):
            data["timestamp"] = self._now_iso()

        return self._append_jsonl(run_dir / "events.jsonl", data)

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all events for a run."""
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        return self._read_jsonl(run_dir / "events.jsonl")

    # ---------------------------------------------------------------
    # Request logs
    # ---------------------------------------------------------------

    def push_request(self, run_id: str, request_log: RequestLog) -> int:
        """Append a request log entry. Returns sequence number."""
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")

        data = request_log.model_dump()
        if not data.get("timestamp"):
            data["timestamp"] = self._now_iso()

        sequence = self._append_jsonl(run_dir / "requests.jsonl", data)
        # Backfill sequence into the data if not set
        return sequence

    def get_requests(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all request logs for a run."""
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        return self._read_jsonl(run_dir / "requests.jsonl")

    # ---------------------------------------------------------------
    # Timing
    # ---------------------------------------------------------------

    def push_timing(self, run_id: str, entries: List[TimingEntry]) -> int:
        """Add timing entries for a run. Returns total entry count."""
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")

        timing_path = run_dir / "timing.json"
        existing = []
        if timing_path.exists():
            try:
                existing = json.loads(timing_path.read_text())
            except (json.JSONDecodeError, OSError):
                existing = []

        for entry in entries:
            existing.append(entry.model_dump())

        timing_path.write_text(json.dumps(existing, indent=2))
        return len(existing)

    def get_timing(self, run_id: str) -> List[Dict[str, Any]]:
        """Get timing data for a run."""
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")

        timing_path = run_dir / "timing.json"
        if not timing_path.exists():
            return []

        return json.loads(timing_path.read_text())

    # ---------------------------------------------------------------
    # Deletion
    # ---------------------------------------------------------------

    def delete_run(self, run_id: str) -> None:
        """Delete a run and all its data.

        Raises FileNotFoundError if the run does not exist.
        """
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run not found: {run_id}")

        # Safety: ensure the directory is under our runs path
        try:
            run_dir.resolve().relative_to(self.runs_path.resolve())
        except ValueError:
            raise ValueError(f"Path traversal rejected: {run_id}")

        shutil.rmtree(run_dir)
        logger.info("Deleted run %s (removed %s)", run_id, run_dir)

    # ---------------------------------------------------------------
    # Stats
    # ---------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics."""
        runs = self.list_runs()
        by_status = {}
        for r in runs:
            by_status[r.status] = by_status.get(r.status, 0) + 1

        return {
            "total_runs": len(runs),
            "by_status": by_status,
            "latest_run": runs[0].run_id if runs else None,
        }
