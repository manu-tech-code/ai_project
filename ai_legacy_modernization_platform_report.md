# AI Legacy Modernization Platform — Detailed Plan

**Author:** Emmanuel Larbi (project lead)
**Date:** 2026-02-27

---

## 1. Executive Summary

This document describes a full, production-ready plan to build an **AI-driven, agentic, language-agnostic Legacy Modernization Platform**. The platform ingests legacy repositories, produces a structured Universal Code Graph (UCG), runs multi-agent analysis and planning, generates safe incremental refactors, validates results, and produces a detailed modernization report and downloadable patch files.

The goal is to deliver a system that serves as: (a) a learning project to master agentic coding, (b) a production-grade tool suitable for enterprise adoption, (c) a foundation for a startup/SaaS, and (d) an open-source platform enabling community adapters.

---

## 2. Core Capabilities (What the platform does)

1. **Language detection and parsing** via pluggable Language Adapters
2. **Universal Code Graph (UCG)** construction — language-agnostic structural representation
3. **Multi-agent analysis** (Code Mapper, Smell Detector, Planner, Transformer, Validator, Learner)
4. **Incremental, safe refactors** with Git-backed patches and CI check integration
5. **Validation**: compilation, test runs, integration smoke tests, and runtime behavior checks (where possible)
6. **Memory & Learning**: vector DB to store prior refactors, patterns, and agent decisions
7. **Reporting**: exportable modernization reports (.md) with risk, effort estimate, and patch bundle
8. **UI & Visualization**: dependency graphs, smell heatmaps, roadmap timelines

---

## 3. System Architecture (High level)

- **Frontend**: Web UI (visualizations, upload, result viewer) — single-page app
- **API / Orchestrator**: Agent orchestration, REST endpoints, job scheduler
- **Language Adapter Layer**: Parser + normalizer per language → emits UCG fragments
- **UCG Store**: Central graph database or serialized store (Neo4j or a graph layer on Postgres)
- **Agent Workers**: Containerized agents (stateless) communicating via message bus (Kafka/RabbitMQ)
- **Memory & Vector DB**: pgvector / Weaviate for embeddings and retrieval
- **Persistence**: PostgreSQL for metadata, Git-backed code storage for patches
- **LLM Provider Layer**: pluggable adapters to any LLM API (OpenAI, Anthropic, Google, local LLMs)
- **CI Runner / Validation Sandbox**: ephemeral runners (Docker-in-Docker or Kubernetes jobs)

> Note: Agents operate on the UCG, not raw files. Language Adapters normalize code into nodes/edges and metadata.

---

## 4. Agents & Responsibilities (Detailed)

1. **Language Detector + Adapter Loader**
   - Detects repository language(s) and selects adapters
   - Generates AST and normalized UCG fragments

2. **Code Mapper Agent**
   - Builds project-wide UCG
   - Extracts modules, call graphs, data access points, config files

3. **Smell Detection Agent**
   - Runs rule-based and ML-assisted detectors for architectural smells
   - Produces a prioritized list of smells with severity and rationale

4. **Refactor Planner Agent**
   - Creates a stepwise migration plan with minimum-risk ordering
   - Produces tasks like "extract service X", "replace JDBC in module Y with ORM"
   - Estimates effort per task using heuristics (LOC, cyclomatic complexity)

5. **Transformation Agent**
   - Generates code patches for single-step transformations using language-specific templates
   - Ensures naming consistency and preserves behavior via tests where possible

6. **Validation Agent**
   - Runs compilation and test suites in sandbox
   - Runs smoke integration tests or contract checks
   - Uses runtime diffing where feasible (logs, response shape checks)

7. **Learner / Reflection Agent**
   - Stores results, successes, and failures to memory
   - Improves planner heuristics and prompt templates over time

---

## 5. Universal Code Graph (UCG) — Specification (short)

Fields per node (examples):
- `id`, `type` (module/class/function/service/controller/entity), `language`, `loc`, `complexity`, `public_api` (bool), `sinks` (DB/fs/network), `sources` (user input), `metadata` (file path, line numbers)

Edges: `calls`, `imports`, `inherits`, `data_flow`, `dependency`

Scoring: Coupling score, cohesion score, smell score

---

## 6. MVP Roadmap & Estimated Timeline (16 weeks / 4 months)

> Timeline assumes a focused team: 1 Senior Engineer (you), 1 Backend Engineer, 1 Frontend Engineer, part-time DevOps, and occasional external consultant for security. If you’re solo, add 1.5–2x time.

### Phase 0 — Preparation (Week 0)
- Kickoff, final requirements, repo templates, infra account setup, select LLM provider(s)
- Deliverables: Project plan, infra baseline, repo skeleton

### Phase 1 — Java-first MVP & UCG (Weeks 1–4)
- Implement language adapter for Java (JavaParser)
- Build Code Mapper Agent → UCG representation and basic visualization
- Basic Smell Detection (controller logic, god classes, JDBC detection)
- REST APIs: `/analyze`, `/status`
- Deliverables: Java adapter, UCG store, web UI basic graph

### Phase 2 — Planner & Simple Transformations (Weeks 5–8)
- Implement Refactor Planner agent (simple refactor templates: extract service, move logic)
- Implement Transformation Agent for small, safe patches
- Implement Git-backed patch generation and review flow
- Deliverables: Planner, patch generator, review UI

### Phase 3 — Validation & Sandbox (Weeks 9–11)
- Implement Validation Agent (build & run tests inside sandboxed runner)
- Integrate CI runner and patch apply/revert automation
- Deliverables: Validation pipeline, sample repo end-to-end test

### Phase 4 — Add PHP Adapter + Language-Agnosticization (Weeks 12–14)
- Implement PHP adapter (PhpParser), map to UCG
- Generalize planner to operate purely on UCG constructs
- Deliverables: PHP adapter, demonstrations on a Laravel legacy project

### Phase 5 — Memory, Learning, Polish & Open-source Prep (Weeks 15–16)
- Add vector DB memory, store transformation traces
- Add user docs, CLI, contribution guide
- Create `.md` export templates for detailed reports
- Deliverables: Vector DB integration, release v0.1, documented .md export

---

## 7. Best Language(s) and Tech Stack (Recommended)

**Core orchestration / agent runtime**: **Python (FastAPI)**
- Rationale:
  - Mature LLM SDKs and ML ecosystem (transformers, sentence-transformers)
  - Rapid development and easy prototyping of agent flows
  - Excellent libraries for AST parsing when combined with language adapters
  - Good for scripting/scheduling and glue code

**Language Adapters**:
- **Java**: JavaParser (Java). Adapter implemented in Java or via Python-Java bridge (py4j) or by calling a microservice written in Java/Kotlin.
- **PHP**: nikic/php-parser (wrap as microservice or use a PHP runtime)
- **Python**: built-in `ast` module
- **Node.js / TypeScript**: Babel / TypeScript parser (run adapter as Node microservice)

**Graph store / UCG**: PostgreSQL + Graph extension (or Neo4j for richer queries)

**Vector DB / Memory**: pgvector (hosted Postgres), Weaviate, or Pinecone

**Message Bus**: Kafka or RabbitMQ (RabbitMQ simpler for MVP)

**Frontend**: React or Vue.js (React recommended), D3 or Cytoscape for graph visualization

**Container orchestration**: Kubernetes (EKS/GKE/AKS) for production; Docker Compose for dev

**CI / Validation runners**: GitHub Actions or self-hosted Kubernetes runners

**LLM Providers**: Make the LLM layer pluggable. Start with a high-quality API (Anthropic/Google/OpenAI) and support locally-hosted models later.

**Why Python for core?**
- It reduces friction integrating many language-specific parsers via microservices
- Great for prompt templating, embeddings, and rapid iteration

**Production alternative:** Write mission-critical components (job runners, parsers) in **Kotlin/Java** or **Go** if you need extreme performance and type-safety — but prototype in Python.

---

## 8. Cost Estimate (Rough) — MVP (4 months) and Monthly Running Cost

> Costs are estimates in **USD**. Adjust for local salaries/timezones. These assume using managed services for vector DB and LLM APIs and mid-tier cloud hosting.

### Team & Development Costs (MVP: 4 months)
- Senior Engineer (lead) — 0.5 FTE × 4 months: $25,000 (contract estimate)
- Backend Engineer — 1 FTE × 4 months: $30,000
- Frontend Engineer — 0.5 FTE × 4 months: $15,000
- DevOps (part-time) — 0.25 FTE × 4 months: $5,000
- Security/Architecture consultant (ad-hoc): $3,000

**Subtotal (labor)**: **$78,000** (can be reduced dramatically if you self-develop)

### Infrastructure & Third-party (First 6 months)
- LLM API costs (development testing + small production): $1,000–$6,000 / month depending on usage. (Estimate: $9,000 for 6 months mid usage)
- Vector DB (managed) + Postgres + hosting: $200–$1,000 / month (estimate $3,000 for 6 months)
- CI runners & sandboxes (Kubernetes pods): $200–$1,000 / month (estimate $3,000 for 6 months)
- Monitoring, logging, domain, SSL: $500

**Subtotal (infra 6 months)**: **$15,500** (mid-range)

### One-time & Misc
- Tools and licenses (analysis tools, security scanners): $1,500
- Marketing / open-source launch expenses: $2,000

**Total (MVP, 4 months)**: **~$97k – $110k** (mid-range)

> **Lower-cost path**: If you (Emmanuel) build majority yourself and leverage open-source and small VPS, expect $10k–$25k mostly for LLM usage, minimal hosting, and some freelance help.

### Monthly Running Costs (after MVP, production one small team)
- LLM API: $1k–$10k/month (usage dependent)
- Hosting (K8s small cluster + DB): $300–$1,500/month
- Vector DB managed: $200–$1,000/month
- CI runners & validation sandboxes: $200–$1,000/month

**Estimated monthly**: **$2k–$12k** depending on scale and LLM usage.

---

## 9. Export: Automated Detailed Report (.md)

The platform will generate a detailed modernization report per project. Each `.md` will include:
- Project overview and metrics (LOC, dominant languages)
- UCG visualization snapshot (embedded image link)
- Top detected smells and severity
- Proposed refactor roadmap with ordered tasks
- Estimated effort per task and total
- Risk and rollback plan
- Generated patches summary (list of patch files)
- Validation results (compilation/test status)

**Export format:** Markdown with front-matter (YAML) for metadata. The system will produce a downloadable `.md` and also a ZIP with patch files.

Example header in generated `.md`:

```yaml
---
project: my-legacy-app
date: 2026-02-27
dominant_languages: [java, jsp]
loc: 124k
smell_count: 42
---
```

---

## 10. Risk, Mitigations, and Ethics

**Main risks:**
- Breaking runtime behavior at scale
- LLM hallucinations producing incorrect code
- Security vulnerabilities introduced during automated patches

**Mitigations:**
- Always produce Git patches, never auto-merge (initially)
- Comprehensive sandbox validation and test harness
- Human-in-the-loop review requirement for risky changes
- Use static analyzers & security scanners as post-checks

**Ethics & IP:**
- Respect user repo ownership — do not retain private code beyond necessary processing unless permitted
- Provide clear data retention and deletion policies

---

## 11. Next Steps (Immediate)

1. Build repo skeleton and infra baseline
2. Implement Java adapter and UCG proof-of-concept
3. Create a small demo repo (a real legacy JSP/Servlet app) to run end-to-end
4. Iterate planner and transformation templates

---

## 12. Appendix

- **Suggested open-source libraries**
  - Java: JavaParser, Spoon
  - PHP: nikic/php-parser
  - Python: ast, astor
  - JS/TS: Babel, TypeScript compiler API
  - Graph DB: Neo4j, PGGraph
  - Vector embeddings: sentence-transformers + pgvector

- **Example CLI commands**
  - `./cli analyze --repo ./my-legacy-app`
  - `./cli plan --repo ./my-legacy-app --out plan.json`
  - `./cli refactor --task extract-service-Order --apply --branch refactor/order-service`


---

_End of document._

