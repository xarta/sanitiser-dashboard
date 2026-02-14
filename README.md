# sanitiser-dashboard

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Dockerised FastAPI service that hosts the doc-sanitiser pipeline dashboard UI and a logging/events API. Other pipeline services push structured events, HTTP request logs, and timing data here; the dashboard renders them as interactive HTML pages.

## ⚠️ AI-Generated Content Notice

This project was **generated with AI assistance** and should be treated accordingly:

- **Not production-ready**: Created for a specific homelab environment.
- **May contain bugs**: AI-generated code can have subtle issues.
- **Author's Python experience**: The author is not an experienced Python programmer.

### AI Tools Used

- GitHub Copilot (Claude models)
- Local vLLM instances for validation

### Licensing Note

Released under the **MIT License**. Given the AI-generated nature:
- The author makes no claims about originality
- Use at your own risk
- If you discover any copyright concerns, please open an issue

---

## How It Works

The sanitiser-dashboard provides two main capabilities:

### Logging API

Pipeline services push structured data during runs:
1. **Events** — stage start/end, progress, errors (JSONL)
2. **Request logs** — HTTP request/response entries (JSONL)
3. **Timing data** — duration measurements per stage (JSON)
4. **Report generation** — test coverage reports (Markdown + JSON) generated server-side from structured data

### Dashboard UI

Vanilla HTML/CSS/JS (no build step) with a dark theme:
1. **Dashboard** — run list, stats cards (total/completed/running/failed)
2. **Run Detail** — event timeline, timing waterfall bars, HTTP request table
3. **File Browser** — navigate the data volume, preview files

## Prerequisites

- **Docker** on the host
- A named volume for persistent run data

## Quick Start

### 1. Build the image

```bash
docker build -t sanitiser-dashboard:latest .
```

### 2. Start the service

```bash
docker compose up -d
```

### 3. Check health

```bash
curl http://localhost:8000/health
```

## API Endpoints

### Service

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Redirect to dashboard UI |
| `GET` | `/health` | Health check |
| `GET` | `/api/info` | Service metadata |
| `GET` | `/api/config` | Client-side configuration |

### Runs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/runs` | Create a new pipeline run |
| `GET` | `/api/runs` | List all runs |
| `GET` | `/api/runs/{run_id}` | Get run details |
| `PATCH` | `/api/runs/{run_id}` | Update run status |
| `DELETE` | `/api/runs/{run_id}` | Delete a run and all its data |

### Events & Logs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/runs/{run_id}/events` | Push pipeline event |
| `GET` | `/api/runs/{run_id}/events` | Get events for a run |
| `POST` | `/api/runs/{run_id}/requests` | Push request log |
| `GET` | `/api/runs/{run_id}/requests` | Get request logs |
| `POST` | `/api/runs/{run_id}/requests/query` | Query/filter request logs with server-side filtering |
| `POST` | `/api/runs/{run_id}/timing` | Push timing data |
| `GET` | `/api/runs/{run_id}/timing` | Get timing data |

### Report Generation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/runs/{run_id}/generate-reports` | Generate test coverage reports from structured data |

### File Browser

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/files` | List data volume root |
| `GET` | `/api/files/{path}` | Read file or list directory |

### Dashboard UI

| Path | Page |
|------|------|
| `/ui/` | Dashboard — run list, stats |
| `/ui/run.html?id={run_id}` | Run detail — events, timing, requests |
| `/ui/files.html` | File browser |

## Project Structure

```
sanitiser-dashboard/
├── app.py                        # FastAPI endpoints + static mount
├── source/
│   ├── __init__.py
│   ├── models.py                 # Pydantic models for all requests/responses
│   ├── report_generator.py       # Server-side test coverage report generation
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
# Unit tests (no external services needed)
PYTHONPATH=. python3 -m unittest discover tests -v

# Health check against live service (reads endpoint from .env)
python3 tools/check_service.py

# Integration tests
python3 tools/check_service.py --test

# Full test suite
python3 tools/check_service.py --all
```

## Environment Variables

All service configuration is loaded from environment variables.
See `.env.example` for client-side configuration.
The server-side config is injected via `secrets.env` at deploy time — never committed to source.

## Ecosystem

This service is part of the [xarta](https://github.com/xarta) document analysis ecosystem — a set of Dockerised microservices built for a nested Proxmox homelab running local AI inference on an RTX 5090 and RTX 4000 Blackwell.

The project grew out of a practical need: AI-generated infrastructure code (Proxmox, LXC, Docker configs) is full of secrets and environment-specific details that make it unsafe to share and hard to reuse. These services clean, chunk, embed, and ingest that code into a vector database so AI agents can query it efficiently — and so sanitised versions can be published to GitHub.

All services delegate compute-heavy work (LLM chat, embeddings, reranking) to shared vLLM endpoints via OpenAI-compatible APIs, taking advantage of batched and parallel GPU operations rather than bundling models locally.

This is a work in progress, decomposing the original project that became too monolithic and difficult to develop into more manageable components. The original project had many incomplete features that were proving difficult to implement with generative AI without impacting other features and so even when all components are migrated there will still be some development to do before the features originally envisaged are complete.

| Repository | Description |
|---|---|
| [Normalized-Semantic-Chunker](https://github.com/xarta/Normalized-Semantic-Chunker) | Embedding-based semantic text chunking with statistical token-size control. Lightweight fork — delegates embeddings to a remote vLLM endpoint. |
| [Agentic-Chunker](https://github.com/xarta/Agentic-Chunker) | LLM-driven proposition chunking — uses chat completions to semantically group content. Fork replacing Google Gemini with local vLLM. |
| [gitleaks-validator](https://github.com/xarta/gitleaks-validator) | Dockerised gitleaks wrapper — pattern-driven secret scanning and replacement via REST API. |
| [knowledge-service](https://github.com/xarta/knowledge-service) | Document ingestion into SeekDB (vector database) with RAG query interface. Composes chunking + embedding services. |
| [content-analyser](https://github.com/xarta/content-analyser) | Duplication detection and contradiction analysis across document sets. Composes chunking, embedding, and LLM services. |
| [file-service](https://github.com/xarta/file-service) | File operations REST API — read, write, archive, copy, move. Safety-constrained path access for containerised pipeline services. |
| [sanitiser-dashboard](https://github.com/xarta/sanitiser-dashboard) | Pipeline dashboard UI and logging API — receives structured events, timing, and request logs from pipeline services. |

## License

MIT — see [LICENSE](LICENSE).
