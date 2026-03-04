# AI Legacy Modernization Platform (ALM) — Frontend Specification

**Version:** 0.2.0
**Author:** Alex Chen, Tech Lead & Architect
**Date:** 2026-03-04
**Framework:** Vue 3.5.13 + TypeScript 5.7.3 + Vite 6.1.0

---

## Table of Contents

1. [Overview](#1-overview)
2. [Route Structure](#2-route-structure)
3. [Pinia Store Definitions](#3-pinia-store-definitions)
4. [Component Tree](#4-component-tree)
5. [API Integration Layer](#5-api-integration-layer)
6. [TypeScript Types](#6-typescript-types)
7. [Tailwind CSS Conventions](#7-tailwind-css-conventions)
8. [Testing Strategy](#8-testing-strategy)

---

## 1. Overview

The ALM frontend is a single-page application built with Vue 3 (Composition API) and TypeScript.
It provides:

- Job submission via drag-and-drop file upload
- Real-time job status polling with progress indicators
- Interactive UCG graph visualization using Cytoscape.js
- Tabular and card-based views for smells, plans, and patches
- Diff viewer for code patches
- Report export (PDF, Markdown)

### Key Technology Choices

| Technology | Version | Purpose |
|---|---|---|
| Vue 3 | 3.5.13 | SPA framework (Composition API, `<script setup>`) |
| TypeScript | 5.7.3 | Static typing for all components and API client |
| Vite | 6.1.0 | Build tool (dev server, HMR, production bundling) |
| Pinia | 2.3.0 | State management (replaces Vuex) |
| Vue Router | 4.5.0 | Client-side routing |
| Tailwind CSS | 4.0.0 | Utility-first CSS |
| @vueuse/core | 12.4.0 | Composables (useStorage, useFetch, useInterval, etc.) |
| Cytoscape.js | 3.30.2 | Graph visualization for UCG |
| Axios | 1.7.9 | HTTP client (wraps API calls) |
| Vitest | 3.0.5 | Unit tests |
| Playwright | 1.50.1 | End-to-end browser tests |

---

## 2. Route Structure

All routes are nested under the main `AppLayout` component which renders the sidebar and header.

```
/                          HomeView          -- Dashboard, recent jobs
/analyze                   AnalyzeView       -- Upload form, submit new job
/jobs/:jobId               JobDetailView     -- Job status overview (redirect hub)
  /jobs/:jobId/graph       GraphView         -- Cytoscape UCG visualization
  /jobs/:jobId/smells      SmellsView        -- Smell list with filters
  /jobs/:jobId/plan        PlanView          -- Refactor plan task list
  /jobs/:jobId/patches     PatchesView       -- Patch list with diff viewer
  /jobs/:jobId/report      ReportView        -- Full modernization report
/not-found                 NotFoundView      -- 404 page (catch-all)
```

### Router Configuration

```typescript
// src/router/index.ts
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'home', component: HomeView },
      { path: 'analyze', name: 'analyze', component: AnalyzeView },
      {
        path: 'jobs/:jobId',
        children: [
          { path: '', name: 'job-detail', redirect: to => ({ name: 'graph', params: to.params }) },
          { path: 'graph', name: 'graph', component: GraphView },
          { path: 'smells', name: 'smells', component: SmellsView },
          { path: 'plan', name: 'plan', component: PlanView },
          { path: 'patches', name: 'patches', component: PatchesView },
          { path: 'report', name: 'report', component: ReportView },
        ],
      },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView },
]
```

### Navigation Guards

- `beforeEach`: validate `jobId` param exists in the analysis store; redirect to home if not found.
- `afterEach`: scroll to top of main content area.

---

## 3. Pinia Store Definitions

### 3.1 Analysis Store (`stores/analysis.ts`)

Manages all job-related state including the active job, job list, and polling.

```typescript
interface AnalysisState {
  jobs: JobSummary[]
  activeJob: Job | null
  activeJobId: string | null
  isLoading: boolean
  isPolling: boolean
  pollInterval: number   // ms, default 3000
  error: string | null
  pagination: PaginationMeta | null
}

// Actions
interface AnalysisActions {
  submitJob(archive: File, label: string, config: Partial<JobConfig>): Promise<Job>
  fetchJob(jobId: string): Promise<Job>
  fetchJobs(page?: number, filters?: JobFilters): Promise<void>
  startPolling(jobId: string): void
  stopPolling(): void
  cancelJob(jobId: string): Promise<void>
  clearError(): void
}

// Getters
interface AnalysisGetters {
  activeJobStatus: ComputedRef<JobStatus | null>
  isJobComplete: ComputedRef<boolean>
  isJobRunning: ComputedRef<boolean>
  jobsByStatus: ComputedRef<Record<JobStatus, JobSummary[]>>
}
```

**Polling Logic:** When `startPolling(jobId)` is called, it sets up a `useInterval` composable
at `pollInterval` ms. Polling stops automatically when job status becomes `complete`, `failed`,
or `cancelled`. Status transitions trigger Pinia state updates, which reactively update all
subscribed components.

---

### 3.2 Graph Store (`stores/graph.ts`)

Manages UCG graph data and Cytoscape.js element state.

```typescript
interface GraphState {
  nodes: UCGNode[]
  edges: UCGEdge[]
  metrics: GraphMetrics | null
  selectedNodeId: string | null
  selectedNode: UCGNodeDetail | null
  filters: GraphFilters
  isLoading: boolean
  pagination: PaginationMeta | null
  error: string | null
}

interface GraphFilters {
  nodeTypes: NodeType[]      // active type filters
  languages: Language[]      // active language filters
  searchQuery: string
  showOrphans: boolean
}

// Actions
interface GraphActions {
  fetchGraph(jobId: string, page?: number): Promise<void>
  fetchNodeDetail(jobId: string, nodeId: string, depth?: number): Promise<void>
  fetchMetrics(jobId: string): Promise<void>
  fetchSubgraph(jobId: string, seedNodeIds: string[], depth: number): Promise<void>
  selectNode(nodeId: string | null): void
  setFilter(filter: Partial<GraphFilters>): void
  resetFilters(): void
}

// Getters
interface GraphGetters {
  cytoscapeElements: ComputedRef<CytoscapeElement[]>  // formatted for cytoscape
  filteredNodes: ComputedRef<UCGNode[]>
  nodeTypeStats: ComputedRef<Record<NodeType, number>>
  hasData: ComputedRef<boolean>
}
```

**Cytoscape Integration:** `cytoscapeElements` getter transforms `nodes` and `edges` into the
`{ data: {...}, group: 'nodes'|'edges' }` format expected by Cytoscape.js. Node color is mapped
by `node_type`, size by `line_end - line_start` (clamped to min/max range).

---

### 3.3 UI Store (`stores/ui.ts`)

Manages global UI state: sidebar, notifications, modals, and theme.

```typescript
interface UIState {
  sidebarOpen: boolean
  sidebarCollapsed: boolean
  activeModal: string | null
  modalProps: Record<string, unknown>
  notifications: Notification[]
  isDarkMode: boolean
}

interface Notification {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  duration: number       // ms, 0 = persistent
  timestamp: number
}

// Actions
interface UIActions {
  toggleSidebar(): void
  openModal(name: string, props?: Record<string, unknown>): void
  closeModal(): void
  notify(notification: Omit<Notification, 'id' | 'timestamp'>): void
  dismissNotification(id: string): void
  setDarkMode(value: boolean): void
}
```

`isDarkMode` is persisted to `localStorage` via `useStorage` from `@vueuse/core`.

---

## 4. Component Tree

```
App.vue
+-- AppLayout (components/layout/AppLayout.vue)
|   +-- AppSidebar (components/layout/AppSidebar.vue)
|   |   +-- [navigation links per route]
|   |   +-- [active job indicator]
|   +-- AppHeader (components/layout/AppHeader.vue)
|   |   +-- [breadcrumb]
|   |   +-- [job status chip]
|   |   +-- [notifications bell]
|   +-- <RouterView /> (renders active view)
|
+-- HomeView (views/HomeView.vue)
|   +-- [JobSummaryCard x N] (recent jobs list)
|   +-- [QuickStatsWidget] (total jobs, smells, patches)
|
+-- AnalyzeView (views/AnalyzeView.vue)
|   +-- [FileDropzone] (drag-and-drop archive upload)
|   +-- [JobConfigForm] (label, skip patterns, severity threshold)
|   +-- BaseButton ("Submit Analysis")
|   +-- [UploadProgress] (shows during upload)
|
+-- GraphView (views/GraphView.vue)
|   +-- GraphControls (components/graph/GraphControls.vue)
|   |   +-- [NodeTypeFilter checkboxes]
|   |   +-- [LanguageFilter checkboxes]
|   |   +-- [SearchInput]
|   |   +-- [LayoutSelector dropdown] (dagre, cose, breadthfirst)
|   |   +-- [FitButton, ResetButton]
|   +-- UCGGraph (components/graph/UCGGraph.vue)
|   |   +-- [Cytoscape.js canvas]
|   +-- [NodeDetailPanel] (slide-in panel on node click)
|       +-- [NodeProperties table]
|       +-- [EdgeList incoming/outgoing]
|
+-- SmellsView (views/SmellsView.vue)
|   +-- [SmellSummaryBar] (severity breakdown)
|   +-- [SeverityFilter buttons]
|   +-- [SmellTypeFilter select]
|   +-- SmellCard x N (components/smells/SmellCard.vue)
|       +-- SmellBadge (components/smells/SmellBadge.vue)
|       +-- [EvidenceTable]
|       +-- [AffectedNodesList]
|       +-- [DismissButton + DismissModal]
|
+-- PlanView (views/PlanView.vue)
|   +-- [PlanSummaryCard] (effort, risk, task counts)
|   +-- PlanTimeline (components/plan/PlanTimeline.vue)
|   |   +-- PlanTask x N (components/plan/PlanTask.vue)
|   |       +-- [PatternBadge]
|   |       +-- [DependencyChips]
|   |       +-- [ApproveButton, RejectButton]
|   +-- [RegeneratePlanButton]
|
+-- PatchesView (views/PatchesView.vue)
|   +-- [PatchStatusFilter]
|   +-- [PatchListTable]
|   |   +-- [LanguageBadge per row]
|   |   +-- [ValidationBadge per row]
|   |   +-- [ViewDiffButton per row]
|   +-- [DiffViewerModal]
|   |   +-- [UnifiedDiffDisplay] (syntax-highlighted diff)
|   |   +-- [ApplyButton, RevertButton]
|   +-- [ExportPatchesButton]
|
+-- ReportView (views/ReportView.vue)
|   +-- [ModernizationScoreWidget] (large circular gauge)
|   +-- [SummaryStatsGrid] (files, lines, smells, patches)
|   +-- [SmellBreakdownChart] (bar chart by type)
|   +-- [RecommendationsList]
|   +-- [SimilarJobsList]
|   +-- [ExportPDFButton, ExportMarkdownButton]
|
+-- UI Components (components/ui/)
    +-- BaseButton.vue
    +-- BaseCard.vue
    +-- BaseBadge.vue
    +-- BaseModal.vue
    +-- StatusBadge.vue
```

---

### 4.1 Core Component Details

#### UCGGraph.vue

The main graph visualization component wrapping Cytoscape.js.

**Props:**
```typescript
interface UCGGraphProps {
  jobId: string
  height?: string  // CSS height, default '600px'
}
```

**Emits:**
```typescript
interface UCGGraphEmits {
  nodeClick: (nodeId: string) => void
  edgeClick: (edgeId: string) => void
  backgroundClick: () => void
}
```

**Implementation Notes:**
- Initializes Cytoscape instance in `onMounted` with dagre layout (via `cytoscape-dagre`).
- Watches `graphStore.cytoscapeElements` and calls `cy.json({ elements })` on change.
- Node color palette (Tailwind-mapped):
  - `CLASS` / `INTERFACE` → blue-500
  - `METHOD` / `FUNCTION` → green-500
  - `FILE` / `MODULE` → purple-500
  - `FIELD` / `VARIABLE` → orange-400
  - `IMPORT` → gray-400
- Node size scales linearly with LOC (min 20px, max 80px).
- Cleanup: `cy.destroy()` in `onUnmounted`.

---

#### SmellCard.vue

Displays a single smell with severity badge, evidence, affected nodes, and dismiss action.

**Props:**
```typescript
interface SmellCardProps {
  smell: SmellDetail
  expanded?: boolean
}
```

**Emits:**
```typescript
interface SmellCardEmits {
  dismiss: (smellId: string, reason: string) => void
  nodeClick: (nodeId: string) => void  // navigates to graph view focused on node
}
```

---

#### PlanTask.vue

Renders a single plan task with pattern badge, dependency graph, and approval controls.

**Props:**
```typescript
interface PlanTaskProps {
  task: PlanTask
  allTasks: PlanTask[]   // needed to render dependency names
  readonly?: boolean
}
```

**Emits:**
```typescript
interface PlanTaskEmits {
  approve: (taskId: string) => void
  reject: (taskId: string) => void
}
```

---

#### BaseModal.vue

Accessible modal dialog using Vue Teleport (renders at `#modal-root`).

**Props:**
```typescript
interface BaseModalProps {
  open: boolean
  title: string
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'fullscreen'
}
```

**Emits:**
```typescript
interface BaseModalEmits {
  close: () => void
}
```

**Accessibility:** Sets `aria-modal="true"`, manages focus trap with `@vueuse/core useEventListener`,
closes on Escape key.

---

## 5. API Integration Layer

### 5.1 Axios Client (`src/api/client.ts`)

```typescript
import axios, { type AxiosInstance } from 'axios'

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// Request interceptor: inject API key from localStorage
client.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('alm_api_key')
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey
  }
  return config
})

// Response interceptor: normalize errors into AppError
client.interceptors.response.use(
  (response) => response,
  (error) => {
    // ... normalize to AppError, trigger ui store notification
    return Promise.reject(normalizeError(error))
  }
)

export default client
```

---

### 5.2 API Endpoints (`src/api/endpoints.ts`)

Organized by resource with typed request/response contracts:

```typescript
import client from './client'
import type { Job, JobSummary, UCGGraph, Smell, Plan, Patch, Report } from '../types'

// Analysis
export const analyzeApi = {
  submit: (formData: FormData) =>
    client.post<Job>('/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  getJob: (jobId: string) =>
    client.get<Job>(`/analyze/${jobId}`),

  listJobs: (params: { page?: number; status?: string }) =>
    client.get<PaginatedResponse<JobSummary>>('/analyze', { params }),

  deleteJob: (jobId: string) =>
    client.delete(`/analyze/${jobId}`),
}

// Graph
export const graphApi = {
  getGraph: (jobId: string, params: { page?: number; include_edges?: boolean }) =>
    client.get<UCGGraphResponse>(`/graph/${jobId}`, { params }),

  getNode: (jobId: string, nodeId: string, depth?: number) =>
    client.get<UCGNodeDetail>(`/graph/${jobId}/nodes/${nodeId}`, { params: { depth } }),

  getMetrics: (jobId: string) =>
    client.get<GraphMetrics>(`/graph/${jobId}/metrics`),

  getSubgraph: (jobId: string, body: SubgraphRequest) =>
    client.post<UCGGraphResponse>(`/graph/${jobId}/subgraph`, body),
}

// Smells
export const smellsApi = {
  listSmells: (jobId: string, params?: SmellFilters) =>
    client.get<PaginatedResponse<SmellDetail>>(`/smells/${jobId}`, { params }),

  getSmell: (jobId: string, smellId: string) =>
    client.get<SmellDetail>(`/smells/${jobId}/${smellId}`),

  dismissSmell: (jobId: string, smellId: string, body: DismissRequest) =>
    client.post(`/smells/${jobId}/${smellId}/dismiss`, body),

  getSummary: (jobId: string) =>
    client.get<SmellSummary>(`/smells/${jobId}/summary`),
}

// Plan
export const planApi = {
  getPlan: (jobId: string) =>
    client.get<Plan>(`/plan/${jobId}`),

  updateTask: (jobId: string, taskId: string, body: Partial<PlanTask>) =>
    client.patch<PlanTask>(`/plan/${jobId}/tasks/${taskId}`, body),

  regenerate: (jobId: string, body?: RegenerateRequest) =>
    client.post(`/plan/${jobId}/regenerate`, body),
}

// Patches
export const patchesApi = {
  listPatches: (jobId: string, params?: PatchFilters) =>
    client.get<PaginatedResponse<PatchSummary>>(`/patches/${jobId}`, { params }),

  getPatch: (jobId: string, patchId: string) =>
    client.get<PatchDetail>(`/patches/${jobId}/${patchId}`),

  applyPatch: (jobId: string, patchId: string, body: ApplyRequest) =>
    client.post(`/patches/${jobId}/${patchId}/apply`, body),

  revertPatch: (jobId: string, patchId: string, body: RevertRequest) =>
    client.post(`/patches/${jobId}/${patchId}/revert`, body),

  exportPatches: (jobId: string) =>
    client.get(`/patches/${jobId}/export`, { responseType: 'blob' }),
}

// Report
export const reportApi = {
  getReport: (jobId: string) =>
    client.get<Report>(`/report/${jobId}`),

  exportPDF: (jobId: string) =>
    client.get(`/report/${jobId}/pdf`, { responseType: 'blob' }),

  exportMarkdown: (jobId: string) =>
    client.get(`/report/${jobId}/markdown`, { responseType: 'text' }),
}
```

---

## 6. TypeScript Types

All shared types are defined in `src/types/index.ts`:

```typescript
// --- Enums ---

export type JobStatus =
  | 'pending' | 'detecting' | 'mapping' | 'analyzing'
  | 'planning' | 'transforming' | 'validating' | 'complete'
  | 'failed' | 'cancelled'

export type NodeType =
  | 'FILE' | 'MODULE' | 'CLASS' | 'FUNCTION' | 'METHOD'
  | 'FIELD' | 'VARIABLE' | 'PARAMETER' | 'IMPORT' | 'ANNOTATION'
  | 'BLOCK' | 'LITERAL' | 'CALL_SITE' | 'TYPE_REF' | 'COMMENT'

export type EdgeType =
  | 'CONTAINS' | 'CALLS' | 'EXTENDS' | 'IMPLEMENTS' | 'IMPORTS'
  | 'USES_TYPE' | 'HAS_PARAMETER' | 'HAS_FIELD' | 'HAS_ANNOTATION'
  | 'RETURNS' | 'THROWS' | 'OVERRIDES' | 'DEPENDS_ON'
  | 'INSTANTIATES' | 'READS' | 'WRITES' | 'DEFINED_IN'

export type SmellType =
  | 'god_class' | 'long_method' | 'feature_envy' | 'data_clumps'
  | 'shotgun_surgery' | 'divergent_change' | 'large_class'
  | 'primitive_obsession' | 'long_parameter_list' | 'dead_code'
  | 'circular_dependency' | 'spaghetti_code' | 'lava_flow'
  | 'tight_coupling' | 'missing_abstraction' | 'anemic_domain_model'
  | 'singleton_abuse'

export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type Language = 'java' | 'python' | 'php' | 'javascript' | 'typescript'
export type PatchType = 'modify' | 'create' | 'delete' | 'rename'
export type PatchStatus = 'pending' | 'applied' | 'reverted' | 'failed'
export type TaskStatus = 'pending' | 'approved' | 'rejected' | 'applied'

// --- Pagination ---

export interface PaginationMeta {
  page: number
  page_size: number
  total_items: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

export interface PaginatedResponse<T> {
  data: T[]
  pagination: PaginationMeta
}

// --- Job ---

export interface JobConfig {
  languages: Language[]
  skip_patterns: string[]
  smell_severity_threshold: Severity
  max_patches_per_task: number
  enable_extended_thinking: boolean
}

export interface JobSummary {
  job_id: string
  status: JobStatus
  label: string | null
  created_at: string
  completed_at: string | null
  duration_seconds: number | null
  languages: Language[]
  file_count: number
  smell_count: number | null
  patch_count: number | null
}

export interface Job extends JobSummary {
  updated_at: string
  total_lines: number
  archive_size_bytes: number
  config: Partial<JobConfig>
  current_stage: string | null
  stage_progress: Record<string, 'pending' | 'running' | 'complete' | 'failed'>
  error: string | null
  ucg_stats: { node_count: number; edge_count: number } | null
}

// --- UCG ---

export interface UCGNode {
  id: string
  node_type: NodeType
  qualified_name: string
  language: Language
  file_path: string | null
  line_start: number | null
  line_end: number | null
  col_start: number | null
  col_end: number | null
  properties: Record<string, unknown>
}

export interface UCGEdge {
  id: string
  edge_type: EdgeType
  source_node_id: string
  target_node_id: string
  weight: number
  properties: Record<string, unknown>
}

export interface UCGNodeDetail {
  node: UCGNode
  incoming_edges: Array<{
    edge_type: EdgeType
    source_node_id: string
    source_node_type: NodeType
    source_qualified_name: string
  }>
  outgoing_edges: Array<{
    edge_type: EdgeType
    target_node_id: string
    target_node_type: NodeType
    target_qualified_name: string
  }>
}

export interface GraphMetrics {
  job_id: string
  computed_at: string
  summary: {
    total_nodes: number
    total_edges: number
    average_coupling: number
    max_cyclomatic_complexity: number
    circular_dependency_count: number
    dead_code_node_count: number
  }
  top_coupled_nodes: Array<{
    node_id: string
    qualified_name: string
    afferent_coupling: number
    efferent_coupling: number
    instability: number
  }>
  top_complex_functions: Array<{
    node_id: string
    qualified_name: string
    cyclomatic_complexity: number
    lines_of_code: number
  }>
}

// --- Smells ---

export interface SmellDetail {
  smell_id: string
  job_id: string
  smell_type: SmellType
  severity: Severity
  description: string
  confidence: number
  dismissed: boolean
  dismissed_at: string | null
  dismissed_by: string | null
  dismissed_reason: string | null
  affected_nodes: Array<{
    node_id: string
    node_type: NodeType
    qualified_name: string
  }>
  evidence: Record<string, unknown>
  llm_rationale: string | null
  created_at: string
}

export interface SmellSummary {
  job_id: string
  total_smells: number
  dismissed_smells: number
  active_smells: number
  by_severity: Record<Severity, number>
  by_type: Partial<Record<SmellType, number>>
  affected_files: number
  estimated_tech_debt_hours: number
}

// --- Plan ---

export interface PlanTask {
  task_id: string
  title: string
  description: string
  smell_ids: string[]
  affected_files: string[]
  refactor_pattern: string
  dependencies: string[]
  estimated_hours: number
  automated: boolean
  status: TaskStatus
  notes: string | null
}

export interface Plan {
  plan_id: string
  job_id: string
  status: string
  estimated_effort_hours: number
  risk_level: Severity
  task_count: number
  automated_task_count: number
  priority_order: string[]
  created_at: string
  tasks: PlanTask[]
}

// --- Patches ---

export interface PatchSummary {
  patch_id: string
  task_id: string
  file_path: string
  patch_type: PatchType
  language: Language
  status: PatchStatus
  validation_passed: boolean | null
  tokens_used: number | null
  model_used: string | null
  created_at: string
}

export interface PatchDetail extends PatchSummary {
  diff: string
  original_content: string
  patched_content: string
  applied_at: string | null
  applied_by: string | null
  reverted_at: string | null
  reverted_reason: string | null
}

// --- Report ---

export interface Report {
  report_id: string
  job_id: string
  generated_at: string
  job_label: string | null
  executive_summary: {
    total_files_analyzed: number
    total_lines_analyzed: number
    languages: Language[]
    smells_found: number
    smells_critical: number
    patches_generated: number
    patches_validated: number
    patches_passed_validation: number
    estimated_tech_debt_hours: number
    modernization_score: number
  }
  smell_breakdown: {
    by_severity: Record<Severity, number>
    by_type: Partial<Record<SmellType, number>>
  }
  plan_summary: {
    total_tasks: number
    automated_tasks: number
    estimated_effort_hours: number
    risk_level: Severity
  }
  patch_summary: {
    total_patches: number
    by_language: Partial<Record<Language, number>>
    by_type: Partial<Record<PatchType, number>>
    validation_pass_rate: number
  }
  recommendations: Array<{
    priority: number
    title: string
    impact: string
    effort_hours: number
  }>
  similar_jobs: Array<{
    job_id: string
    label: string | null
    similarity_score: number
    key_finding: string
  }>
}

// --- Cytoscape ---

export interface CytoscapeNodeData {
  id: string
  label: string
  node_type: NodeType
  language: Language
  lines: number
  qualified_name: string
}

export interface CytoscapeEdgeData {
  id: string
  source: string
  target: string
  edge_type: EdgeType
  weight: number
}

export type CytoscapeElement =
  | { group: 'nodes'; data: CytoscapeNodeData }
  | { group: 'edges'; data: CytoscapeEdgeData }
```

---

## 7. Tailwind CSS Conventions

### Design Tokens (via Tailwind theme)

```typescript
// tailwind.config.ts
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        severity: {
          critical: '#dc2626',   // red-600
          high: '#ea580c',       // orange-600
          medium: '#ca8a04',     // yellow-600
          low: '#16a34a',        // green-600
        },
        node: {
          class: '#3b82f6',      // blue-500
          method: '#22c55e',     // green-500
          file: '#a855f7',       // purple-500
          field: '#f97316',      // orange-500
          import: '#9ca3af',     // gray-400
        },
      },
    },
  },
}
```

### Component CSS Conventions

- All component styles use Tailwind utility classes inside `<template>`.
- No scoped `<style>` blocks except for Cytoscape.js canvas sizing (where Tailwind is insufficient).
- Responsive breakpoints: `sm` (640px), `md` (768px), `lg` (1024px), `xl` (1280px).
- Default layout: `xl` sidebar always visible, `< xl` sidebar is a drawer overlay.

---

## 8. Testing Strategy

### Unit Tests (Vitest)

Location: `src/**/__tests__/*.spec.ts` or `src/**/*.spec.ts`

- **Stores**: Test each Pinia store action and getter with `createPinia()`.
  Mock API endpoints with `vi.mock('../api/endpoints')`.
- **Components**: Mount with `@vue/test-utils`. Test prop validation, emits, and DOM output.
  Do NOT test Cytoscape.js directly (mock `UCGGraph.vue` in parent tests).
- **API Layer**: Test `client.ts` interceptors with `axios-mock-adapter`.

### End-to-End Tests (Playwright)

Location: `tests/e2e/`

Key flows covered:
1. **Upload & Submit**: Upload a sample .zip archive, verify job appears in list with `pending` status.
2. **Status Polling**: Mock backend to cycle through statuses, verify UI updates.
3. **Graph View**: Verify Cytoscape canvas renders, node click opens detail panel.
4. **Smells View**: Verify smell cards render, dismiss a smell via modal.
5. **Patches View**: Open diff modal, mark patch as applied.
6. **Report Export**: Click PDF export, verify file download is triggered.

### Vitest Configuration

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      exclude: ['**/node_modules/**', '**/dist/**', '**/*.spec.ts'],
      thresholds: {
        lines: 75,
        functions: 75,
        branches: 70,
      },
    },
  },
})
```
