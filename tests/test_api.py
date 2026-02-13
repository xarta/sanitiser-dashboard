"""Unit tests for FastAPI endpoints."""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class TestDashboardEndpoints(unittest.TestCase):
    """Tests for dashboard API endpoints."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.data_path = Path(self.tmpdir)
        (self.data_path / "runs").mkdir()

        import os
        os.environ["DATA_PATH"] = str(self.data_path)
        os.environ["STATIC_PATH"] = str(self.data_path / "static")  # Doesn't exist, UI won't mount

        import importlib
        import source.run_storage
        importlib.reload(source.run_storage)
        import app as app_module
        importlib.reload(app_module)
        self.client = TestClient(app_module.app)

    def test_health(self):
        """GET /health returns health status."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")

    def test_service_info(self):
        """GET /api/info returns service metadata."""
        resp = self.client.get("/api/info")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["service"], "sanitiser-dashboard")

    def test_create_run(self):
        """POST /api/runs creates a new run."""
        resp = self.client.post("/api/runs", json={
            "target": "docs/test",
            "mode": "analyse",
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["run_id"])
        self.assertEqual(data["status"], "created")

    def test_list_runs_empty(self):
        """GET /api/runs on empty storage returns empty list."""
        resp = self.client.get("/api/runs")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_list_runs(self):
        """GET /api/runs returns created runs."""
        self.client.post("/api/runs", json={"target": "a", "mode": "analyse"})
        self.client.post("/api/runs", json={"target": "b", "mode": "sanitise"})
        resp = self.client.get("/api/runs")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_get_run(self):
        """GET /api/runs/{run_id} returns run detail."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        resp = self.client.get(f"/api/runs/{run_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["run_id"], run_id)

    def test_get_run_not_found(self):
        """GET /api/runs/nonexistent returns 404."""
        resp = self.client.get("/api/runs/nonexistent")
        self.assertEqual(resp.status_code, 404)

    def test_update_run(self):
        """PATCH /api/runs/{run_id} updates status."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        resp = self.client.patch(f"/api/runs/{run_id}", json={"status": "running"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "running")

    def test_push_event(self):
        """POST /api/runs/{run_id}/events records event."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        resp = self.client.post(f"/api/runs/{run_id}/events", json={
            "event_type": "stage_start",
            "message": "Starting scan",
            "stage": 2,
            "stage_name": "Gitleaks",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["sequence"], 1)

    def test_get_events(self):
        """GET /api/runs/{run_id}/events returns events."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        self.client.post(f"/api/runs/{run_id}/events", json={
            "event_type": "info", "message": "test",
        })
        resp = self.client.get(f"/api/runs/{run_id}/events")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_push_request_log(self):
        """POST /api/runs/{run_id}/requests records request log."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        resp = self.client.post(f"/api/runs/{run_id}/requests", json={
            "service": "gitleaks-validator",
            "method": "POST",
            "url": "http://localhost:9999/scan",
            "response_status": 200,
            "duration_ms": 1234,
        })
        self.assertEqual(resp.status_code, 201)

    def test_get_requests(self):
        """GET /api/runs/{run_id}/requests returns request logs."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        self.client.post(f"/api/runs/{run_id}/requests", json={
            "service": "chunker", "method": "POST", "url": "/chunk",
        })
        resp = self.client.get(f"/api/runs/{run_id}/requests")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_push_timing(self):
        """POST /api/runs/{run_id}/timing records timing data."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        resp = self.client.post(f"/api/runs/{run_id}/timing", json=[
            {"stage": 1, "stage_name": "Archive", "duration_ms": 500},
            {"stage": 2, "stage_name": "Gitleaks", "duration_ms": 3000},
        ])
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["entry_count"], 2)

    def test_get_timing(self):
        """GET /api/runs/{run_id}/timing returns timing data."""
        create_resp = self.client.post("/api/runs", json={"target": "x", "mode": "analyse"})
        run_id = create_resp.json()["run_id"]
        self.client.post(f"/api/runs/{run_id}/timing", json=[
            {"stage": 1, "stage_name": "Test", "duration_ms": 100},
        ])
        resp = self.client.get(f"/api/runs/{run_id}/timing")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_file_browse_api(self):
        """GET /api/files lists data volume."""
        resp = self.client.get("/api/files")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("entries", data)

    def test_file_browse_path_traversal(self):
        """Path traversal in file browse is rejected."""
        resp = self.client.get("/api/files/../../etc/passwd")
        # Either 403 (caught by traversal check) or 404 (path normalised and not found)
        self.assertIn(resp.status_code, (403, 404))


if __name__ == "__main__":
    unittest.main()
