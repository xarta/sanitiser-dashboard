# sanitiser-dashboard — GitHub Copilot Instructions

## Project Overview

sanitiser-dashboard is a Dockerised FastAPI service that hosts the doc-sanitiser pipeline dashboard UI and a logging/events API. Other pipeline services push structured events, HTTP request logs, and timing data here; the dashboard renders them as HTML pages.

Part of the doc-sanitiser ecosystem. Deployed via Docker.

## Key Rules

- **Use `python3`** not `python`.
- **British spelling** — `sanitise`, `analyse`, `colour`, etc.
- **No real infrastructure in source** — never put real IPs, hostnames, LXC IDs, or API keys in committed code. All loaded from environment variables.
- **TDD approach** — write tests first when implementing new features.
- **Stdlib HTTP clients** — all HTTP client code uses `urllib.request` only. No `requests`, no `httpx`.
- **FastAPI + pydantic** — web framework. Use `pydantic.BaseModel` for request/response models.
- **Run tests with unittest** — `PYTHONPATH=. python3 -m unittest discover tests -v`.
- **Vanilla HTML/CSS/JS** — no build step, no frameworks. Dark theme matching ai-control hub.

## Project Structure

```
sanitiser-dashboard/
├── app.py                        # FastAPI endpoints + static mount
├── source/
│   ├── __init__.py
│   ├── models.py                 # Pydantic models for all requests/responses
│   └── run_storage.py            # Run lifecycle, event/request/timing persistence
├── static/
│   ├── index.html                # Dashboard — run list, stats
│   ├── run.html                  # Run detail — events, timing waterfall, requests
│   ├── files.html                # File browser — navigate data volume
│   └── css/
│       └── dashboard.css         # Dark theme styles
├── tests/
│   ├── __init__.py
│   ├── test_run_storage.py       # Storage unit tests
│   └── test_api.py               # Endpoint tests
├── tools/
│   └── check_service.py          # Health + integration tests
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
├── .dockerignore
├── LICENSE
└── README.md
```

## Running Tests

```bash
# Unit tests (fast, no external services needed)
PYTHONPATH=. python3 -m unittest discover tests -v

# Health check (requires deployed service, reads from .env)
python3 tools/check_service.py

# Integration tests
python3 tools/check_service.py --test

# Full test suite
python3 tools/check_service.py --all
```

## Data Volume

Runs are stored as JSONL/JSON files:
```
/app/data/runs/{run_id}/
  meta.json        — run metadata
  events.jsonl     — event stream
  requests.jsonl   — HTTP request/response logs
  timing.json      — timing data
  reports/         — stage output reports
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATA_PATH` | Path to persistent data volume | `/app/data` |
| `STATIC_PATH` | Path to static UI files | `/app/static` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Dashboard UI

Vanilla HTML/CSS/JS served from `/ui/`. Pages:
- `/ui/` — Dashboard: run list, stats
- `/ui/run.html?id={run_id}` — Run detail: events, timing waterfall, requests
- `/ui/files.html` — File browser: navigate data volume

Dark theme (`#1a1a2e` / `#16213e` / `#00d4ff`) matching the ai-control hub.

## Relationship to doc-sanitiser

This service receives pipeline events, request logs, and timing data from the orchestrator. It replaces the local HTML report viewers from the doc-sanitiser test infrastructure.
