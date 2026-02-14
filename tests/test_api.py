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

    # ---------------------------------------------------------------
    # Request query endpoint
    # ---------------------------------------------------------------

    def _create_run_with_requests(self):
        """Helper: create a run and push sample request logs."""
        create_resp = self.client.post("/api/runs", json={"target": "test", "mode": "test"})
        run_id = create_resp.json()["run_id"]

        # Push varied request logs
        self.client.post(f"/api/runs/{run_id}/requests", json={
            "service": "llm",
            "method": "POST",
            "url": "http://h/v1/chat/completions",
            "response_status": 200,
            "duration_ms": 50.0,
            "test_context": "test_llm.TestLLM.test_chat",
            "request_body": {"messages": [{"role": "user", "content": "restart the service"}]},
            "response_body": {"choices": [{"message": {"content": "ok"}}]},
        })
        self.client.post(f"/api/runs/{run_id}/requests", json={
            "service": "embedding",
            "method": "POST",
            "url": "http://h/v1/embeddings",
            "response_status": 200,
            "duration_ms": 15.0,
            "test_context": "test_emb.TestEmb.test_batch",
            "request_body": {"input": ["hello"]},
            "response_body": {"data": [{"embedding": [0.1, 0.2]}]},
        })
        self.client.post(f"/api/runs/{run_id}/requests", json={
            "service": "llm",
            "method": "POST",
            "url": "http://h/v1/chat/completions",
            "response_status": 429,
            "duration_ms": 1000.0,
            "test_context": "test_llm.TestLLM.test_retry",
            "request_body": {"messages": []},
            "response_body": None,
            "error": "Rate limited",
        })
        return run_id

    def test_query_requests_no_filter(self):
        """POST /api/runs/{run_id}/requests/query returns all when no filters."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["matched"], 3)

    def test_query_requests_by_endpoint(self):
        """Filter by endpoint_type returns matching entries."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={
            "endpoint_type": "llm",
        })
        data = resp.json()
        self.assertEqual(data["matched"], 2)

    def test_query_requests_by_test_pattern(self):
        """Filter by test_pattern returns matching entries."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={
            "test_pattern": "TestEmb",
        })
        data = resp.json()
        self.assertEqual(data["matched"], 1)

    def test_query_requests_by_status(self):
        """Filter by status_code returns matching entries."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={
            "status_code": 429,
        })
        data = resp.json()
        self.assertEqual(data["matched"], 1)

    def test_query_requests_errors_only(self):
        """Filter errors_only returns only error entries."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={
            "errors_only": True,
        })
        data = resp.json()
        self.assertEqual(data["matched"], 1)

    def test_query_requests_keyword_search(self):
        """Keyword search finds entries with matching payload content."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={
            "keyword": "restart",
        })
        data = resp.json()
        self.assertEqual(data["matched"], 1)

    def test_query_requests_include_payloads(self):
        """include_payloads=true returns full bodies."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={
            "endpoint_type": "embedding",
            "include_payloads": True,
        })
        data = resp.json()
        self.assertEqual(data["matched"], 1)
        entry = data["entries"][0]
        self.assertIn("request_body", entry)
        self.assertIn("response_body", entry)

    def test_query_requests_excludes_payloads_by_default(self):
        """include_payloads=false (default) strips bodies."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={
            "endpoint_type": "embedding",
        })
        data = resp.json()
        entry = data["entries"][0]
        self.assertNotIn("request_body", entry)
        self.assertNotIn("response_body", entry)

    def test_query_requests_summary_by_test(self):
        """Query response includes summary_by_test."""
        run_id = self._create_run_with_requests()
        resp = self.client.post(f"/api/runs/{run_id}/requests/query", json={})
        data = resp.json()
        self.assertIn("summary_by_test", data)
        self.assertGreater(len(data["summary_by_test"]), 0)

    def test_query_requests_run_not_found(self):
        """Query on nonexistent run returns 404."""
        resp = self.client.post("/api/runs/nonexistent/requests/query", json={})
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
