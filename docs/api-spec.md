# AI Legacy Modernization Platform (ALM) — REST API Specification

**Version:** 0.2.0
**Author:** Alex Chen, Tech Lead & Architect
**Date:** 2026-03-04
**Base URL:** `/api/v1`
**Authentication:** `X-API-Key: <key>` header required on all endpoints except `/health`
**Content-Type:** `application/json` (unless noted as multipart/form-data)

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Common Schemas](#2-common-schemas)
3. [Analysis Endpoints](#3-analysis-endpoints)
4. [Graph Endpoints](#4-graph-endpoints)
5. [Smells Endpoints](#5-smells-endpoints)
6. [Plan Endpoints](#6-plan-endpoints)
7. [Patches Endpoints](#7-patches-endpoints)
8. [Validation Endpoints](#8-validation-endpoints)
9. [Report Endpoints](#9-report-endpoints)
10. [Admin Endpoints](#10-admin-endpoints)
11. [Error Responses](#11-error-responses)
12. [Status Codes Reference](#12-status-codes-reference)

---

## 1. Authentication

All requests must include the API key in the `X-API-Key` header:

```
X-API-Key: alm_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

API keys are created via `POST /api/v1/admin/api-keys` (requires an existing `admin`-scoped key).

For first-time setup or browser clients without a key, use the open bootstrap endpoint:
`POST /api/v1/admin/api-keys/generate` (no auth required — creates a key with `read` + `write` scopes).

### Key Format

```
alm_{env}_{32-char-hex}
```

Examples:
- `alm_live_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4`
- `alm_test_00000000000000000000000000000001`

### Authentication Error

```json
HTTP 401 Unauthorized
{
  "error": "unauthorized",
  "message": "Invalid or missing API key",
  "request_id": "req_01j..."
}
```

---

## 2. Common Schemas

### Pagination Query Parameters

All list endpoints accept:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | integer | 1 | Page number (1-indexed) |
| `page_size` | integer | 50 | Items per page (max: 200) |

### Paginated Response Envelope

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 342,
    "total_pages": 7,
    "has_next": true,
    "has_prev": false
  }
}
```

### UUID Format

All IDs are UUID v4 strings: `"3fa85f64-5717-4562-b3fc-2c963f66afa6"`

### Timestamp Format

All timestamps are ISO 8601 UTC: `"2026-03-04T12:00:00.000Z"`

---

## 3. Analysis Endpoints

### POST /analyze

Submit a new analysis job by uploading a source code archive.

**Content-Type:** `multipart/form-data`

**Request Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `archive` | file | Yes | Source archive (.zip, .tar.gz, .tgz), max 500 MB |
| `label` | string | No | Human-readable job label (max 200 chars) |
| `config` | string (JSON) | No | Job configuration overrides (see below) |

**Config JSON Schema:**

```json
{
  "languages": ["java", "python"],
  "skip_patterns": ["**/test/**", "**/vendor/**"],
  "smell_severity_threshold": "medium",
  "max_patches_per_task": 5,
  "enable_extended_thinking": false
}
```

**Response 202 Accepted:**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "label": "My Legacy Service v1.0",
  "created_at": "2026-03-04T12:00:00.000Z",
  "estimated_duration_seconds": 300,
  "links": {
    "self": "/api/v1/analyze/3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "graph": "/api/v1/graph/3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "report": "/api/v1/report/3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
}
```

**Error Responses:**

| Status | Error | Condition |
|---|---|---|
| 400 | `invalid_archive` | Unsupported file format or corrupted archive |
| 400 | `archive_too_large` | Archive exceeds MAX_UPLOAD_SIZE_MB |
| 400 | `archive_bomb` | Too many files or uncompressed size too large |
| 422 | `invalid_config` | Config JSON is malformed or has invalid fields |

---

### GET /analyze/{job_id}

Get job status and full metadata.

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `job_id` | UUID | Job identifier |

**Response 200 OK:**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "analyzing",
  "label": "My Legacy Service v1.0",
  "created_at": "2026-03-04T12:00:00.000Z",
  "updated_at": "2026-03-04T12:02:15.000Z",
  "completed_at": null,
  "duration_seconds": null,
  "languages": ["java", "python"],
  "file_count": 342,
  "total_lines": 48291,
  "archive_size_bytes": 12582912,
  "config": {
    "smell_severity_threshold": "medium"
  },
  "current_stage": "analyzing",
  "stage_progress": {
    "detecting": "complete",
    "mapping": "complete",
    "analyzing": "running",
    "planning": "pending",
    "transforming": "pending",
    "validating": "pending"
  },
  "error": null,
  "ucg_stats": {
    "node_count": 4821,
    "edge_count": 19203
  },
  "smell_count": null,
  "patch_count": null
}
```

**Status values:** `pending`, `detecting`, `mapping`, `analyzing`, `planning`, `transforming`,
`validating`, `complete`, `failed`, `cancelled`

**Error Responses:**

| Status | Error | Condition |
|---|---|---|
| 404 | `job_not_found` | No job with this ID exists |

---

### GET /analyze

List jobs with optional filters.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | string | (all) | Filter by status value |
| `page` | integer | 1 | Page number |
| `page_size` | integer | 50 | Items per page |

**Response 200 OK:**

```json
{
  "data": [
    {
      "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "status": "complete",
      "label": "My Legacy Service v1.0",
      "created_at": "2026-03-04T12:00:00.000Z",
      "completed_at": "2026-03-04T12:04:32.000Z",
      "duration_seconds": 272,
      "languages": ["java"],
      "file_count": 342,
      "smell_count": 18,
      "patch_count": 12
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 7,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

---

### DELETE /analyze/{job_id}

Cancel a pending job or delete a completed one. Running jobs cannot be deleted.

**Response 204 No Content** (success, no body)

**Error Responses:**

| Status | Error | Condition |
|---|---|---|
| 404 | `job_not_found` | No job with this ID |
| 409 | `job_running` | Job is currently running and cannot be deleted |

---

## 4. Graph Endpoints

### GET /graph/{job_id}

Get the full UCG for a completed job (paginated).

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | integer | 1 | Page number |
| `page_size` | integer | 100 | Items per page (max 500) |
| `include_edges` | boolean | true | Include edges in response |

**Response 200 OK:**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "nodes": [
    {
      "id": "node-uuid-1",
      "node_type": "CLASS",
      "qualified_name": "com.example.service.UserService",
      "language": "java",
      "file_path": "src/main/java/com/example/service/UserService.java",
      "line_start": 12,
      "line_end": 289,
      "col_start": 0,
      "col_end": 1,
      "properties": {
        "is_abstract": false,
        "is_interface": false
      }
    }
  ],
  "edges": [
    {
      "id": "edge-uuid-1",
      "edge_type": "CALLS",
      "source_node_id": "node-uuid-1",
      "target_node_id": "node-uuid-2",
      "weight": 1.0,
      "properties": {}
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 100,
    "total_items": 4821,
    "total_pages": 49,
    "has_next": true,
    "has_prev": false
  }
}
```

---

### GET /graph/{job_id}/nodes

List UCG nodes with filters.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `node_type` | string | Filter by node type (CLASS, METHOD, FUNCTION, etc.) |
| `language` | string | Filter by language |
| `file_path` | string | Filter by file path prefix |
| `search` | string | Full-text search on qualified_name |
| `page` | integer | Page number |
| `page_size` | integer | Items per page |

**Response 200 OK:** Paginated list of node objects (no edges).

---

### GET /graph/{job_id}/nodes/{node_id}

Get a single node with its direct neighbors.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `depth` | integer | 1 | Neighbor traversal depth (max 3) |

**Response 200 OK:**

```json
{
  "node": {
    "id": "node-uuid-1",
    "node_type": "CLASS",
    "qualified_name": "com.example.service.UserService",
    "language": "java",
    "file_path": "src/main/java/com/example/service/UserService.java",
    "line_start": 12,
    "line_end": 289,
    "properties": {
      "is_abstract": false,
      "is_interface": false
    }
  },
  "incoming_edges": [
    {
      "edge_type": "CALLS",
      "source_node_id": "node-uuid-5",
      "source_node_type": "METHOD",
      "source_qualified_name": "com.example.controller.UserController.getUser"
    }
  ],
  "outgoing_edges": [
    {
      "edge_type": "CALLS",
      "target_node_id": "node-uuid-9",
      "target_node_type": "METHOD",
      "target_qualified_name": "com.example.repository.UserRepository.findById"
    }
  ]
}
```

---

### GET /graph/{job_id}/edges

List UCG edges with filters.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `edge_type` | string | Filter by edge type (CALLS, EXTENDS, IMPLEMENTS, etc.) |
| `source_node_id` | UUID | Only edges from this source node |
| `target_node_id` | UUID | Only edges to this target node |
| `page` | integer | Page number |
| `page_size` | integer | Items per page |

**Response 200 OK:** Paginated list of edge objects.

---

### GET /graph/{job_id}/metrics

Get computed graph metrics for the job.

**Response 200 OK:**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "computed_at": "2026-03-04T12:03:00.000Z",
  "summary": {
    "total_nodes": 4821,
    "total_edges": 19203,
    "average_coupling": 4.2,
    "max_cyclomatic_complexity": 42,
    "circular_dependency_count": 3,
    "dead_code_node_count": 87
  },
  "top_coupled_nodes": [
    {
      "node_id": "node-uuid-1",
      "qualified_name": "com.example.service.UserService",
      "afferent_coupling": 28,
      "efferent_coupling": 19,
      "instability": 0.40
    }
  ],
  "top_complex_functions": [
    {
      "node_id": "node-uuid-2",
      "qualified_name": "com.example.util.DataProcessor.process",
      "cyclomatic_complexity": 42,
      "lines_of_code": 198
    }
  ]
}
```

---

### POST /graph/{job_id}/subgraph

Extract a subgraph around a set of seed nodes.

**Request Body:**

```json
{
  "seed_node_ids": ["node-uuid-1", "node-uuid-2"],
  "depth": 2,
  "edge_types": ["CALLS", "EXTENDS", "IMPLEMENTS"],
  "direction": "both"
}
```

**Field definitions:**

| Field | Type | Default | Description |
|---|---|---|---|
| `seed_node_ids` | UUID[] | required | Starting nodes for traversal |
| `depth` | integer | 2 | BFS depth (max 5) |
| `edge_types` | string[] | (all) | Edge types to traverse |
| `direction` | string | "both" | "inbound", "outbound", or "both" |

**Response 200 OK:** Graph object with `nodes`, `edges`, and `pagination`.

---

## 5. Smells Endpoints

### GET /smells/{job_id}

List all architectural smells detected for a job.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `severity` | string | Filter: critical, high, medium, low |
| `smell_type` | string | Filter by SmellType enum value |
| `dismissed` | boolean | Include dismissed smells (default: false) |
| `page` | integer | Page number |
| `page_size` | integer | Items per page |

**Response 200 OK:**

```json
{
  "data": [
    {
      "smell_id": "smell-uuid-1",
      "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "smell_type": "god_class",
      "severity": "critical",
      "description": "UserService has 47 methods and 892 lines. It handles authentication, authorization, profile management, and email notifications.",
      "confidence": 0.97,
      "dismissed": false,
      "affected_nodes": [
        {
          "node_id": "node-uuid-1",
          "node_type": "CLASS",
          "qualified_name": "com.example.service.UserService"
        }
      ],
      "evidence": {
        "method_count": 47,
        "lines_of_code": 892,
        "efferent_coupling": 23,
        "lcom": 0.81
      },
      "llm_rationale": "This class violates the Single Responsibility Principle by combining multiple concerns including authentication, email, and profile management.",
      "created_at": "2026-03-04T12:02:30.000Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 18,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

---

### GET /smells/{job_id}/{smell_id}

Get full detail for a single smell.

**Response 200 OK:** Full smell object with all `evidence` and `llm_rationale` fields.

**Error Responses:**

| Status | Error | Condition |
|---|---|---|
| 404 | `smell_not_found` | No smell with this ID for this job |

---

### POST /smells/{job_id}/{smell_id}/dismiss

Dismiss a smell with a reason (marks it as a known/acceptable issue).

**Request Body:**

```json
{
  "reason": "This class is intentionally a facade and its complexity is managed by the team.",
  "dismissed_by": "user@example.com"
}
```

**Response 200 OK:**

```json
{
  "smell_id": "smell-uuid-1",
  "dismissed": true,
  "dismissed_at": "2026-03-04T14:00:00.000Z",
  "dismissed_by": "user@example.com",
  "reason": "This class is intentionally a facade and its complexity is managed by the team."
}
```

---

### GET /smells/{job_id}/summary

Aggregated smell statistics.

**Response 200 OK:**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "total_smells": 18,
  "dismissed_smells": 2,
  "active_smells": 16,
  "by_severity": {
    "critical": 3,
    "high": 5,
    "medium": 7,
    "low": 3
  },
  "by_type": {
    "god_class": 2,
    "long_method": 4,
    "circular_dependency": 3,
    "dead_code": 6,
    "tight_coupling": 3
  },
  "affected_files": 24,
  "estimated_tech_debt_hours": 87.5
}
```

---

## 6. Plan Endpoints

### GET /plan/{job_id}

Get the refactor plan for a job.

**Response 200 OK:**

```json
{
  "plan_id": "plan-uuid-1",
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "draft",
  "estimated_effort_hours": 87.5,
  "risk_level": "high",
  "task_count": 12,
  "automated_task_count": 8,
  "priority_order": ["task-uuid-1", "task-uuid-3", "task-uuid-2"],
  "created_at": "2026-03-04T12:03:00.000Z",
  "tasks": [
    {
      "task_id": "task-uuid-1",
      "title": "Extract UserService into bounded contexts",
      "description": "Split UserService into AuthService, ProfileService, and NotificationService following DDD bounded context principles.",
      "smell_ids": ["smell-uuid-1"],
      "affected_files": [
        "src/main/java/com/example/service/UserService.java"
      ],
      "refactor_pattern": "extract_class",
      "dependencies": [],
      "estimated_hours": 12.0,
      "automated": true,
      "status": "pending"
    }
  ]
}
```

**Task status values:** `pending`, `approved`, `rejected`, `applied`

---

### GET /plan/{job_id}/tasks

List all tasks in the plan.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `status` | string | Filter: pending, approved, rejected, applied |
| `automated` | boolean | Filter by automated flag |
| `page` | integer | Page number |
| `page_size` | integer | Items per page |

**Response 200 OK:** Paginated list of task objects.

---

### GET /plan/{job_id}/tasks/{task_id}

Get full detail for a single task.

**Response 200 OK:** Full task object with all fields.

---

### PATCH /plan/{job_id}/tasks/{task_id}

Update a task status or add notes.

**Request Body (any subset):**

```json
{
  "status": "approved",
  "priority_override": 1,
  "notes": "Reviewed and approved by tech lead on 2026-03-04."
}
```

**Response 200 OK:** Updated task object.

**Error Responses:**

| Status | Error | Condition |
|---|---|---|
| 400 | `invalid_status_transition` | Cannot change from current status to requested status |
| 404 | `task_not_found` | No task with this ID for this plan |

---

### POST /plan/{job_id}/regenerate

Trigger LLM plan regeneration. Requires that smells have been detected.

**Request Body:**

```json
{
  "focus_smell_types": ["god_class", "circular_dependency"],
  "exclude_task_ids": ["task-uuid-3"],
  "max_tasks": 15
}
```

**Response 202 Accepted:**

```json
{
  "message": "Plan regeneration queued",
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "new_plan_id": "plan-uuid-2"
}
```

---

## 7. Patches Endpoints

### GET /patches/{job_id}

List all code patches generated for a job.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `status` | string | Filter: pending, applied, reverted, failed |
| `language` | string | Filter by programming language |
| `task_id` | UUID | Filter by plan task |
| `page` | integer | Page number |
| `page_size` | integer | Items per page |

**Response 200 OK:**

```json
{
  "data": [
    {
      "patch_id": "patch-uuid-1",
      "task_id": "task-uuid-1",
      "file_path": "src/main/java/com/example/service/UserService.java",
      "patch_type": "modify",
      "language": "java",
      "status": "pending",
      "validation_passed": true,
      "tokens_used": 4821,
      "model_used": "claude-opus-4-6",
      "created_at": "2026-03-04T12:03:30.000Z"
    }
  ],
  "pagination": { ... }
}
```

---

### GET /patches/{job_id}/{patch_id}

Get a single patch with the full diff.

**Response 200 OK:**

```json
{
  "patch_id": "patch-uuid-1",
  "task_id": "task-uuid-1",
  "file_path": "src/main/java/com/example/service/UserService.java",
  "patch_type": "modify",
  "language": "java",
  "status": "pending",
  "diff": "--- a/src/main/java/com/example/service/UserService.java\n+++ b/src/main/java/com/example/service/UserService.java\n@@ -1,6 +1,6 @@\n ...",
  "original_content": "public class UserService { ... }",
  "patched_content": "public class AuthService { ... }",
  "validation_passed": true,
  "tokens_used": 4821,
  "model_used": "claude-opus-4-6",
  "created_at": "2026-03-04T12:03:30.000Z",
  "applied_at": null,
  "reverted_at": null
}
```

---

### POST /patches/{job_id}/{patch_id}/apply

Mark a patch as applied (user confirms they applied it to their codebase).

**Request Body:**

```json
{
  "applied_by": "user@example.com",
  "notes": "Applied via git cherry-pick abc1234"
}
```

**Response 200 OK:**

```json
{
  "patch_id": "patch-uuid-1",
  "status": "applied",
  "applied_at": "2026-03-04T15:00:00.000Z",
  "applied_by": "user@example.com"
}
```

---

### POST /patches/{job_id}/{patch_id}/revert

Mark a patch as reverted.

**Request Body:**

```json
{
  "reason": "Caused integration test failures in CI pipeline."
}
```

**Response 200 OK:**

```json
{
  "patch_id": "patch-uuid-1",
  "status": "reverted",
  "reverted_at": "2026-03-04T16:00:00.000Z",
  "reason": "Caused integration test failures in CI pipeline."
}
```

---

### GET /patches/{job_id}/export

Export all patches with status `pending` or `applied` as a ZIP archive.

**Response 200 OK:**
- Content-Type: `application/zip`
- Content-Disposition: `attachment; filename="alm-patches-{job_id}.zip"`
- Body: Binary ZIP containing one unified diff (.patch) file per patch

---

## 8. Validation Endpoints

### GET /validate/{job_id}

List all validation results for a job.

**Response 200 OK:**

```json
{
  "data": [
    {
      "result_id": "result-uuid-1",
      "patch_id": "patch-uuid-1",
      "passed": true,
      "overall_score": 0.95,
      "check_summary": {
        "syntax": true,
        "lint": true,
        "test": true,
        "semantic": true,
        "security": false
      },
      "created_at": "2026-03-04T12:04:00.000Z"
    }
  ],
  "pagination": { ... }
}
```

---

### GET /validate/{job_id}/{result_id}

Get full validation result with all check details.

**Response 200 OK:**

```json
{
  "result_id": "result-uuid-1",
  "patch_id": "patch-uuid-1",
  "passed": true,
  "overall_score": 0.95,
  "checks": [
    {
      "check_name": "python_syntax",
      "check_type": "syntax",
      "passed": true,
      "output": "No syntax errors found.",
      "duration_ms": 45
    },
    {
      "check_name": "ruff_lint",
      "check_type": "lint",
      "passed": true,
      "output": "All checks passed. 0 issues found.",
      "duration_ms": 312
    },
    {
      "check_name": "security_scan",
      "check_type": "security",
      "passed": false,
      "output": "B105: Possible hardcoded password string at line 42.",
      "duration_ms": 891
    }
  ],
  "created_at": "2026-03-04T12:04:00.000Z"
}
```

---

### POST /validate/{job_id}/rerun

Re-run validation for all failed patches in a job.

**Response 202 Accepted:**

```json
{
  "message": "Validation re-run queued",
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "patches_queued": 3
}
```

---

## 9. Report Endpoints

### GET /report/{job_id}

Get the complete modernization report as JSON.

**Response 200 OK:**

```json
{
  "report_id": "report-uuid-1",
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "generated_at": "2026-03-04T12:05:00.000Z",
  "job_label": "My Legacy Service v1.0",
  "executive_summary": {
    "total_files_analyzed": 342,
    "total_lines_analyzed": 48291,
    "languages": ["java", "python"],
    "smells_found": 18,
    "smells_critical": 3,
    "patches_generated": 12,
    "patches_validated": 12,
    "patches_passed_validation": 10,
    "estimated_tech_debt_hours": 87.5,
    "modernization_score": 42
  },
  "smell_breakdown": {
    "by_severity": {
      "critical": 3,
      "high": 5,
      "medium": 7,
      "low": 3
    },
    "by_type": {
      "god_class": 2,
      "long_method": 4,
      "circular_dependency": 3
    }
  },
  "plan_summary": {
    "total_tasks": 12,
    "automated_tasks": 8,
    "estimated_effort_hours": 87.5,
    "risk_level": "high"
  },
  "patch_summary": {
    "total_patches": 12,
    "by_language": { "java": 10, "python": 2 },
    "by_type": { "modify": 9, "create": 3 },
    "validation_pass_rate": 0.833
  },
  "recommendations": [
    {
      "priority": 1,
      "title": "Extract UserService god class immediately",
      "impact": "Reduces coupling for 23 dependent modules",
      "effort_hours": 12.0
    }
  ],
  "similar_jobs": [
    {
      "job_id": "previous-job-uuid",
      "label": "Legacy ERP Module",
      "similarity_score": 0.87,
      "key_finding": "Same god_class + circular_dependency pattern resolved successfully"
    }
  ]
}
```

**modernization_score**: 0-100. 100 = no smells detected, all patches pass validation.
Computed as: `max(0, 100 - sum(severity_weights) - coupling_penalty)`.

---

### GET /report/{job_id}/pdf

Export the report as a PDF document.

**Response 200 OK:**
- Content-Type: `application/pdf`
- Content-Disposition: `attachment; filename="alm-report-{job_id}.pdf"`
- Body: Binary PDF stream

---

### GET /report/{job_id}/markdown

Export the report as a Markdown document.

**Response 200 OK:**
- Content-Type: `text/markdown; charset=utf-8`
- Content-Disposition: `attachment; filename="alm-report-{job_id}.md"`
- Body: UTF-8 Markdown text

---

### GET /report

List all completed reports.

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `page` | integer | Page number |
| `page_size` | integer | Items per page |

**Response 200 OK:** Paginated list of report summary objects (no full detail).

---

## 10. Admin Endpoints

### POST /admin/api-keys/generate

Bootstrap endpoint to auto-generate an API key. **No authentication required.**

Used by the frontend SPA on first load to obtain a working key when none is stored in `localStorage`.

**Request Body:** None (empty body)

**Response 200 OK:**

```json
{
  "key": "alm_live_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "label": "auto-generated",
  "scopes": ["read", "write"],
  "created_at": "2026-03-05T10:00:00.000Z"
}
```

The key is stored in browser `localStorage` under key `alm_api_key` and injected into all subsequent
requests via the `X-API-Key` header. The frontend `AppHeader` also provides a manual "Generate Key"
button as a fallback.

---

### GET /health

System health check. No authentication required.

**Response 200 OK:**

```json
{
  "status": "ok",
  "version": "0.2.0",
  "environment": "production",
  "timestamp": "2026-03-04T12:00:00.000Z",
  "services": {
    "database": { "status": "ok", "latency_ms": 2 },
    "redis": { "status": "ok", "latency_ms": 1 },
    "rabbitmq": { "status": "ok", "latency_ms": 3 },
    "java_parser": { "status": "ok", "latency_ms": 12 }
  }
}
```

**Response 503 Service Unavailable** if any critical service is down.

---

### GET /admin/metrics

Prometheus-format application metrics. Requires `admin` scope.

**Response 200 OK:**
- Content-Type: `text/plain; version=0.0.4`
- Body: Prometheus text format

---

### POST /admin/api-keys

Create a new API key. Requires `admin` scope.

**Request Body:**

```json
{
  "label": "CI Pipeline Key",
  "scopes": ["read", "write"],
  "expires_at": "2027-01-01T00:00:00.000Z",
  "rate_limit_per_minute": 100
}
```

**Field definitions:**

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | string | Yes | Human-readable key name |
| `scopes` | string[] | Yes | One or more of: `read`, `write`, `admin` |
| `expires_at` | ISO8601 | No | Expiry timestamp (null = never) |
| `rate_limit_per_minute` | integer | No | Override global rate limit |

**Response 201 Created:**

```json
{
  "key_id": "key-uuid-1",
  "key": "alm_live_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
  "label": "CI Pipeline Key",
  "scopes": ["read", "write"],
  "expires_at": "2027-01-01T00:00:00.000Z",
  "rate_limit_per_minute": 100,
  "created_at": "2026-03-04T12:00:00.000Z",
  "warning": "This key value will not be shown again. Store it securely now."
}
```

---

### GET /admin/api-keys

List all API keys. Key values are never returned in list responses.

**Response 200 OK:**

```json
{
  "data": [
    {
      "key_id": "key-uuid-1",
      "label": "CI Pipeline Key",
      "scopes": ["read", "write"],
      "expires_at": "2027-01-01T00:00:00.000Z",
      "rate_limit_per_minute": 100,
      "created_at": "2026-03-04T12:00:00.000Z",
      "last_used_at": "2026-03-04T11:55:00.000Z",
      "revoked": false
    }
  ],
  "pagination": { ... }
}
```

---

### DELETE /admin/api-keys/{key_id}

Revoke an API key immediately. Revoked keys cannot be re-activated.

**Response 204 No Content** (success, no body)

**Error Responses:**

| Status | Error | Condition |
|---|---|---|
| 404 | `key_not_found` | No key with this ID |
| 409 | `key_already_revoked` | Key was already revoked |

---

## 11. Error Responses

All error responses follow a standard envelope:

```json
{
  "error": "snake_case_error_code",
  "message": "Human-readable description of the error.",
  "request_id": "req_01j9abc123def456",
  "details": {}
}
```

The `details` field is optional and contains field-specific validation errors for 422 responses:

```json
{
  "error": "validation_error",
  "message": "Request body validation failed.",
  "request_id": "req_01j9abc123def456",
  "details": {
    "fields": [
      {
        "field": "config.smell_severity_threshold",
        "message": "must be one of: critical, high, medium, low"
      }
    ]
  }
}
```

---

## 12. Status Codes Reference

| Code | Meaning | When Used |
|---|---|---|
| 200 | OK | Successful GET, PATCH |
| 201 | Created | Successful POST that creates a resource |
| 202 | Accepted | Request accepted for async processing |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Malformed request, invalid file type, file too large |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | Valid key but insufficient scope |
| 404 | Not Found | Resource with given ID does not exist |
| 409 | Conflict | Action not allowed given current resource state |
| 413 | Payload Too Large | Archive exceeds size limit |
| 422 | Unprocessable Entity | Request body schema validation failure |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Dependency (DB, LLM) unavailable |

### Rate Limit Headers

When rate limiting applies, responses include:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1741089660
Retry-After: 42
```
