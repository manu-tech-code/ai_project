# AI Legacy Modernization Platform (ALM) — Architecture Overview

**Version:** 0.2.0
**Date:** 2026-03-05

---

## Services

Seven runtime components communicate over a shared Docker Compose network:

| Service | Technology | Port | Role |
|---|---|---|---|
| **Backend API** | Python 3.12 / FastAPI 0.115.6 | 8000 | REST API, agent orchestration, job pipeline |
| **Frontend SPA** | Vue 3.5 / Vite / nginx | 8080 | User interface served by nginx reverse proxy |
| **Java Parser Service** | Java 21 / Spring Boot 3.4.2 | 8090 | AST extraction for Java source files |
| **PostgreSQL** | PostgreSQL 16 + pgvector 0.8.0 | 5432 | Persistent state: jobs, UCG, smells, patches, embeddings |
| **Redis** | Redis 7.4 | 6379 | API response caching, rate limiting |
| **RabbitMQ** | RabbitMQ 3.13 | 5672/15672 | Async job queuing (future) |
| **nginx** | nginx 1.27 alpine | 8080 | Reverse proxy + static SPA hosting |

---

## Request Flow

```
Browser --> nginx:8080
  /api/* --> FastAPI backend:8000
  /*     --> Vue SPA static files
```

A typical job submission:
1. Browser uploads ZIP archive via `POST /api/v1/analyze` (multipart)
2. Backend extracts archive to shared volume `/alm_jobs/alm_job_<uuid>/`
3. Job record created in PostgreSQL with `status=pending`
4. Background task launched: `AnalysisService.run()`
5. Pipeline stages run sequentially, updating `jobs.status` at each step
6. Frontend polls `GET /api/v1/analyze/{job_id}` every 3 seconds
7. On completion, graph data available at `GET /api/v1/graph/{job_id}`

---

## Agent Pipeline

Seven agents run sequentially per job:

```
[1] LanguageDetector  -- file extension scan, detects Java/Python/PHP/JS/TS
[2] Mapper            -- builds UCG by calling adapters per language
       |-- JavaAdapter: POST /parse to java-parser:8090 with {"repoPath": "/alm_jobs/..."}
       |-- PythonASTAdapter: stdlib ast module
       |-- PHPAdapter: nikic/php-parser subprocess
       |-- JSTSAdapter: @typescript-eslint/parser subprocess
[3] SmellDetector     -- rule-based heuristics + LLM (claude-opus-4-6) confirmation
[4] Planner           -- LLM generates prioritized refactor plan
[5] Transformer       -- LLM generates code patches for automated tasks
[6] Validator         -- sandbox-validates each patch (syntax, lint, test)
[7] Learner           -- pgvector embeddings for cross-job similarity (non-critical)
```

Each agent receives a `JobContext` (job_id, repo_path, db_session, job_config, languages).
Agents use `NotImplementedError` gracefully — missing agents log a warning and the pipeline continues.

---

## Shared Volume

`alm_jobs_data` is a named Docker volume mounted at `/alm_jobs` in both `backend` and `java-parser`.
This allows the backend to extract archives once, and the Java Parser to read them directly by path.

```
backend:     /alm_jobs/alm_job_<uuid>/  <-- extracted source code
java-parser: /alm_jobs/alm_job_<uuid>/  <-- read-only access
```

---

## Caching Layer

`app/core/cache.py` provides Redis-backed caching:

| Data | Cache Key | TTL | Invalidated When |
|---|---|---|---|
| Job list | `alm:jobs:p{page}:ps{size}:s{status}` | 15s | Job created or completed |
| Graph data | `alm:graph:{job_id}:p{page}:ps{size}:e{edges}` | 1h | Never (immutable after job completes) |
| Graph metrics | `alm:metrics:{job_id}` | 1h | Never (immutable after job completes) |

All cache operations fail silently if Redis is unavailable.

---

## API Authentication

- API keys stored as bcrypt hashes in `api_keys` table
- `X-API-Key` header required on all endpoints except `/health` and `/admin/api-keys/generate`
- Open bootstrap endpoint `POST /admin/api-keys/generate` creates a `read+write` key — used by
  the frontend SPA on first load to obtain a working key without any prior setup

---

## LLM Integration

All LLM calls go through a provider abstraction (`app/services/llm/base.py`):
- **Primary:** `AnthropicProvider` using `claude-opus-4-6`
- **Fallback:** `OpenAIProvider` using `gpt-4o`
- **Testing:** `StubProvider` (no-op, returns empty responses)

Provider is selected via `LLM_PROVIDER` env var (`anthropic` | `openai` | `stub`).
