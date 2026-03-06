# AI Legacy Modernization Platform (ALM) — Technical Specification

**Version:** 0.2.0
**Author:** Alex Chen, Tech Lead & Architect
**Date:** 2026-03-04
**Status:** Active

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Technology Stack](#3-technology-stack)
4. [Service Interaction Diagram](#4-service-interaction-diagram)
5. [Universal Code Graph (UCG) Data Model](#5-universal-code-graph-ucg-data-model)
6. [Agent Pipeline](#6-agent-pipeline)
7. [API Endpoint Reference](#7-api-endpoint-reference)
8. [Database Design](#8-database-design)
9. [Queue Architecture](#9-queue-architecture)
10. [LLM Integration](#10-llm-integration)
11. [Security Model](#11-security-model)
12. [Infrastructure & Deployment](#12-infrastructure--deployment)
13. [Testing Strategy](#13-testing-strategy)
14. [Non-Functional Requirements](#14-non-functional-requirements)

---

## 1. Executive Summary

ALM (AI Legacy Modernization Platform) is a multi-service system that ingests legacy codebases written in
Java, PHP, Python, and JavaScript/TypeScript, constructs a language-agnostic Universal Code Graph (UCG),
detects architectural smells, generates LLM-guided refactor plans, produces validated code patches, and
exports modernization reports. The system is designed to be modular, language-agnostic at the analysis
layer, and horizontally scalable.

### Core Value Proposition

| Problem | ALM Solution |
|---|---|
| Manual code archaeology | Automated UCG construction from ASTs |
| Inconsistent smell detection | Rule-based + LLM smell classification |
| Risk of large refactors | Patch sandbox validation before delivery |
| No audit trail | Immutable job/patch/report records |
| Analyst bottleneck | Async pipeline, parallel agent execution |

---

## 2. Architecture Overview

ALM is composed of seven runtime components:

| Component | Technology | Role |
|---|---|---|
| **Backend API** | Python 3.12 / FastAPI 0.115.6 | REST API, orchestration, agent runner |
| **Frontend SPA** | Vue 3.5.13 / TypeScript 5.7.3 | User interface, graph visualization |
| **Java Parser Service** | Java 21 / Spring Boot 3.4.2 | JavaParser-based AST extraction |
| **PostgreSQL** | PostgreSQL 16 + pgvector 0.8.0 | Persistent state, UCG, embeddings |
| **RabbitMQ** | RabbitMQ 3.13 | Async job queuing |
| **Redis** | Redis 7.4 | Cache, job-status pub/sub, rate limiting |
| **nginx** | nginx 1.27 alpine | Reverse proxy, static asset serving |

### Design Principles

1. **Language Neutrality** - The UCG is a common graph schema that all language adapters must populate.
   Agents operate exclusively on the UCG, never on raw source code.
2. **Async-First** - All I/O (DB, LLM, queue, file system) is performed asynchronously using Python asyncio.
3. **Agent Isolation** - Each pipeline stage is an independent agent with a defined input/output contract.
   Agents communicate only via the shared database and can be retried independently.
4. **Immutability** - Completed jobs, patches, and reports are never mutated. New versions create new records.
5. **LLM Abstraction** - All LLM calls go through a provider abstraction layer, making the primary provider
   (Anthropic) swappable with fallback to OpenAI.
6. **Redis Caching** - `app/core/cache.py` provides `cache_get`, `cache_set`, `cache_invalidate` helpers.
   Job lists are cached for 15 seconds; graph data and metrics for 1 hour (completed jobs only). Cache is
   invalidated on job creation and completion. All cache operations fail silently if Redis is unavailable.

---

## 3. Technology Stack

### Exact Version Table

| Component | Package | Version |
|---|---|---|
| Python runtime | python | 3.12 |
| Web framework | fastapi | 0.115.6 |
| ASGI server | uvicorn[standard] | 0.34.0 |
| Data validation | pydantic | 2.10.4 |
| Settings management | pydantic-settings | 2.7.1 |
| ORM | sqlalchemy | 2.0.36 |
| DB migrations | alembic | 1.14.0 |
| PostgreSQL async driver | asyncpg | 0.30.0 |
| AMQP client | aio-pika | 9.5.1 |
| Primary LLM SDK | anthropic | 0.45.0 |
| Secondary LLM SDK | openai | 1.61.0 |
| HTTP client | httpx | 0.28.1 |
| Env management | python-dotenv | 1.0.1 |
| Redis client | redis | 5.2.1 |
| pgvector ORM extension | pgvector | 0.3.6 |
| Linter/formatter | ruff | 0.9.4 |
| Test framework | pytest | 8.3.4 |
| Async test support | pytest-asyncio | 0.25.2 |
| Test coverage | pytest-cov | 6.0.0 |
| Type checker | mypy | 1.14.1 |
| Frontend framework | vue | 3.5.13 |
| Language | typescript | 5.7.3 |
| Build tool | vite | 6.1.0 |
| State management | pinia | 2.3.0 |
| Client-side routing | vue-router | 4.5.0 |
| CSS framework | tailwindcss | 4.0.0 |
| Composition utilities | @vueuse/core | 12.4.0 |
| Graph visualization | cytoscape | 3.30.2 |
| HTTP client (FE) | axios | 1.7.9 |
| Unit test (FE) | vitest | 3.0.5 |
| E2E test (FE) | @playwright/test | 1.50.1 |
| Java version | java | 21 (LTS) |
| Java framework | spring-boot | 3.4.2 |
| Java AST library | javaparser | 3.26.2 |
| Build tool (Java) | maven | 3.9.9 |
| Database | postgresql | 16 |
| Vector extension | pgvector | 0.8.0 |
| Message broker | rabbitmq | 3.13 |
| Cache | redis | 7.4 |
| Reverse proxy | nginx | 1.27 (alpine) |
| Container runtime | docker compose | v2 |

---

## 4. Service Interaction Diagram

```
                     +--------------------------------------------------+
                     |                  CLIENT BROWSER                  |
                     |              Vue 3 SPA (port 8080)                |
                     +---------------------+----------------------------+
                                           | HTTPS / WSS
                     +---------------------v----------------------------+
                     |           nginx 1.27 (reverse proxy)            |
                     |  /api/* -> backend:8000   / -> frontend dist    |
                     +------------------+----------------------------------+
                                        |
              +-------------------------v---------------------------------------------+
              |              FastAPI Backend  Python 3.12 :8000                       |
              |                                                                        |
              |  +------------------------------------------------------------------+  |
              |  |                       Agent Pipeline                             |  |
              |  |  [1] LanguageDetector  ->  detect file languages                 |  |
              |  |  [2] Mapper            ->  build UCG from ASTs                   |  |
              |  |  [3] SmellDetector     ->  rule + LLM analysis                   |  |
              |  |  [4] Planner           ->  generate refactor plan                |  |
              |  |  [5] Transformer       ->  produce code patches                  |  |
              |  |  [6] Validator         ->  sandbox validation                    |  |
              |  |  [7] Learner           ->  store embeddings                      |  |
              |  +------------------------+-----------------------------------------+  |
              +---------------------------+--------------------------------------------+
                                          |
          +-------------------------------+-----------------------------+
          |                              |                             |
+---------v--------+         +-----------v------+          +----------v------+
|  PostgreSQL 16   |         |  RabbitMQ 3.13   |          |   Redis 7.4     |
|  + pgvector      |         |  Exchanges:      |          |  - Job status   |
|                  |         |  - alm.direct    |          |  - LLM cache    |
|  Tables:         |         |  - alm.dlq       |          |  - Rate limit   |
|  - jobs          |         +------------------+          +-----------------+
|  - ucg_nodes     |
|  - ucg_edges     |                    |
|  - smells        |         +----------v-----------------------+
|  - plans         |         |  Java Parser Service             |
|  - patches       |         |  Spring Boot 3.4.2 :8090         |
|  - validations   |         |  JavaParser 3.26.2               |
|  - reports       |         |                                  |
|  - api_keys      |         |  REST POST /parse                |
|  - embeddings    |         |  Input:  {"repoPath": "/alm_jobs/..."} |
+------------------+         |  Output: UCG node/edge JSON      |
                             +----------------------------------+
```

### Data Flow for a Typical Job

```
User uploads ZIP --> POST /api/v1/analyze
                         |
                         v
                  Create Job record (status=PENDING)
                         |
                         v
                  Publish to alm.direct exchange
                         |
                         v
              +---------------------------+
              |   AGENT PIPELINE (async)  |
              |                           |
              |  [1] LanguageDetector     |
              |       detects langs       |
              |            |              |
              |  [2] Mapper               |--> Java parser service (if .java)
              |       builds UCG          |
              |            |              |
              |  [3] SmellDetector        |--> Anthropic API
              |       LLM + rules         |
              |            |              |
              |  [4] Planner              |--> Anthropic API
              |       refactor plan       |
              |            |              |
              |  [5] Transformer          |--> Anthropic API
              |       code patches        |
              |            |              |
              |  [6] Validator            |
              |       sandbox checks      |
              |            |              |
              |  [7] Learner              |--> pgvector
              |       store embeddings    |
              +---------------------------+
                         |
                         v
              Job status = COMPLETE
              Report at GET /api/v1/report/{job_id}
```

---

## 5. Universal Code Graph (UCG) Data Model

The UCG is the central data structure of ALM. It is a directed property graph stored in PostgreSQL.
All language adapters must produce UCG-compliant output.

### 5.1 Node Types

| Node Type | Description | Mandatory Fields |
|---|---|---|
| `FILE` | A source file | `path`, `language`, `size_bytes`, `checksum` |
| `MODULE` | A module, package, or namespace | `qualified_name`, `language` |
| `CLASS` | A class definition | `qualified_name`, `is_abstract`, `is_interface` |
| `FUNCTION` | A standalone function | `qualified_name`, `signature`, `return_type`, `is_async` |
| `METHOD` | A method within a class | `qualified_name`, `signature`, `return_type`, `visibility`, `is_static`, `is_async` |
| `FIELD` | A class-level field or property | `name`, `type_annotation`, `visibility`, `is_static` |
| `VARIABLE` | A local variable or constant | `name`, `type_annotation`, `is_constant` |
| `PARAMETER` | A function/method parameter | `name`, `type_annotation`, `position`, `has_default` |
| `IMPORT` | An import/require statement | `source_module`, `imported_names`, `is_wildcard` |
| `ANNOTATION` | A decorator or annotation | `name`, `arguments` |
| `BLOCK` | A code block (loop, try, if) | `block_type`, `line_start`, `line_end` |
| `LITERAL` | A constant literal value | `value`, `literal_type` |
| `CALL_SITE` | A specific invocation location | `callee_name`, `argument_count`, `line_number` |
| `TYPE_REF` | A reference to a type | `type_name`, `is_generic`, `type_args` |
| `COMMENT` | A doc comment or inline comment | `content`, `comment_type` |

### 5.2 UCG Node Schema (PostgreSQL)

```sql
ucg_nodes
---------
id              UUID        PRIMARY KEY DEFAULT gen_random_uuid()
job_id          UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE
node_type       VARCHAR(32) NOT NULL  -- enum values from 5.1
qualified_name  TEXT        NOT NULL
language        VARCHAR(16) NOT NULL  -- java|python|php|javascript|typescript
file_path       TEXT
line_start      INTEGER
line_end        INTEGER
col_start       INTEGER
col_end         INTEGER
properties      JSONB       NOT NULL DEFAULT '{}'
embedding       vector(1536)          -- pgvector, nullable
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

The `properties` JSONB field contains all node-type-specific fields listed in 5.1. This allows new
node types and fields to be added without schema migrations.

### 5.3 Edge Types

| Edge Type | From Node Type(s) | To Node Type(s) | Description |
|---|---|---|---|
| `CONTAINS` | FILE, MODULE, CLASS | any | Structural containment |
| `CALLS` | FUNCTION, METHOD | FUNCTION, METHOD, CALL_SITE | Function/method invocation |
| `EXTENDS` | CLASS | CLASS | Class inheritance |
| `IMPLEMENTS` | CLASS | CLASS (interface) | Interface implementation |
| `IMPORTS` | FILE, MODULE | MODULE, FILE | Import relationship |
| `USES_TYPE` | CLASS, FUNCTION, METHOD, FIELD, PARAMETER | TYPE_REF, CLASS | Type reference |
| `HAS_PARAMETER` | FUNCTION, METHOD | PARAMETER | Parameter declaration |
| `HAS_FIELD` | CLASS | FIELD | Field ownership |
| `HAS_ANNOTATION` | CLASS, METHOD, FUNCTION, FIELD | ANNOTATION | Decorator / annotation |
| `RETURNS` | FUNCTION, METHOD | TYPE_REF | Return type declaration |
| `THROWS` | FUNCTION, METHOD | TYPE_REF | Exception declaration |
| `OVERRIDES` | METHOD | METHOD | Method override relationship |
| `DEPENDS_ON` | MODULE, FILE | MODULE, FILE | Package-level dependency |
| `INSTANTIATES` | FUNCTION, METHOD | CLASS | Object instantiation |
| `READS` | FUNCTION, METHOD | FIELD, VARIABLE | Read access to field/var |
| `WRITES` | FUNCTION, METHOD | FIELD, VARIABLE | Write access to field/var |
| `DEFINED_IN` | any | FILE | Source file location link |

### 5.4 UCG Edge Schema (PostgreSQL)

```sql
ucg_edges
---------
id              UUID        PRIMARY KEY DEFAULT gen_random_uuid()
job_id          UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE
edge_type       VARCHAR(32) NOT NULL
source_node_id  UUID        NOT NULL REFERENCES ucg_nodes(id) ON DELETE CASCADE
target_node_id  UUID        NOT NULL REFERENCES ucg_nodes(id) ON DELETE CASCADE
properties      JSONB       NOT NULL DEFAULT '{}'
weight          FLOAT       NOT NULL DEFAULT 1.0
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
```

### 5.5 Graph Metrics Derived from UCG

The following metrics are computed post-UCG construction and stored in the job record:

| Metric | Formula | Smell Threshold |
|---|---|---|
| Afferent Coupling (Ca) | Count of inbound CALLS + DEPENDS_ON edges | > 20 |
| Efferent Coupling (Ce) | Count of outbound CALLS + DEPENDS_ON edges | > 15 |
| Instability (I) | Ce / (Ca + Ce) | > 0.9 |
| Cyclomatic Complexity | Unique execution paths through BLOCK nodes | > 10 per function |
| Depth of Inheritance (DIT) | Longest EXTENDS chain | > 5 |
| LCOM | Methods not sharing fields / total methods | > 0.7 |
| Lines of Code | line_end - line_start per node | > 300 per class |
| Fan-in | Count of CALLS edges targeting a node | > 25 |
| Fan-out | Count of CALLS edges originating from a node | > 15 |
| Number of Methods | COUNT(METHOD) per CLASS node | > 30 |

---

## 6. Agent Pipeline

The pipeline consists of 7 agents executed sequentially per job. Each agent receives a `JobContext`
and updates the shared database. Agents are designed to be idempotent -- they can be safely re-run
on the same job without producing duplicate data.

### 6.1 JobContext (shared input to all agents)

```python
class JobContext(BaseModel):
    job_id: UUID
    repo_path: Path           # extracted source root on local filesystem
    languages: list[str]      # populated by LanguageDetector
    job_config: dict          # user-supplied configuration overrides
    # Injected at runtime (not serializable):
    # db_session: AsyncSession
    # llm_provider: LLMProvider
```

### 6.2 Agent 1: LanguageDetector

**Purpose:** Scan the repository and identify all programming languages present.

| Field | Value |
|---|---|
| Input | `repo_path: Path` |
| Output | `languages: list[LanguageInfo]` |
| DB Writes | `jobs.languages`, `jobs.file_count`, `jobs.total_lines` |
| LLM | No |
| External Services | No |

```python
class LanguageInfo(BaseModel):
    language: str            # 'java' | 'python' | 'php' | 'javascript' | 'typescript'
    file_count: int
    total_lines: int
    file_extensions: list[str]
    frameworks_detected: list[str]  # e.g. ['spring', 'django', 'laravel', 'react']
```

**Detection Strategy:**
1. Walk directory tree, group files by extension (.java, .py, .php, .js, .ts, .jsx, .tsx).
2. Sample .java files for Spring/Jakarta EE annotations.
3. Check composer.json for PHP framework (Laravel, Symfony, etc.).
4. Check requirements.txt, pyproject.toml, setup.py for Python framework (Django, Flask, FastAPI).
5. Check package.json dependencies for JS/TS framework (React, Vue, Angular, Next.js).
6. Respect .gitignore and skip binary files, test fixtures, and vendor directories.

---

### 6.3 Agent 2: Mapper (UCG Builder)

**Purpose:** Build the Universal Code Graph by parsing all source files into AST nodes and edges.

| Field | Value |
|---|---|
| Input | `JobContext` with `languages` populated |
| Output | `ucg_stats: UCGStats` |
| DB Writes | Bulk inserts into `ucg_nodes`, `ucg_edges` |
| LLM | No |
| External Services | Java Parser Service (HTTP) for Java files |

```python
class UCGStats(BaseModel):
    node_count: int
    edge_count: int
    nodes_by_type: dict[str, int]   # e.g. {'CLASS': 45, 'METHOD': 312}
    edges_by_type: dict[str, int]
    parse_errors: list[ParseError]

class ParseError(BaseModel):
    file_path: str
    error_message: str
    line_number: int | None
```

**Adapter Dispatch Table:**

| Language | Adapter | Strategy |
|---|---|---|
| `java` | `JavaAdapter` | POST to java-parser-service, returns UCG JSON |
| `python` | `PythonASTAdapter` | stdlib `ast` module, walk AST nodes |
| `php` | `PHPAdapter` | Subprocess call to nikic/php-parser CLI |
| `javascript` | `JSTSAdapter` | Subprocess call to @typescript-eslint/parser |
| `typescript` | `JSTSAdapter` | Same adapter, TypeScript mode enabled |

**Batch Strategy:** Files are processed in batches of 50. UCG nodes and edges are bulk-inserted
using SQLAlchemy `insert()` for PostgreSQL throughput efficiency.

---

### 6.4 Agent 3: SmellDetector

**Purpose:** Identify architectural smells in the UCG using rule-based heuristics and LLM confirmation.

| Field | Value |
|---|---|
| Input | UCG nodes/edges from DB for `job_id` |
| Output | `list[SmellResult]` |
| DB Writes | Inserts into `smells` |
| LLM | Yes -- `claude-opus-4-6` |
| External Services | No |

```python
class SmellResult(BaseModel):
    smell_id: UUID
    smell_type: SmellType
    severity: Literal['critical', 'high', 'medium', 'low']
    affected_nodes: list[UUID]     # ucg_node IDs
    description: str
    evidence: dict                 # metric values that triggered detection
    confidence: float              # 0.0-1.0 (rule score * LLM confidence)
    llm_rationale: str | None      # LLM-generated explanation
```

**SmellType Enum:**

```python
class SmellType(str, Enum):
    GOD_CLASS = "god_class"
    LONG_METHOD = "long_method"
    FEATURE_ENVY = "feature_envy"
    DATA_CLUMPS = "data_clumps"
    SHOTGUN_SURGERY = "shotgun_surgery"
    DIVERGENT_CHANGE = "divergent_change"
    LARGE_CLASS = "large_class"
    PRIMITIVE_OBSESSION = "primitive_obsession"
    LONG_PARAMETER_LIST = "long_parameter_list"
    DEAD_CODE = "dead_code"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    SPAGHETTI_CODE = "spaghetti_code"
    LAVA_FLOW = "lava_flow"
    TIGHT_COUPLING = "tight_coupling"
    MISSING_ABSTRACTION = "missing_abstraction"
    ANEMIC_DOMAIN_MODEL = "anemic_domain_model"
    SINGLETON_ABUSE = "singleton_abuse"
```

**Detection Pipeline:**
1. Run all rule-based detectors against UCG metrics (fast, no LLM cost).
2. Collect candidates per smell type.
3. For each candidate batch, invoke LLM with the serialized UCG subgraph.
4. LLM returns `{ "confirmed": bool, "severity": str, "rationale": str, "confidence": float }`.
5. Merge rule score and LLM confidence. Write confirmed smells to `smells` table.

---

### 6.5 Agent 4: Planner

**Purpose:** Generate a prioritized, dependency-ordered refactor plan from detected smells.

| Field | Value |
|---|---|
| Input | `list[SmellResult]` from DB |
| Output | `RefactorPlan` |
| DB Writes | Inserts into `plans` and `plan_tasks` |
| LLM | Yes -- `claude-opus-4-6` |
| External Services | No |

```python
class RefactorPlan(BaseModel):
    plan_id: UUID
    job_id: UUID
    tasks: list[PlanTask]
    estimated_effort_hours: float
    risk_level: Literal['low', 'medium', 'high', 'critical']
    priority_order: list[UUID]     # task IDs in recommended execution order

class PlanTask(BaseModel):
    task_id: UUID
    title: str
    description: str
    smell_ids: list[UUID]          # smells this task addresses
    affected_files: list[str]
    refactor_pattern: RefactorPattern
    dependencies: list[UUID]       # task IDs that must complete first
    estimated_hours: float
    automated: bool                # True if Transformer can handle automatically
```

**RefactorPattern Enum:**

```python
class RefactorPattern(str, Enum):
    EXTRACT_CLASS = "extract_class"
    EXTRACT_METHOD = "extract_method"
    MOVE_METHOD = "move_method"
    INTRODUCE_INTERFACE = "introduce_interface"
    REPLACE_MAGIC_NUMBERS = "replace_magic_numbers"
    ENCAPSULATE_FIELD = "encapsulate_field"
    INTRODUCE_PARAMETER_OBJECT = "introduce_parameter_object"
    REPLACE_CONDITIONAL_WITH_POLYMORPHISM = "replace_conditional_with_polymorphism"
    REMOVE_DEAD_CODE = "remove_dead_code"
    BREAK_CIRCULAR_DEPENDENCY = "break_circular_dependency"
    INTRODUCE_FACADE = "introduce_facade"
    STRANGLER_FIG = "strangler_fig"
    DECOMPOSE_CONDITIONAL = "decompose_conditional"
```

---

### 6.6 Agent 5: Transformer (Patch Generator)

**Purpose:** Generate concrete code patches for all automated tasks in the refactor plan.

| Field | Value |
|---|---|
| Input | `RefactorPlan` from DB |
| Output | `list[CodePatch]` |
| DB Writes | Inserts into `patches` |
| LLM | Yes -- `claude-opus-4-6` with extended thinking for complex transforms |
| External Services | No |

```python
class CodePatch(BaseModel):
    patch_id: UUID
    task_id: UUID
    file_path: str
    original_content: str
    patched_content: str
    diff: str               # unified diff format (difflib output)
    patch_type: Literal['modify', 'create', 'delete', 'rename']
    language: str
    tokens_used: int
    model_used: str
```

**Generation Strategy:**
1. Filter RefactorPlan to only `automated=True` tasks.
2. For each task, serialize affected source files and relevant UCG subgraph as JSON.
3. Construct structured prompt with: refactor pattern, affected code, constraints, output format.
4. Parse LLM response to extract file modifications (structured JSON output via tool use).
5. Generate unified diff using Python `difflib.unified_diff`.
6. Store original + patched content in `patches` table (no filesystem writes at this stage).

---

### 6.7 Agent 6: Validator

**Purpose:** Validate each code patch in an isolated sandbox environment.

| Field | Value |
|---|---|
| Input | `list[CodePatch]` from DB |
| Output | `list[ValidationResult]` |
| DB Writes | Inserts into `validation_results` |
| LLM | Optional (semantic validation only) |
| External Services | Subprocess sandbox |

```python
class ValidationResult(BaseModel):
    result_id: UUID
    patch_id: UUID
    passed: bool
    checks: list[ValidationCheck]
    overall_score: float        # 0.0-1.0

class ValidationCheck(BaseModel):
    check_name: str
    check_type: Literal['syntax', 'lint', 'test', 'semantic', 'security']
    passed: bool
    output: str
    duration_ms: int
```

**Validation Checks by Language:**

| Language | Syntax Check | Lint Check | Test Check |
|---|---|---|---|
| Python | `ast.parse()` | `ruff check --select ALL` | `pytest --collect-only` |
| Java | `javac` compilation | `checkstyle` | `mvn test -pl <module>` |
| PHP | `php -l` | `phpstan analyse` | `./vendor/bin/phpunit` |
| JS/TS | `tsc --noEmit` | `eslint` | `vitest run` |

**Sandbox Constraints:**
- Isolated temp directory per validation run.
- No outbound network access (process-level restriction via OS namespace).
- Hard timeout: 30 seconds per patch (SIGKILL on timeout).
- Memory limit: 512 MB (enforced via resource.setrlimit).

---

### 6.8 Agent 7: Learner

**Purpose:** Vectorize completed job artifacts and store embeddings for cross-project similarity search.

| Field | Value |
|---|---|
| Input | Complete job data from DB |
| Output | `LearnerOutput` |
| DB Writes | Updates `ucg_nodes.embedding`, inserts into `embeddings` table |
| LLM | Yes -- `text-embedding-3-small` (OpenAI) |
| External Services | No |

```python
class LearnerOutput(BaseModel):
    embeddings_created: int
    patterns_indexed: int
    similar_jobs: list[UUID]   # previously processed jobs with similar smell profiles
```

**Embedding Strategy:**
- Embed CLASS and FUNCTION nodes (qualified_name + surrounding context text).
- Embed each smell description + evidence metrics.
- Embed each plan task description.
- Store all embeddings in `ucg_nodes.embedding` (1536-dim vector) and `embeddings` table.
- Query pgvector with cosine similarity to find historically similar code patterns.

---

## 7. API Endpoint Reference

All endpoints are prefixed with `/api/v1`. Authentication via `X-API-Key` header (required on all
endpoints except `/api/v1/health`). See `docs/api-spec.md` for full request/response schemas.

### 7.1 Analysis Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/analyze` | Submit a new analysis job (multipart/form-data upload) |
| `GET` | `/analyze/{job_id}` | Get job status and metadata |
| `GET` | `/analyze` | List all jobs (paginated, filterable by status) |
| `DELETE` | `/analyze/{job_id}` | Cancel a pending job or delete a completed one |

### 7.2 Graph Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/graph/{job_id}` | Get full UCG (paginated nodes+edges) |
| `GET` | `/graph/{job_id}/nodes` | List nodes with type/language filters |
| `GET` | `/graph/{job_id}/nodes/{node_id}` | Get single node detail with neighbors |
| `GET` | `/graph/{job_id}/edges` | List edges with type filters |
| `GET` | `/graph/{job_id}/metrics` | Get computed graph metrics |
| `POST` | `/graph/{job_id}/subgraph` | Extract subgraph by seed node set and depth |

### 7.3 Smells Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/smells/{job_id}` | List all smells for a job (filterable by severity/type) |
| `GET` | `/smells/{job_id}/{smell_id}` | Get single smell detail with evidence |
| `POST` | `/smells/{job_id}/{smell_id}/dismiss` | Dismiss a smell (requires reason) |
| `GET` | `/smells/{job_id}/summary` | Aggregated smell statistics by type and severity |

### 7.4 Plan Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/plan/{job_id}` | Get the refactor plan for a job |
| `GET` | `/plan/{job_id}/tasks` | List all plan tasks |
| `GET` | `/plan/{job_id}/tasks/{task_id}` | Get single task detail |
| `PATCH` | `/plan/{job_id}/tasks/{task_id}` | Approve, reject, or reorder a task |
| `POST` | `/plan/{job_id}/regenerate` | Trigger plan regeneration (LLM re-run) |

### 7.5 Patches Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/patches/{job_id}` | List all patches for a job |
| `GET` | `/patches/{job_id}/{patch_id}` | Get single patch with full diff |
| `POST` | `/patches/{job_id}/{patch_id}/apply` | Mark patch as applied |
| `POST` | `/patches/{job_id}/{patch_id}/revert` | Mark patch as reverted |
| `GET` | `/patches/{job_id}/export` | Export all approved patches as .zip archive |

### 7.6 Validation Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/validate/{job_id}` | List all validation results for a job |
| `GET` | `/validate/{job_id}/{result_id}` | Get single validation result with check details |
| `POST` | `/validate/{job_id}/rerun` | Re-run validation for failed patches |

### 7.7 Report Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/report/{job_id}` | Get modernization report as JSON |
| `GET` | `/report/{job_id}/pdf` | Export report as PDF (streamed) |
| `GET` | `/report/{job_id}/markdown` | Export report as Markdown |
| `GET` | `/report` | List all completed reports |

### 7.8 Admin Endpoints

| Method | Path | Auth Required | Description |
|---|---|---|---|
| `GET` | `/health` | No | System health check |
| `GET` | `/admin/metrics` | Yes (admin) | Prometheus-format application metrics |
| `POST` | `/admin/api-keys/generate` | No | Bootstrap: auto-generate a read+write key (used by frontend on first load) |
| `POST` | `/admin/api-keys` | Yes (admin) | Create a new API key with custom scopes |
| `GET` | `/admin/api-keys` | Yes (admin) | List all API keys |
| `DELETE` | `/admin/api-keys/{key_id}` | Yes (admin) | Revoke an API key |

---

## 8. Database Design

See `docs/db-schema.md` for the full PostgreSQL DDL with all table definitions, constraints, and indexes.

### Job Status State Machine

```
+-----------+
|  PENDING  |
+-----+-----+
      | queue consumer picks up job
      v
+-----------+
| DETECTING |  (LanguageDetector running)
+-----+-----+
      |
      v
+-----------+
|  MAPPING  |  (Mapper/UCG builder running)
+-----+-----+
      |
      v
+-----------+
| ANALYZING |  (SmellDetector running)
+-----+-----+
      |
      v
+-----------+
| PLANNING  |  (Planner running)
+-----+-----+
      |
      v
+--------------+
| TRANSFORMING |  (Transformer running)
+------+-------+
       |
       v
+--------------+
|  VALIDATING  |  (Validator running)
+------+-------+
       |
       v
+----------+
| COMPLETE |
+----------+

FAILED    <-- any stage on unrecoverable error (max 3 retries)
CANCELLED <-- user DELETE /analyze/{job_id} while PENDING
```

Status values: `pending`, `detecting`, `mapping`, `analyzing`, `planning`, `transforming`,
`validating`, `complete`, `failed`, `cancelled`

---

## 9. Queue Architecture

### RabbitMQ Exchange/Queue Layout

```
Exchange: alm.direct (direct, durable)
  +-- Routing Key: analyze   --> Queue: alm.analyze
  +-- Routing Key: map       --> Queue: alm.map
  +-- Routing Key: detect    --> Queue: alm.detect
  +-- Routing Key: plan      --> Queue: alm.plan
  +-- Routing Key: transform --> Queue: alm.transform
  +-- Routing Key: validate  --> Queue: alm.validate
  +-- Routing Key: learn     --> Queue: alm.learn

Exchange: alm.dlq (fanout, durable)
  +-- Queue: alm.dead-letter  (failed messages after max 3 retries)
```

### Message Schema

```json
{
  "message_id": "uuid-v4",
  "job_id": "uuid-v4",
  "stage": "analyze | map | detect | plan | transform | validate | learn",
  "timestamp": "2026-03-04T12:00:00Z",
  "retry_count": 0,
  "payload": {}
}
```

### Dead Letter Policy

- Messages are rejected (not nacked) after 3 consecutive processing failures.
- DLQ messages are stored for 7 days for manual inspection.
- An alert is emitted to Redis pub/sub channel `alm:alerts` on DLQ ingestion.

---

## 10. LLM Integration

### Provider Abstraction

All LLM calls go through `app.services.llm.base.LLMProvider` (abstract base class). The interface
exposes two methods: `complete(prompt, ...)` and `embed(texts)`. Concrete implementations:

- `AnthropicProvider` -- primary, uses `claude-opus-4-6` (configurable via `ANTHROPIC_MODEL` env var)
- `OpenAIProvider` -- fallback, uses `gpt-4o` for completion, `text-embedding-3-small` for embeddings
- `StubProvider` -- no-op implementation used in unit tests (no LLM API calls)

### Model Selection Per Agent

| Agent | Model | Justification |
|---|---|---|
| SmellDetector | claude-opus-4-6 | Best code reasoning, structured JSON output |
| Planner | claude-opus-4-6 | Complex multi-step planning with dependency graph |
| Transformer | claude-opus-4-6 | Accurate code generation, tool-use for structured output |
| Learner | text-embedding-3-small | Cost-efficient embeddings, 1536 dims matches pgvector config |

### Rate Limiting & Retry Policy

- Anthropic tier 1: 60 requests/minute, 100k tokens/minute.
- OpenAI tier 1: 500 requests/minute.
- Both providers: exponential backoff with jitter (initial delay 1s, max delay 60s, max retries 5).
- Redis tracks per-API-key LLM request counts with 60-second sliding window TTL.

### Prompt Engineering Conventions

- All prompts use XML-tagged sections: `<task>`, `<context>`, `<output_format>`, `<constraints>`.
- Structured output enforced via Anthropic tool use / OpenAI function calling.
- System prompt establishes the ALM expert persona and output contract.
- Temperature: 0.2 for code generation, 0.7 for plan narrative.

---

## 11. Security Model

### Authentication

- API keys stored in `api_keys` table, hashed with bcrypt (work factor 12).
- Raw key value returned once at creation time, never stored or re-shown.
- `X-API-Key` header required on all endpoints except `/api/v1/health`.
- Keys have: optional expiry timestamp, scope list, per-key rate limits, owner label.

### Authorization Scopes

| Scope | Permissions |
|---|---|
| `read` | GET all non-admin endpoints |
| `write` | POST/PATCH/DELETE on jobs, smells, plans, patches |
| `admin` | All endpoints including /admin/* (key creation, revocation, metrics) |

### Input Validation & Safety

- Uploaded archives limited to 500 MB (configurable via `MAX_UPLOAD_SIZE_MB`).
- Allowed archive types: .zip, .tar.gz, .tgz. MIME type verified.
- Path traversal prevention: all extracted paths validated against job sandbox directory.
- Archive bomb protection: limit to 50,000 files and 2 GB uncompressed.
- All Pydantic models use strict mode. No `model_config = ConfigDict(extra='allow')`.

### Sandbox Isolation (Validator)

- Patch validation runs in a separate process via `asyncio.create_subprocess_exec`.
- Temp directory created per validation run, cleaned up after completion.
- No outbound network calls from sandbox process (enforced via OS-level restrictions).
- Hard timeout: 30 seconds per validation run (SIGKILL on timeout).
- Memory limit: 512 MB (enforced via `resource.setrlimit`).

---

## 12. Infrastructure & Deployment

### Docker Compose Services

| Service | Image | Port(s) | Depends On | Notes |
|---|---|---|---|---|
| `postgres` | postgres:16-alpine | 5432 | -- | |
| `redis` | redis:7.4-alpine | 6379 | -- | |
| `rabbitmq` | rabbitmq:3.13-management | 5672, 15672 | -- | |
| `backend` | ./backend (Dockerfile) | 8000 | postgres, redis, rabbitmq | Mounts `alm_jobs_data` at `/alm_jobs` |
| `java-parser` | ./java-parser-service (Dockerfile) | 8090 | -- | Mounts `alm_jobs_data` at `/alm_jobs` |
| `nginx` | nginx:1.27-alpine | 8080 | backend | Serves SPA; proxies `/api/*` to backend |

Frontend is built as static assets during Docker image build and served by nginx.

**Shared Volume:** `alm_jobs_data` is a named Docker volume mounted at `/alm_jobs` in both the
`backend` and `java-parser` containers. The backend extracts uploaded archives here so that the
Java Parser Service can read them directly via filesystem path (sent as `repoPath` in the JSON body).

### Backend Environment Variables

```
# Database
DATABASE_URL=postgresql+asyncpg://alm:alm@postgres:5432/alm
DATABASE_POOL_SIZE=20
DATABASE_POOL_MAX_OVERFLOW=10

# Cache
REDIS_URL=redis://redis:6379/0

# Queue
RABBITMQ_URL=amqp://alm:alm@rabbitmq:5672/

# LLM Providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Services
JAVA_PARSER_URL=http://java-parser:8090

# Job storage (shared volume path — also mounted in java-parser container)
ALM_JOBS_DIR=/alm_jobs

# Application
SECRET_KEY=<random-256-bit-hex>
ALM_ENV=production
LOG_LEVEL=INFO
MAX_UPLOAD_SIZE_MB=500
SANDBOX_TIMEOUT_SECONDS=30
MAX_CONCURRENT_JOBS=10
```

### Health Check Endpoints

- `GET /api/v1/health` returns `{ "status": "ok", "version": "0.2.0", "services": {...} }`
- Checks: database connectivity, Redis ping, RabbitMQ connection, java-parser reachability.

---

## 13. Testing Strategy

### Test Pyramid

```
         +-----------------------------+
         |         E2E Tests           |  Playwright -- full browser flows
         |        (~5% of suite)       |  Tests: upload -> graph -> report
         +-----------------------------+
         |     Integration Tests       |  pytest + httpx AsyncClient
         |       (~25% of suite)       |  Real PostgreSQL (testcontainers)
         +-----------------------------+  Mocked RabbitMQ, real Redis
         |         Unit Tests          |  pytest-asyncio
         |       (~70% of suite)       |  Mocked DB, LLM, queue
         +-----------------------------+
```

### Test Configuration

- `pytest.ini_options.asyncio_mode = "auto"` -- all async tests auto-collected.
- Test DB: isolated PostgreSQL instance per test session via testcontainers-python.
- LLM calls: fully mocked in unit tests using `unittest.mock.AsyncMock`.
- Integration tests use fixture LLM responses from `tests/fixtures/llm_responses/`.
- Coverage threshold: 80% overall, 90% for agent pipeline (`app/agents/`).
- CI runs: lint (ruff) -> typecheck (mypy) -> unit tests -> integration tests -> E2E (nightly).

### Test File Organization

```
tests/
+-- unit/
|   +-- agents/           # one test file per agent
|   +-- adapters/         # one test file per language adapter
|   +-- services/         # LLM provider, queue, report service
|   +-- api/              # API route unit tests (mocked dependencies)
+-- integration/
|   +-- test_pipeline.py  # full pipeline integration test
|   +-- test_api.py       # API integration with real DB
|   +-- test_java_parser.py
+-- e2e/                  # Playwright tests
+-- fixtures/
    +-- sample_repos/     # tiny Java, Python, PHP, JS repos for testing
    +-- llm_responses/    # recorded LLM responses for replay
```

---

## 14. Non-Functional Requirements

| Requirement | Target | Measurement |
|---|---|---|
| Job processing time (10k LOC) | < 5 minutes end-to-end | Prometheus histogram |
| API response time (read endpoints) | < 200ms p99 | nginx access log |
| API response time (write endpoints) | < 500ms p99 (excl. async work) | Prometheus histogram |
| UCG construction throughput | 50k nodes/minute | Agent metrics |
| LLM call latency (SmellDetector) | < 30s per smell batch | LLM provider metrics |
| System availability | 99.5% (excluding maintenance) | Uptime monitoring |
| Max concurrent jobs | 10 (configurable via env) | Queue depth monitoring |
| Database connection pool | 20 async connections per backend instance | SQLAlchemy pool stats |
| Max archive size | 500 MB | FastAPI request size limit |
| Report export (PDF) | < 10s | Prometheus histogram |
| Embeddings batch size | 100 nodes per OpenAI API call | Learner agent metrics |
| RabbitMQ message TTL | 24 hours (DLQ: 7 days) | RabbitMQ management |
| Redis key TTL (job status) | 1 hour after job completion | Redis config |
