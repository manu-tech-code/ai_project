# AI Legacy Modernization Platform (ALM) — Database Schema

**Version:** 0.2.0
**Database:** PostgreSQL 16 with pgvector 0.8.0
**Author:** Alex Chen, Tech Lead & Architect
**Date:** 2026-03-04

---

## Table of Contents

1. [Setup & Extensions](#1-setup--extensions)
2. [Enumerations](#2-enumerations)
3. [Core Tables](#3-core-tables)
4. [UCG Tables](#4-ucg-tables)
5. [Analysis Tables](#5-analysis-tables)
6. [Embeddings Table](#6-embeddings-table)
7. [Auth Tables](#7-auth-tables)
8. [Indexes](#8-indexes)
9. [Constraints Summary](#9-constraints-summary)
10. [Alembic Migration Notes](#10-alembic-migration-notes)

---

## 1. Setup & Extensions

```sql
-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Enable vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable full-text search dictionary
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

---

## 2. Enumerations

```sql
CREATE TYPE job_status AS ENUM (
    'pending',
    'detecting',
    'mapping',
    'analyzing',
    'planning',
    'transforming',
    'validating',
    'complete',
    'failed',
    'cancelled'
);

CREATE TYPE node_type AS ENUM (
    'FILE',
    'MODULE',
    'CLASS',
    'FUNCTION',
    'METHOD',
    'FIELD',
    'VARIABLE',
    'PARAMETER',
    'IMPORT',
    'ANNOTATION',
    'BLOCK',
    'LITERAL',
    'CALL_SITE',
    'TYPE_REF',
    'COMMENT'
);

CREATE TYPE edge_type AS ENUM (
    'CONTAINS',
    'CALLS',
    'EXTENDS',
    'IMPLEMENTS',
    'IMPORTS',
    'USES_TYPE',
    'HAS_PARAMETER',
    'HAS_FIELD',
    'HAS_ANNOTATION',
    'RETURNS',
    'THROWS',
    'OVERRIDES',
    'DEPENDS_ON',
    'INSTANTIATES',
    'READS',
    'WRITES',
    'DEFINED_IN'
);

CREATE TYPE smell_type AS ENUM (
    'god_class',
    'long_method',
    'feature_envy',
    'data_clumps',
    'shotgun_surgery',
    'divergent_change',
    'large_class',
    'primitive_obsession',
    'long_parameter_list',
    'dead_code',
    'circular_dependency',
    'spaghetti_code',
    'lava_flow',
    'tight_coupling',
    'missing_abstraction',
    'anemic_domain_model',
    'singleton_abuse'
);

CREATE TYPE severity_level AS ENUM ('critical', 'high', 'medium', 'low');

CREATE TYPE refactor_pattern AS ENUM (
    'extract_class',
    'extract_method',
    'move_method',
    'introduce_interface',
    'replace_magic_numbers',
    'encapsulate_field',
    'introduce_parameter_object',
    'replace_conditional_with_polymorphism',
    'remove_dead_code',
    'break_circular_dependency',
    'introduce_facade',
    'strangler_fig',
    'decompose_conditional'
);

CREATE TYPE patch_type AS ENUM ('modify', 'create', 'delete', 'rename');

CREATE TYPE task_status AS ENUM ('pending', 'approved', 'rejected', 'applied');

CREATE TYPE patch_status AS ENUM ('pending', 'applied', 'reverted', 'failed');

CREATE TYPE language AS ENUM ('java', 'python', 'php', 'javascript', 'typescript');

CREATE TYPE check_type AS ENUM ('syntax', 'lint', 'test', 'semantic', 'security');
```

---

## 3. Core Tables

### jobs

The central table tracking each analysis run from submission to completion.

```sql
CREATE TABLE jobs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    label               TEXT,
    status              job_status  NOT NULL DEFAULT 'pending',
    current_stage       TEXT,

    -- Archive metadata
    archive_filename    TEXT,
    archive_size_bytes  BIGINT,
    archive_checksum    TEXT,         -- SHA-256 of uploaded file

    -- Extracted code metadata (populated by LanguageDetector)
    languages           TEXT[]        NOT NULL DEFAULT '{}',
    file_count          INTEGER,
    total_lines         INTEGER,

    -- User-supplied configuration
    config              JSONB         NOT NULL DEFAULT '{}',

    -- UCG summary (populated by Mapper)
    ucg_node_count      INTEGER,
    ucg_edge_count      INTEGER,

    -- Smell summary (populated by SmellDetector)
    smell_count         INTEGER,

    -- Patch summary (populated by Transformer)
    patch_count         INTEGER,

    -- Error tracking
    error_message       TEXT,
    error_stage         TEXT,
    retry_count         INTEGER       NOT NULL DEFAULT 0,

    -- Timestamps
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,

    CONSTRAINT jobs_retry_count_non_negative CHECK (retry_count >= 0),
    CONSTRAINT jobs_file_count_positive CHECK (file_count IS NULL OR file_count > 0)
);

COMMENT ON TABLE jobs IS 'Central tracking table for all ALM analysis jobs.';
COMMENT ON COLUMN jobs.config IS 'User-supplied overrides: languages filter, severity thresholds, etc.';
```

---

## 4. UCG Tables

### ucg_nodes

Stores all nodes of the Universal Code Graph for each job.

```sql
CREATE TABLE ucg_nodes (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    node_type       node_type   NOT NULL,
    qualified_name  TEXT        NOT NULL,
    language        language    NOT NULL,
    file_path       TEXT,
    line_start      INTEGER,
    line_end        INTEGER,
    col_start       INTEGER,
    col_end         INTEGER,

    -- All node-type-specific fields stored here as JSONB
    -- Fields vary by node_type (see tech-spec.md section 5.1)
    properties      JSONB       NOT NULL DEFAULT '{}',

    -- pgvector embedding (1536-dim, populated by Learner agent)
    embedding       vector(1536),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ucg_nodes_qualified_name_not_empty
        CHECK (char_length(qualified_name) > 0),
    CONSTRAINT ucg_nodes_lines_valid
        CHECK (line_end IS NULL OR line_start IS NULL OR line_end >= line_start)
);

COMMENT ON TABLE ucg_nodes IS 'Universal Code Graph nodes — language-agnostic representation of all code entities.';
COMMENT ON COLUMN ucg_nodes.properties IS 'Node-type-specific properties (see tech-spec.md UCG Data Model).';
COMMENT ON COLUMN ucg_nodes.embedding IS '1536-dimensional vector embedding for similarity search.';
```

---

### ucg_edges

Stores all directed edges of the Universal Code Graph.

```sql
CREATE TABLE ucg_edges (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    edge_type       edge_type   NOT NULL,
    source_node_id  UUID        NOT NULL REFERENCES ucg_nodes(id) ON DELETE CASCADE,
    target_node_id  UUID        NOT NULL REFERENCES ucg_nodes(id) ON DELETE CASCADE,

    -- Edge-specific properties (e.g., call_count, line_number for CALLS edges)
    properties      JSONB       NOT NULL DEFAULT '{}',
    weight          FLOAT       NOT NULL DEFAULT 1.0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ucg_edges_no_self_loop
        CHECK (source_node_id <> target_node_id),
    CONSTRAINT ucg_edges_weight_positive
        CHECK (weight > 0)
);

COMMENT ON TABLE ucg_edges IS 'Universal Code Graph edges — directed relationships between code entities.';
```

---

## 5. Analysis Tables

### smells

Detected architectural smells with evidence and LLM analysis.

```sql
CREATE TABLE smells (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID            NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    smell_type      smell_type      NOT NULL,
    severity        severity_level  NOT NULL,
    description     TEXT            NOT NULL,
    confidence      FLOAT           NOT NULL,

    -- Array of UCG node IDs that are affected
    affected_node_ids UUID[]        NOT NULL DEFAULT '{}',

    -- Rule-based metrics that triggered detection
    evidence        JSONB           NOT NULL DEFAULT '{}',

    -- LLM-generated explanation (nullable if rule-only detection)
    llm_rationale   TEXT,

    -- Dismissal tracking
    dismissed           BOOLEAN         NOT NULL DEFAULT false,
    dismissed_at        TIMESTAMPTZ,
    dismissed_by        TEXT,
    dismissed_reason    TEXT,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT smells_confidence_range
        CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

COMMENT ON TABLE smells IS 'Architectural smells detected by the SmellDetector agent.';
COMMENT ON COLUMN smells.evidence IS 'Computed graph metrics that triggered detection (fan_in, fan_out, LOC, etc.).';
```

---

### plans

Refactor plans generated by the Planner agent. One plan per job (or versioned if regenerated).

```sql
CREATE TABLE plans (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id                  UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    version                 INTEGER     NOT NULL DEFAULT 1,
    estimated_effort_hours  FLOAT,
    risk_level              severity_level,
    priority_order          UUID[]      NOT NULL DEFAULT '{}',  -- task IDs in priority order
    llm_model               TEXT,
    tokens_used             INTEGER,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT plans_version_positive CHECK (version > 0),
    UNIQUE (job_id, version)
);

COMMENT ON TABLE plans IS 'Refactor plans generated by the Planner agent.';
COMMENT ON COLUMN plans.priority_order IS 'Ordered array of plan_tasks.id values — recommended execution order.';
```

---

### plan_tasks

Individual refactoring tasks within a plan.

```sql
CREATE TABLE plan_tasks (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id             UUID            NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    job_id              UUID            NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    title               TEXT            NOT NULL,
    description         TEXT            NOT NULL,
    smell_ids           UUID[]          NOT NULL DEFAULT '{}',  -- references smells.id
    affected_files      TEXT[]          NOT NULL DEFAULT '{}',
    refactor_pattern    refactor_pattern NOT NULL,
    dependencies        UUID[]          NOT NULL DEFAULT '{}',  -- other plan_tasks.id
    estimated_hours     FLOAT,
    automated           BOOLEAN         NOT NULL DEFAULT true,
    status              task_status     NOT NULL DEFAULT 'pending',
    priority_override   INTEGER,
    notes               TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

COMMENT ON TABLE plan_tasks IS 'Individual refactoring tasks within a plan.';
COMMENT ON COLUMN plan_tasks.automated IS 'True if the Transformer agent can generate a patch automatically.';
COMMENT ON COLUMN plan_tasks.dependencies IS 'task IDs that must be applied before this task.';
```

---

### patches

Code patches generated by the Transformer agent for automated plan tasks.

```sql
CREATE TABLE patches (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID            NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    task_id             UUID            NOT NULL REFERENCES plan_tasks(id) ON DELETE CASCADE,
    file_path           TEXT            NOT NULL,
    patch_type          patch_type      NOT NULL,
    language            language        NOT NULL,
    status              patch_status    NOT NULL DEFAULT 'pending',

    -- Content (stored as TEXT; large patches may be chunked)
    original_content    TEXT            NOT NULL,
    patched_content     TEXT            NOT NULL,
    diff                TEXT            NOT NULL,  -- unified diff format

    -- LLM metadata
    tokens_used         INTEGER,
    model_used          TEXT,

    -- Application tracking
    applied_at          TIMESTAMPTZ,
    applied_by          TEXT,
    reverted_at         TIMESTAMPTZ,
    reverted_reason     TEXT,

    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

COMMENT ON TABLE patches IS 'Code patches generated by the Transformer agent.';
COMMENT ON COLUMN patches.diff IS 'Unified diff format output from difflib.unified_diff.';
```

---

### validation_results

Results of sandbox validation runs for each patch.

```sql
CREATE TABLE validation_results (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    patch_id        UUID        NOT NULL REFERENCES patches(id) ON DELETE CASCADE,
    passed          BOOLEAN     NOT NULL,
    overall_score   FLOAT       NOT NULL,  -- 0.0–1.0

    -- Detailed check results stored as JSONB array
    -- Each element: { check_name, check_type, passed, output, duration_ms }
    checks          JSONB       NOT NULL DEFAULT '[]',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT validation_results_score_range
        CHECK (overall_score >= 0.0 AND overall_score <= 1.0)
);

COMMENT ON TABLE validation_results IS 'Sandbox validation results for each generated patch.';
COMMENT ON COLUMN validation_results.checks IS 'Array of ValidationCheck objects with per-check details.';
```

---

### reports

Modernization report metadata (full content generated on demand).

```sql
CREATE TABLE reports (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Cached report content (JSON, Markdown)
    report_json         JSONB       NOT NULL DEFAULT '{}',
    report_markdown     TEXT,

    -- Summary statistics (denormalized for fast list queries)
    modernization_score INTEGER,    -- 0–100
    total_smells        INTEGER,
    critical_smells     INTEGER,
    patches_generated   INTEGER,
    patches_passed      INTEGER,
    estimated_hours     FLOAT,

    UNIQUE (job_id)
);

COMMENT ON TABLE reports IS 'Cached modernization report data for each completed job.';
COMMENT ON COLUMN reports.modernization_score IS '0-100 score. 100 = no smells, all patches pass validation.';
```

---

## 6. Embeddings Table

### embeddings

Supplementary embeddings table for storing text embeddings indexed for similarity search.

```sql
CREATE TABLE embeddings (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

    -- The entity this embedding represents
    entity_type     TEXT        NOT NULL,  -- 'ucg_node' | 'smell' | 'plan_task' | 'patch'
    entity_id       UUID        NOT NULL,

    -- The text content that was embedded
    content_text    TEXT        NOT NULL,

    -- The vector embedding (1536 dimensions for text-embedding-3-small)
    embedding       vector(1536) NOT NULL,

    model_used      TEXT        NOT NULL DEFAULT 'text-embedding-3-small',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE embeddings IS 'Vector embeddings for semantic similarity search across jobs.';
COMMENT ON COLUMN embeddings.entity_type IS 'Discriminator: ucg_node, smell, plan_task, or patch.';
```

---

## 7. Auth Tables

### api_keys

API key management table. Raw key values are never stored -- only bcrypt hashes.

```sql
CREATE TABLE api_keys (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    label                   TEXT        NOT NULL,
    key_hash                TEXT        NOT NULL UNIQUE,  -- bcrypt hash (work factor 12)
    key_prefix              TEXT        NOT NULL,         -- first 12 chars of raw key (for display)

    -- Authorization
    scopes                  TEXT[]      NOT NULL DEFAULT '{}',  -- ['read', 'write', 'admin']
    rate_limit_per_minute   INTEGER     NOT NULL DEFAULT 100,

    -- Lifecycle
    expires_at              TIMESTAMPTZ,
    revoked                 BOOLEAN     NOT NULL DEFAULT false,
    revoked_at              TIMESTAMPTZ,
    last_used_at            TIMESTAMPTZ,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT api_keys_label_not_empty
        CHECK (char_length(label) > 0),
    CONSTRAINT api_keys_rate_limit_positive
        CHECK (rate_limit_per_minute > 0)
);

COMMENT ON TABLE api_keys IS 'API key store. Raw key values are never persisted.';
COMMENT ON COLUMN api_keys.key_hash IS 'bcrypt hash (cost 12) of the raw API key.';
COMMENT ON COLUMN api_keys.key_prefix IS 'First 12 chars of the raw key for identification in UI.';
COMMENT ON COLUMN api_keys.scopes IS 'Authorization scopes: read, write, admin.';
```

---

## 8. Indexes

```sql
-- jobs: fast lookup by status (for queue consumers)
CREATE INDEX idx_jobs_status ON jobs (status);
CREATE INDEX idx_jobs_created_at ON jobs (created_at DESC);

-- ucg_nodes: primary access patterns
CREATE INDEX idx_ucg_nodes_job_id ON ucg_nodes (job_id);
CREATE INDEX idx_ucg_nodes_job_type ON ucg_nodes (job_id, node_type);
CREATE INDEX idx_ucg_nodes_job_language ON ucg_nodes (job_id, language);
CREATE INDEX idx_ucg_nodes_qualified_name ON ucg_nodes USING gin (qualified_name gin_trgm_ops);

-- ucg_nodes: vector similarity search (IVFFlat index for 1536-dim ANN search)
CREATE INDEX idx_ucg_nodes_embedding ON ucg_nodes
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ucg_edges: primary access patterns
CREATE INDEX idx_ucg_edges_job_id ON ucg_edges (job_id);
CREATE INDEX idx_ucg_edges_job_type ON ucg_edges (job_id, edge_type);
CREATE INDEX idx_ucg_edges_source ON ucg_edges (source_node_id);
CREATE INDEX idx_ucg_edges_target ON ucg_edges (target_node_id);
CREATE INDEX idx_ucg_edges_source_type ON ucg_edges (source_node_id, edge_type);
CREATE INDEX idx_ucg_edges_target_type ON ucg_edges (target_node_id, edge_type);

-- smells: filtering by job and severity
CREATE INDEX idx_smells_job_id ON smells (job_id);
CREATE INDEX idx_smells_job_severity ON smells (job_id, severity);
CREATE INDEX idx_smells_job_type ON smells (job_id, smell_type);
CREATE INDEX idx_smells_dismissed ON smells (job_id, dismissed);

-- plans and tasks
CREATE INDEX idx_plans_job_id ON plans (job_id);
CREATE INDEX idx_plan_tasks_plan_id ON plan_tasks (plan_id);
CREATE INDEX idx_plan_tasks_job_id ON plan_tasks (job_id);
CREATE INDEX idx_plan_tasks_status ON plan_tasks (plan_id, status);

-- patches
CREATE INDEX idx_patches_job_id ON patches (job_id);
CREATE INDEX idx_patches_task_id ON patches (task_id);
CREATE INDEX idx_patches_status ON patches (job_id, status);

-- validation_results
CREATE INDEX idx_validation_results_job_id ON validation_results (job_id);
CREATE INDEX idx_validation_results_patch_id ON validation_results (patch_id);
CREATE INDEX idx_validation_results_passed ON validation_results (job_id, passed);

-- reports
CREATE INDEX idx_reports_job_id ON reports (job_id);
CREATE INDEX idx_reports_generated_at ON reports (generated_at DESC);

-- embeddings
CREATE INDEX idx_embeddings_job_id ON embeddings (job_id);
CREATE INDEX idx_embeddings_entity ON embeddings (entity_type, entity_id);
CREATE INDEX idx_embeddings_vector ON embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- api_keys
CREATE INDEX idx_api_keys_revoked ON api_keys (revoked, expires_at);
```

---

## 9. Constraints Summary

### Referential Integrity

| Table | Column | References | On Delete |
|---|---|---|---|
| ucg_nodes | job_id | jobs.id | CASCADE |
| ucg_edges | job_id | jobs.id | CASCADE |
| ucg_edges | source_node_id | ucg_nodes.id | CASCADE |
| ucg_edges | target_node_id | ucg_nodes.id | CASCADE |
| smells | job_id | jobs.id | CASCADE |
| plans | job_id | jobs.id | CASCADE |
| plan_tasks | plan_id | plans.id | CASCADE |
| plan_tasks | job_id | jobs.id | CASCADE |
| patches | job_id | jobs.id | CASCADE |
| patches | task_id | plan_tasks.id | CASCADE |
| validation_results | job_id | jobs.id | CASCADE |
| validation_results | patch_id | patches.id | CASCADE |
| reports | job_id | jobs.id | CASCADE |
| embeddings | job_id | jobs.id | CASCADE |

### Check Constraints

| Table | Constraint | Expression |
|---|---|---|
| jobs | `jobs_retry_count_non_negative` | `retry_count >= 0` |
| jobs | `jobs_file_count_positive` | `file_count IS NULL OR file_count > 0` |
| ucg_nodes | `ucg_nodes_qualified_name_not_empty` | `char_length(qualified_name) > 0` |
| ucg_nodes | `ucg_nodes_lines_valid` | `line_end IS NULL OR line_start IS NULL OR line_end >= line_start` |
| ucg_edges | `ucg_edges_no_self_loop` | `source_node_id <> target_node_id` |
| ucg_edges | `ucg_edges_weight_positive` | `weight > 0` |
| smells | `smells_confidence_range` | `confidence >= 0.0 AND confidence <= 1.0` |
| plans | `plans_version_positive` | `version > 0` |
| validation_results | `validation_results_score_range` | `overall_score >= 0.0 AND overall_score <= 1.0` |
| api_keys | `api_keys_label_not_empty` | `char_length(label) > 0` |
| api_keys | `api_keys_rate_limit_positive` | `rate_limit_per_minute > 0` |

### Unique Constraints

| Table | Columns |
|---|---|
| plans | (job_id, version) |
| reports | (job_id) |
| api_keys | (key_hash) |

---

## 10. Alembic Migration Notes

### Initial Migration

The first Alembic migration (version `0001_initial`) creates all extensions, enumerations, tables,
and indexes in a single transaction.

### Migration Conventions

- **Naming:** `{version}_{short_description}`, e.g., `0001_initial`, `0002_add_dismissed_by_to_smells`
- **Reversibility:** All migrations must implement both `upgrade()` and `downgrade()`.
- **Enum Changes:** Adding values to PostgreSQL enums requires `ALTER TYPE ... ADD VALUE` which is NOT
  transactional in PostgreSQL. Use a new migration step that creates the new enum and migrates data.
- **Large Table Migrations:** Use concurrent index creation for production deployments:
  `CREATE INDEX CONCURRENTLY` (requires running outside a transaction block).

### SQLAlchemy Model Mapping

| DB Table | SQLAlchemy Model | Location |
|---|---|---|
| jobs | `Job` | `app/models/job.py` |
| ucg_nodes | `UCGNode` | `app/models/ucg.py` |
| ucg_edges | `UCGEdge` | `app/models/ucg.py` |
| smells | `Smell` | `app/models/smell.py` |
| plans | `Plan` | `app/models/plan.py` |
| plan_tasks | `PlanTask` | `app/models/plan.py` |
| patches | `Patch` | `app/models/patch.py` |
| validation_results | `ValidationResult` | `app/models/patch.py` |
| reports | `Report` | `app/models/job.py` |
| embeddings | `Embedding` | `app/models/ucg.py` |
| api_keys | `APIKey` | `app/models/api_key.py` |

### Connection Pool Configuration

```python
# app/core/database.py
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=settings.ALM_ENV == "development",
)
```
