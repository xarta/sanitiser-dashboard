"""Unit tests for run storage."""

import json
import tempfile
import unittest
from pathlib import Path

from source.models import (
    CreateRunRequest,
    PipelineEvent,
    RequestLog,
    TimingEntry,
)
from source.run_storage import RunStorage


class TestRunLifecycle(unittest.TestCase):
    """Tests for run creation, update, listing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = RunStorage(Path(self.tmpdir))

    def test_create_run(self):
        """Create a new run returns valid response."""
        req = CreateRunRequest(target="docs/test", mode="analyse")
        result = self.storage.create_run(req)
        self.assertTrue(result.run_id)
        self.assertEqual(result.target, "docs/test")
        self.assertEqual(result.mode, "analyse")
        self.assertEqual(result.status, "created")

    def test_get_run(self):
        """Get run returns full details."""
        req = CreateRunRequest(target="docs/test", mode="sanitise")
        created = self.storage.create_run(req)
        detail = self.storage.get_run(created.run_id)
        self.assertEqual(detail.run_id, created.run_id)
        self.assertEqual(detail.target, "docs/test")
        self.assertEqual(detail.event_count, 0)

    def test_get_nonexistent_run(self):
        """Getting non-existent run raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.storage.get_run("nonexistent-run")

    def test_update_run(self):
        """Updating a run changes its status."""
        req = CreateRunRequest(target="docs/test", mode="analyse")
        created = self.storage.create_run(req)
        updated = self.storage.update_run(created.run_id, "running")
        self.assertEqual(updated.status, "running")

    def test_update_with_summary(self):
        """Updating with summary data persists it."""
        req = CreateRunRequest(target="docs/test", mode="analyse")
        created = self.storage.create_run(req)
        summary = {"secrets_found": 3, "files_scanned": 10}
        updated = self.storage.update_run(created.run_id, "completed", summary=summary)
        self.assertEqual(updated.summary, summary)

    def test_list_runs(self):
        """List runs returns all runs."""
        self.storage.create_run(CreateRunRequest(target="a", mode="analyse"))
        self.storage.create_run(CreateRunRequest(target="b", mode="sanitise"))
        runs = self.storage.list_runs()
        self.assertEqual(len(runs), 2)

    def test_list_runs_empty(self):
        """List runs on empty storage returns empty list."""
        runs = self.storage.list_runs()
        self.assertEqual(runs, [])


class TestEvents(unittest.TestCase):
    """Tests for event push/read."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = RunStorage(Path(self.tmpdir))
        req = CreateRunRequest(target="docs/test", mode="analyse")
        self.run = self.storage.create_run(req)

    def test_push_event(self):
        """Pushing an event records it."""
        event = PipelineEvent(
            event_type="stage_start",
            message="Starting gitleaks scan",
            stage=2,
            stage_name="Gitleaks Scan",
        )
        seq = self.storage.push_event(self.run.run_id, event)
        self.assertEqual(seq, 1)

    def test_push_multiple_events(self):
        """Multiple events get sequential numbers."""
        for i in range(3):
            event = PipelineEvent(event_type="info", message=f"Event {i}")
            seq = self.storage.push_event(self.run.run_id, event)
            self.assertEqual(seq, i + 1)

    def test_get_events(self):
        """Getting events returns all pushed events."""
        self.storage.push_event(
            self.run.run_id,
            PipelineEvent(event_type="stage_start", message="Start"),
        )
        self.storage.push_event(
            self.run.run_id,
            PipelineEvent(event_type="stage_end", message="End", duration_ms=150),
        )
        events = self.storage.get_events(self.run.run_id)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_type"], "stage_start")
        self.assertEqual(events[1]["duration_ms"], 150)

    def test_get_events_empty(self):
        """Getting events with none returns empty list."""
        events = self.storage.get_events(self.run.run_id)
        self.assertEqual(events, [])

    def test_push_event_nonexistent_run(self):
        """Pushing to non-existent run raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.storage.push_event(
                "fake", PipelineEvent(event_type="info", message="x")
            )

    def test_event_auto_timestamp(self):
        """Events without timestamp get one auto-set."""
        self.storage.push_event(
            self.run.run_id,
            PipelineEvent(event_type="info", message="auto"),
        )
        events = self.storage.get_events(self.run.run_id)
        self.assertIsNotNone(events[0]["timestamp"])


class TestRequestLogs(unittest.TestCase):
    """Tests for request log push/read."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = RunStorage(Path(self.tmpdir))
        req = CreateRunRequest(target="docs/test", mode="analyse")
        self.run = self.storage.create_run(req)

    def test_push_request(self):
        """Pushing a request log records it."""
        log = RequestLog(
            service="gitleaks-validator",
            method="POST",
            url="http://localhost:9999/scan",
            response_status=200,
            duration_ms=1234,
        )
        seq = self.storage.push_request(self.run.run_id, log)
        self.assertEqual(seq, 1)

    def test_get_requests(self):
        """Getting request logs returns all entries."""
        self.storage.push_request(
            self.run.run_id,
            RequestLog(service="chunker", method="POST", url="/chunk"),
        )
        requests = self.storage.get_requests(self.run.run_id)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["service"], "chunker")


class TestTiming(unittest.TestCase):
    """Tests for timing data push/read."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = RunStorage(Path(self.tmpdir))
        req = CreateRunRequest(target="docs/test", mode="analyse")
        self.run = self.storage.create_run(req)

    def test_push_timing(self):
        """Pushing timing data records it."""
        entries = [
            TimingEntry(stage=1, stage_name="Archive", duration_ms=500),
            TimingEntry(stage=2, stage_name="Gitleaks", duration_ms=3000),
        ]
        count = self.storage.push_timing(self.run.run_id, entries)
        self.assertEqual(count, 2)

    def test_push_timing_appends(self):
        """Pushing timing data appends to existing."""
        self.storage.push_timing(
            self.run.run_id,
            [TimingEntry(stage=1, stage_name="First", duration_ms=100)],
        )
        count = self.storage.push_timing(
            self.run.run_id,
            [TimingEntry(stage=2, stage_name="Second", duration_ms=200)],
        )
        self.assertEqual(count, 2)

    def test_get_timing(self):
        """Getting timing data returns all entries."""
        self.storage.push_timing(
            self.run.run_id,
            [TimingEntry(stage=1, stage_name="Test", duration_ms=100)],
        )
        timing = self.storage.get_timing(self.run.run_id)
        self.assertEqual(len(timing), 1)
        self.assertEqual(timing[0]["stage_name"], "Test")

    def test_get_timing_empty(self):
        """Getting timing from run with none returns empty list."""
        timing = self.storage.get_timing(self.run.run_id)
        self.assertEqual(timing, [])


class TestStats(unittest.TestCase):
    """Tests for statistics."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = RunStorage(Path(self.tmpdir))

    def test_stats_empty(self):
        """Stats on empty storage."""
        stats = self.storage.get_stats()
        self.assertEqual(stats["total_runs"], 0)
        self.assertIsNone(stats["latest_run"])

    def test_stats_with_runs(self):
        """Stats with runs shows correct counts."""
        r1 = self.storage.create_run(CreateRunRequest(target="a", mode="analyse"))
        self.storage.update_run(r1.run_id, "completed")
        r2 = self.storage.create_run(CreateRunRequest(target="b", mode="analyse"))
        self.storage.update_run(r2.run_id, "failed")

        stats = self.storage.get_stats()
        self.assertEqual(stats["total_runs"], 2)
        self.assertIn("completed", stats["by_status"])
        self.assertIn("failed", stats["by_status"])


if __name__ == "__main__":
    unittest.main()
