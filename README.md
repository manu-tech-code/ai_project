# AI Legacy Modernization Platform (ALM)

An AI-driven, agentic platform that ingests legacy codebases, builds a language-agnostic
Universal Code Graph (UCG), detects architectural smells, generates prioritized refactor
roadmaps, produces safe incremental code patches, validates changes in sandboxed runners,
and exports detailed modernization reports.

> **Current status:** Phase 1 — Java adapter, UCG extraction, and basic smell detection
> are working. Phases 2–5 are actively scaffolded and in progress.

---

## Table of Contents

1. [Vision & Goals](#vision--goals)
2. [Architecture](#architecture)
3. [Agent Pipeline](#agent-pipeline)
4. [MVP Phases](#mvp-phases)
5. [Tech Stack](#tech-stack)
6. [Repository Structure](#repository-structure)
7. [Quick Start](#quick-start)
8. [API Reference](#api-reference)
9. [CLI Reference](#cli-reference)
10. [Configuration](#configuration)
11. [Development Guide](#development-guide)
12. [Testing](#testing)
13. [Roadmap to Production](#roadmap-to-production)
14. [Contributing](#contributing)

---

## Vision & Goals

ALM turns the painful, manual process of modernizing legacy software into a structured,
AI-assisted, auditable workflow. It is designed to serve as:

- A **production-grade enterprise tool** for modernizing Java, PHP, Python, and JS/TS codebases
- A **SaaS/open-source platform** with pluggable language adapters and LLM providers
- A **learning platform** for mastering agentic AI coding patterns at scale

**What the platform delivers per analyzed repository:**

| Output | Description |
|---|---|
| Universal Code Graph | Language-agnostic structural graph (nodes, edges, metrics) |
| Smell Report | Prioritized list of architectural smells with severity and rationale |
| Refactor Roadmap | Ordered migration tasks with effort estimates and risk scores |
| Code Patches | Git-backed `.patch` files per transformation step |
| Validation Results | Compilation, test suite, and smoke test outcomes per patch |
| Modernization Report | Exportable `.md` report + downloadable ZIP with all patches |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web UI / CLI                             │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST / WebSocket
┌────────────────────────────▼────────────────────────────────────┐
│              FastAPI Orchestrator (Python)                       │
│  /analyze  /status  /graph  /smells  /plan  /patches  /report   │
└──┬─────────────────────────┬───────────────────────────────┬────┘
   │                         │                               │
   ▼                         ▼                               ▼
Language Adapter        Agent Workers                  LLM Provider Layer
Layer                   (via RabbitMQ)                 (OpenAI / Anthropic /
                                                        Google / Local)
┌──────────────┐    ┌───────────────────┐
│ Java Adapter │    │  Code Mapper      │        ┌──────────────────┐
│ (port 8090)  │    │  Smell Detector   │        │  UCG Store       │
│ PHP Adapter  │    │  Refactor Planner │◄──────►│  (PostgreSQL +   │
│ Python AST   │    │  Transformer      │        │   Neo4j / graph) │
│ JS/TS Adapter│    │  Validator        │        └──────────────────┘
└──────────────┘    │  Learner          │
                    └───────────────────┘        ┌──────────────────┐
                                                 │  Vector DB       │
                                                 │  (pgvector /     │
                                                 │   Weaviate)      │
                                                 └──────────────────┘
                    ┌───────────────────┐
                    │  Validation       │
                    │  Sandbox          │
                    │  (Docker / K8s)   │
                    └───────────────────┘
```

**Key principle:** All agents operate on the UCG — never on raw source files. Language
Adapters are responsible for normalizing language-specific ASTs into UCG nodes and edges.

---

## Agent Pipeline

The platform uses a 7-agent pipeline. Each agent is stateless, containerizable, and
communicates via the message bus.

### Agent 1 — Language Detector & Adapter Loader
**Status:** ✅ Implemented (Java) | 🔲 Stubbed (PHP, Python, JS/TS)

Detects the language composition of a repository, selects the correct adapters, and
coordinates their execution.

- Walks the repo and detects languages by extension and content heuristics
- Loads and invokes the matching `LanguageAdapter` for each detected language
- Emits raw UCG fragments per language to the Code Mapper Agent

**Adapters:**
| Language | Implementation | Status |
|---|---|---|
| Java | JavaParser via Spring Boot microservice (port 8090) | ✅ Working |
| Python | Built-in `ast` module | 🔲 Stubbed |
| PHP | `nikic/php-parser` microservice | 🔲 Stubbed |
| JavaScript/TypeScript | Babel / TS Compiler API microservice | 🔲 Stubbed |

---

### Agent 2 — Code Mapper Agent
**Status:** ✅ Implemented

Merges all UCG fragments from adapters into a single project-wide UCG.

- Deduplicates and resolves cross-language dependencies
- Extracts: modules, classes, functions, controllers, entities, data access points
- Computes per-node metrics: LOC, cyclomatic complexity, coupling score, cohesion score
- Stores the completed UCG in the UCG Store

**UCG Node fields:** `id`, `type`, `language`, `loc`, `complexity`, `public_api`,
`sinks`, `sources`, `metadata` (file path, line numbers)

**UCG Edge types:** `calls`, `imports`, `inherits`, `data_flow`, `dependency`, `contains`

---

### Agent 3 — Smell Detection Agent
**Status:** ✅ Implemented (rule-based) | 🔲 Planned (ML-assisted)

Runs rule-based and ML-assisted detectors against the UCG.

**Currently detected smells:**
| Smell | Trigger | Severity |
|---|---|---|
| God Class | Class with 10+ methods | Medium |
| Large Class | Class with 300+ LOC | Low |
| JDBC Direct Usage | Raw JDBC calls detected | Medium |

**Planned detectors:**
- Cyclic dependencies between modules
- Anemic domain model (data classes with no logic)
- Feature envy (method uses another class's data excessively)
- Shotgun surgery (one change requires many small edits across files)
- Strangler fig candidates (legacy endpoints wrappable by new service)
- Security sinks without input validation
- ML-assisted smell scoring using historical refactor patterns from Vector DB

Each smell includes: `id`, `type`, `affected_node`, `severity`, `rationale`,
`suggested_action`, `effort_estimate`

---

### Agent 4 — Refactor Planner Agent
**Status:** 🔲 Stubbed — next priority

Produces a stepwise, minimum-risk migration roadmap from the smell report and UCG.

- Orders refactor tasks to minimize cascading breakage (topological sort on UCG)
- Generates concrete task descriptions: "Extract `OrderService` from `OrderController`"
- Estimates effort per task using LOC, complexity, and dependency count heuristics
- Assigns risk scores and suggests rollback strategies
- Outputs a structured `plan.json` consumable by the Transformer Agent

**Output format per task:**
```json
{
  "task_id": "task-001",
  "type": "extract_service",
  "target_node": "OrderController",
  "description": "Extract business logic into OrderService",
  "effort_points": 5,
  "risk": "low",
  "depends_on": [],
  "rollback": "git revert <patch-sha>"
}
```

---

### Agent 5 — Transformation Agent
**Status:** 🔲 Stubbed — Phase 2

Generates actual code patches for each planned task using LLM + language-specific templates.

- Uses prompt templates per transformation type (extract service, replace JDBC with ORM, etc.)
- Calls LLM provider with UCG context + source code snippet
- Produces unified `.patch` files, one per task
- Ensures naming consistency and preserves public API signatures
- Stores patches in Git-backed patch store with metadata

**Transformation types (planned):**
- Extract service / extract class
- Replace JDBC → JPA/Hibernate
- Convert singleton to Spring Bean
- Extract configuration to environment variables
- Decompose God Class into focused classes
- Migrate JSP to REST endpoint + separate frontend

---

### Agent 6 — Validation Agent
**Status:** 🔲 Stubbed — Phase 3

Validates each generated patch in an ephemeral sandbox before it is surfaced to the user.

- Applies patch to a clean branch in a sandboxed container
- Runs: compilation check → unit tests → integration smoke tests
- Performs runtime diffing where feasible (log shape, response structure)
- Reports pass/fail per patch with full build output
- Failed patches are flagged and fed back to Transformation Agent for retry

**Sandbox options:** Docker-in-Docker (MVP), Kubernetes ephemeral jobs (production)

---

### Agent 7 — Learner / Reflection Agent
**Status:** 🔲 Stubbed — Phase 5

Improves the platform over time by storing outcomes in the Vector DB.

- Stores successful transformations as embeddings (code + context + patch)
- Feeds successful patterns back to Planner (improves effort estimates)
- Improves prompt templates for Transformation Agent based on validation outcomes
- Enables few-shot retrieval: "find similar transformations to this God Class"

---

## MVP Phases

### Phase 0 — Foundation ✅ Complete
- [x] Repo structure and CI/CD baseline
- [x] FastAPI app with REST endpoints
- [x] Docker Compose stack (Postgres, RabbitMQ, Java parser)
- [x] CLI scaffold (`alm` command via Typer)
- [x] Environment configuration system

### Phase 1 — Java UCG & Smell Detection ✅ In Progress
- [x] Java language adapter (JavaParser microservice)
- [x] Code Mapper Agent → UCG construction
- [x] Smell Detection Agent (god classes, large classes, JDBC)
- [x] REST APIs: `/analyze`, `/status`, `/graph`, `/smells`
- [x] Phase 1 UI (Cytoscape.js graph visualization)
- [ ] Persistent UCG storage (PostgreSQL)
- [ ] Advanced smell detectors (cyclic deps, anemic model)
- [ ] Expand Java parsing: inheritance edges, interface resolution, data flow

### Phase 2 — Refactor Planner & Patch Generation 🔲 Next
- [ ] Refactor Planner Agent (topological ordering, effort estimation)
- [ ] LLM provider wiring (OpenAI / Anthropic)
- [ ] Transformation Agent (extract service, JDBC→ORM templates)
- [ ] Git-backed patch generation and storage
- [ ] REST APIs: `/plan`, `/patches`
- [ ] Patch review UI (diff viewer, approve/reject workflow)
- [ ] CLI: `alm plan`, `alm refactor`

### Phase 3 — Validation Sandbox 🔲 Planned
- [ ] Validation Agent (Docker sandbox runner)
- [ ] Patch apply → compile → test pipeline
- [ ] REST API: `/validate`
- [ ] Retry loop: Transformer → Validator → Transformer
- [ ] Pass/fail reporting per patch with build output
- [ ] CI integration (GitHub Actions hook)

### Phase 4 — Multi-Language Support 🔲 Planned
- [ ] PHP adapter (nikic/php-parser microservice)
- [ ] Python adapter (ast module, full implementation)
- [ ] JS/TS adapter (Babel/TS Compiler API microservice)
- [ ] Planner generalized to pure UCG (language-agnostic tasks)
- [ ] Cross-language dependency resolution in UCG

### Phase 5 — Memory, Learning & Production Polish 🔲 Planned
- [ ] Vector DB integration (pgvector / Weaviate)
- [ ] Learner Agent (embeddings, pattern retrieval, prompt improvement)
- [ ] Report generator: exportable `.md` + patch ZIP bundle
- [ ] REST API: `/report`
- [ ] Full React frontend (dependency graph, smell heatmap, roadmap timeline)
- [ ] Authentication & authorization (API keys / OAuth)
- [ ] Kubernetes production deployment manifests
- [ ] Comprehensive test suite (unit + integration + E2E)
- [ ] Open-source documentation and contribution guide

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| API / Orchestrator | Python 3.11, FastAPI, Uvicorn | REST endpoints, agent orchestration |
| CLI | Typer | Developer command-line interface |
| Data validation | Pydantic v2 | Request/response models, UCG schema |
| Java parsing | Spring Boot 3.2, JavaParser 3.25 | Java AST → UCG fragments |
| PHP parsing | nikic/php-parser (microservice) | PHP AST → UCG fragments |
| Python parsing | Built-in `ast` module | Python AST → UCG fragments |
| JS/TS parsing | Babel / TS Compiler API (microservice) | JS/TS AST → UCG fragments |
| Message bus | RabbitMQ 3 | Async agent communication |
| UCG persistence | PostgreSQL 16 + pgvector | UCG nodes, edges, embeddings |
| Graph queries | Neo4j (optional) | Rich graph traversal for large UCGs |
| Vector DB / Memory | pgvector or Weaviate | Pattern retrieval, learning memory |
| LLM provider | OpenAI / Anthropic / Google (pluggable) | Planner reasoning, patch generation |
| Frontend | React, Cytoscape.js, D3 | Graph visualization, review UI |
| Validation sandbox | Docker-in-Docker / K8s jobs | Safe patch testing |
| Container orchestration | Docker Compose (dev), Kubernetes (prod) | Service deployment |

---

## Repository Structure

```
ai_project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── cli.py               # Typer CLI
│   │   ├── core/
│   │   │   ├── config.py        # Settings (env-driven)
│   │   │   └── logging.py       # Structured logging
│   │   ├── api/
│   │   │   └── routes.py        # REST route definitions
│   │   ├── agents/
│   │   │   ├── base.py          # Abstract Agent class
│   │   │   ├── mapper.py        # Code Mapper Agent ✅
│   │   │   ├── smell.py         # Smell Detection Agent ✅
│   │   │   ├── planner.py       # Refactor Planner Agent 🔲
│   │   │   ├── transformer.py   # Transformation Agent 🔲
│   │   │   ├── validator.py     # Validation Agent 🔲
│   │   │   └── learner.py       # Learner Agent 🔲
│   │   ├── adapters/
│   │   │   ├── base.py          # Abstract LanguageAdapter
│   │   │   ├── java.py          # Java adapter ✅
│   │   │   ├── python.py        # Python adapter 🔲
│   │   │   ├── php.py           # PHP adapter 🔲
│   │   │   └── js_ts.py         # JS/TS adapter 🔲
│   │   ├── ucg/
│   │   │   ├── models.py        # UCG node/edge Pydantic models
│   │   │   └── store.py         # UCG store (in-memory → PostgreSQL)
│   │   └── services/
│   │       ├── analysis.py      # Analysis orchestration
│   │       ├── llm/
│   │       │   ├── base.py      # Abstract LlmProvider
│   │       │   └── openai.py    # OpenAI provider 🔲
│   │       ├── queue/
│   │       │   └── base.py      # MessageBus (RabbitMQ)
│   │       └── validation/
│   │           └── runner.py    # Sandbox runner
│   └── pyproject.toml
├── frontend/
│   ├── public/
│   │   ├── index.html           # Phase 1 UI
│   │   └── app.js               # Cytoscape.js graph rendering
│   └── src/
│       └── main.tsx             # Full React app (Phase 5)
├── java-parser-service/         # Spring Boot JavaParser microservice
│   └── src/main/java/...
├── infra/
│   ├── docker-compose.yml       # Dev stack
│   └── .env.example             # Environment variable template
├── docs/
│   ├── architecture.md
│   └── roadmap.md
├── scripts/
│   └── dev.sh                   # Start backend in dev mode
├── tests/
│   └── test_smoke.py
└── ai_legacy_modernization_platform_report.md   # Full project plan
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Java 17+ and Maven (for the Java parser service)
- Docker and Docker Compose (for the full dev stack)

### 1. Start the infrastructure

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up -d
```

This starts PostgreSQL (port 5432), RabbitMQ (port 5672 / management UI 15672), and
the Java parser service (port 8090).

### 2. Start the backend

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e backend
uvicorn app.main:app --reload --app-dir backend
```

Backend is available at `http://localhost:8000`.

### 3. (Optional) Run the Java parser service standalone

```bash
cd java-parser-service
./mvnw spring-boot:run
# or: mvn spring-boot:run
```

Parser service is available at `http://localhost:8090/parse`.

### 4. Open the UI

```
http://localhost:8000/ui
```

Enter a path to a local Java repository and click **Analyze**.

---

## API Reference

| Method | Endpoint | Description | Status |
|---|---|---|---|
| `POST` | `/api/analyze` | Submit a repo for analysis | ✅ |
| `GET` | `/api/status/{job_id}` | Poll analysis job status | ✅ |
| `GET` | `/api/graph/{job_id}` | Retrieve UCG (nodes + edges) | ✅ |
| `GET` | `/api/smells/{job_id}` | Retrieve detected smells | ✅ |
| `GET` | `/api/plan/{job_id}` | Retrieve refactor plan | 🔲 Phase 2 |
| `GET` | `/api/patches/{job_id}` | List generated patches | 🔲 Phase 2 |
| `POST` | `/api/validate/{patch_id}` | Trigger sandbox validation | 🔲 Phase 3 |
| `GET` | `/api/report/{job_id}` | Download modernization report | 🔲 Phase 5 |
| `GET` | `/health` | Health check | ✅ |

**Analyze request:**
```json
POST /api/analyze
{
  "repo_path": "/absolute/path/to/your/repo"
}
```

**Response:**
```json
{
  "job_id": "abc123",
  "status": "queued"
}
```

---

## CLI Reference

```bash
# Analyze a repository
alm analyze --repo /path/to/legacy-repo

# Generate a refactor plan (Phase 2)
alm plan --repo /path/to/legacy-repo --out plan.json

# Apply a specific refactor task as a patch (Phase 2)
alm refactor --task task-001 --branch refactor/extract-order-service

# Run validation on a patch (Phase 3)
alm validate --patch patches/task-001.patch

# Export modernization report (Phase 5)
alm report --job-id abc123 --out ./reports/
```

---

## Configuration

All configuration is driven by environment variables. Copy `infra/.env.example` to
`infra/.env` and adjust values:

```bash
# LLM
LLM_PROVIDER=openai                    # openai | anthropic | google | local
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Database
POSTGRES_URL=postgresql://postgres:postgres@localhost:5432/alm

# Message bus
MESSAGE_BUS_URL=amqp://guest:guest@localhost:5672/

# Java parser service
JAVA_PARSER_URL=http://localhost:8090/parse
JAVA_PARSER_TIMEOUT_SECONDS=30

# Vector DB (Phase 5)
VECTOR_DB_PROVIDER=pgvector            # pgvector | weaviate | pinecone
WEAVIATE_URL=http://localhost:8080

# Environment
ENV=dev                                # dev | staging | production
```

---

## Development Guide

### Running agents locally

Each agent can be exercised directly via the analysis service:

```python
from app.services.analysis import run_analysis
result = run_analysis("/path/to/repo")
print(result.smells)
```

### Adding a new language adapter

1. Create `backend/app/adapters/<language>.py`
2. Subclass `LanguageAdapter` from `adapters/base.py`
3. Implement `parse(repo_path: str) -> dict` returning `{"nodes": [...], "edges": [...]}`
4. Register the adapter in `services/analysis.py` language dispatch

### Adding a new smell detector

1. Open `backend/app/agents/smell.py`
2. Add a new detection method following the existing pattern
3. Append results to the smells list with `id`, `type`, `affected_node`, `severity`,
   `rationale`, `suggested_action`, `effort_estimate`

### Adding a new LLM provider

1. Create `backend/app/services/llm/<provider>.py`
2. Subclass `LlmProvider` from `services/llm/base.py`
3. Implement `complete(prompt: str) -> str`
4. Set `LLM_PROVIDER=<provider>` in `.env`

### Running linting

```bash
cd backend
ruff check .
ruff format .
```

---

## Testing

```bash
# Install test dependencies
pip install -e "backend[dev]"

# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

**Test coverage targets by phase:**

| Phase | Target |
|---|---|
| Phase 1 | UCG model validation, adapter contract tests, smell detector unit tests |
| Phase 2 | Planner ordering logic, patch format validation |
| Phase 3 | Sandbox runner integration tests, retry loop |
| Phase 5 | Full E2E: repo → smells → plan → patch → validation → report |

---

## Roadmap to Production

| Capability | Phase | Priority |
|---|---|---|
| Persistent UCG storage (PostgreSQL) | 1 | High |
| Refactor Planner Agent | 2 | High |
| LLM provider wiring (OpenAI) | 2 | High |
| Transformation Agent + patch generation | 2 | High |
| Patch review UI | 2 | Medium |
| Validation sandbox (Docker) | 3 | High |
| CI integration (GitHub Actions) | 3 | Medium |
| PHP adapter | 4 | Medium |
| Python + JS/TS adapters | 4 | Medium |
| Vector DB + Learner Agent | 5 | Medium |
| Report export (`.md` + ZIP) | 5 | Medium |
| Full React frontend | 5 | Medium |
| Auth / API keys | 5 | High |
| Kubernetes deployment | 5 | High |
| Comprehensive test suite | All | High |
| Security scanning on patches | 3+ | High |

**Production readiness checklist:**
- [ ] All agents fully implemented and tested
- [ ] PostgreSQL replaces all in-memory stores
- [ ] RabbitMQ message bus wired for async agent execution
- [ ] Validation sandbox running in Kubernetes
- [ ] Authentication implemented (API keys minimum)
- [ ] Structured logging and distributed tracing (OpenTelemetry)
- [ ] Health checks and readiness probes on all services
- [ ] Horizontal scaling tested under load
- [ ] Security: OWASP checks on all REST endpoints
- [ ] Data retention and deletion policy documented and enforced

---

## Contributing

1. Fork the repo and create a branch from `main`
2. Follow the adapter / agent patterns described in [Development Guide](#development-guide)
3. Add tests for any new agent or adapter
4. Open a PR with a description of the change and the phase it belongs to

See `ai_legacy_modernization_platform_report.md` for the full architectural vision and
detailed phase plan.

---

_Author: Emmanuel Larbi · AI Legacy Modernization Platform · 2026_
