#!/usr/bin/env python3
"""Health check and integration test tool for sanitiser-dashboard.

Usage:
    python3 tools/check_service.py              # Health check only
    python3 tools/check_service.py --test       # Run integration tests
    python3 tools/check_service.py --all        # Full test suite
    python3 tools/check_service.py --json       # Output as JSON

Reads DASHBOARD_URL from .env (or environment).
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# ===================================================================
# .env loader
# ===================================================================

def _load_env(env_path: str = ".env") -> None:
    """Load key=value pairs from .env into os.environ (no overwrite)."""
    path = Path(env_path)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# ===================================================================
# HTTP helpers (stdlib only)
# ===================================================================

def _http_get(url: str, timeout: int = 30) -> dict:
    """GET request, return parsed JSON."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _http_post_json(url: str, body, timeout: int = 60) -> dict:
    """POST JSON request, return parsed JSON."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _http_patch_json(url: str, body: dict, timeout: int = 60) -> dict:
    """PATCH JSON request, return parsed JSON."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ===================================================================
# Checks
# ===================================================================

def check_health(base_url: str) -> dict:
    """Run health check against the service."""
    result = {"test": "health_check", "passed": False, "details": {}}
    try:
        start = time.monotonic()
        health = _http_get(f"{base_url}/health")
        info = _http_get(f"{base_url}/api/info")
        latency = (time.monotonic() - start) * 1000

        result["details"]["health"] = health
        result["details"]["service_info"] = info
        result["details"]["latency_ms"] = round(latency, 1)

        if health.get("status") == "healthy":
            result["passed"] = True
            result["details"]["message"] = f"Healthy — {health.get('runs_count', 0)} runs"
        else:
            result["details"]["message"] = f"Unhealthy: {health}"

    except urllib.error.URLError as exc:
        result["details"]["message"] = f"Connection failed: {exc}"
    except Exception as exc:
        result["details"]["message"] = f"Error: {exc}"

    return result


def check_run_lifecycle(base_url: str) -> dict:
    """Test full run lifecycle: create, push events/requests/timing, update."""
    result = {"test": "run_lifecycle", "passed": False, "details": {}}

    try:
        # Create run
        run = _http_post_json(f"{base_url}/api/runs", {
            "target": "integration-test",
            "mode": "test",
            "description": "Integration test run from check_service.py",
        })
        run_id = run["run_id"]
        result["details"]["create"] = run

        # Push events
        ev1 = _http_post_json(f"{base_url}/api/runs/{run_id}/events", {
            "event_type": "stage_start",
            "stage": 1,
            "stage_name": "Test Stage",
            "message": "Starting integration test",
        })
        result["details"]["event_1"] = ev1

        ev2 = _http_post_json(f"{base_url}/api/runs/{run_id}/events", {
            "event_type": "stage_end",
            "stage": 1,
            "stage_name": "Test Stage",
            "message": "Test stage completed",
            "duration_ms": 42,
        })
        result["details"]["event_2"] = ev2

        # Push request log
        req_log = _http_post_json(f"{base_url}/api/runs/{run_id}/requests", {
            "service": "test-service",
            "method": "GET",
            "url": f"{base_url}/health",
            "response_status": 200,
            "duration_ms": 15,
        })
        result["details"]["request_log"] = req_log

        # Push timing
        timing = _http_post_json(f"{base_url}/api/runs/{run_id}/timing", [
            {"stage": 1, "stage_name": "Test Stage", "duration_ms": 42},
        ])
        result["details"]["timing"] = timing

        # Read back
        detail = _http_get(f"{base_url}/api/runs/{run_id}")
        result["details"]["detail"] = detail

        if detail.get("event_count", 0) != 2:
            result["details"]["message"] = f"Expected 2 events, got {detail.get('event_count')}"
            return result

        if detail.get("request_count", 0) != 1:
            result["details"]["message"] = f"Expected 1 request, got {detail.get('request_count')}"
            return result

        # Update status
        updated = _http_patch_json(f"{base_url}/api/runs/{run_id}", {
            "status": "completed",
            "message": "Integration test passed",
        })
        result["details"]["update"] = updated

        if updated.get("status") != "completed":
            result["details"]["message"] = f"Expected 'completed', got '{updated.get('status')}'"
            return result

        result["passed"] = True
        result["details"]["message"] = f"Full lifecycle passed (run {run_id})"

    except urllib.error.HTTPError as exc:
        body = exc.read().decode() if exc.fp else str(exc)
        result["details"]["message"] = f"HTTP {exc.code}: {body}"
    except Exception as exc:
        result["details"]["message"] = f"Error: {exc}"

    return result


def check_file_browser(base_url: str) -> dict:
    """Test the file browsing API."""
    result = {"test": "file_browser", "passed": False, "details": {}}

    try:
        listing = _http_get(f"{base_url}/api/files")
        result["details"]["root_listing"] = listing

        if "entries" in listing:
            result["passed"] = True
            result["details"]["message"] = f"File browser working ({listing.get('count', 0)} entries)"
        else:
            result["details"]["message"] = "Invalid listing response"

    except urllib.error.HTTPError as exc:
        body = exc.read().decode() if exc.fp else str(exc)
        result["details"]["message"] = f"HTTP {exc.code}: {body}"
    except Exception as exc:
        result["details"]["message"] = f"Error: {exc}"

    return result


# ===================================================================
# Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="sanitiser-dashboard health check and integration tests")
    parser.add_argument("--test", action="store_true", help="Run integration tests")
    parser.add_argument("--all", action="store_true", help="Run full test suite")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    _load_env()
    base_url = os.getenv("DASHBOARD_URL", "").rstrip("/")
    if not base_url:
        print("Error: DASHBOARD_URL not set. Create .env or set environment variable.")
        sys.exit(1)

    results = []

    # Always run health check
    health = check_health(base_url)
    results.append(health)

    if args.test or args.all:
        results.append(check_run_lifecycle(base_url))

    if args.all:
        results.append(check_file_browser(base_url))

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            msg = r.get("details", {}).get("message", "")
            print(f"[{status}] {r['test']}: {msg}")

    # Exit code
    all_passed = all(r["passed"] for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
