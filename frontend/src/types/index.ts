/**
 * ALM Frontend — Shared TypeScript type definitions.
 *
 * All types mirror the backend Pydantic schemas and API response shapes.
 * See docs/api-spec.md for the authoritative schema reference.
 */

// --- Enums ---

export type JobStatus =
  | 'pending'
  | 'detecting'
  | 'mapping'
  | 'analyzing'
  | 'planning'
  | 'transforming'
  | 'validating'
  | 'complete'
  | 'failed'
  | 'cancelled'

export type NodeType =
  | 'FILE'
  | 'MODULE'
  | 'CLASS'
  | 'FUNCTION'
  | 'METHOD'
  | 'FIELD'
  | 'VARIABLE'
  | 'PARAMETER'
  | 'IMPORT'
  | 'ANNOTATION'
  | 'BLOCK'
  | 'LITERAL'
  | 'CALL_SITE'
  | 'TYPE_REF'
  | 'COMMENT'

export type EdgeType =
  | 'CONTAINS'
  | 'CALLS'
  | 'EXTENDS'
  | 'IMPLEMENTS'
  | 'IMPORTS'
  | 'USES_TYPE'
  | 'HAS_PARAMETER'
  | 'HAS_FIELD'
  | 'HAS_ANNOTATION'
  | 'RETURNS'
  | 'THROWS'
  | 'OVERRIDES'
  | 'DEPENDS_ON'
  | 'INSTANTIATES'
  | 'READS'
  | 'WRITES'
  | 'DEFINED_IN'

export type SmellType =
  | 'god_class'
  | 'long_method'
  | 'feature_envy'
  | 'data_clumps'
  | 'shotgun_surgery'
  | 'divergent_change'
  | 'large_class'
  | 'primitive_obsession'
  | 'long_parameter_list'
  | 'dead_code'
  | 'circular_dependency'
  | 'spaghetti_code'
  | 'lava_flow'
  | 'tight_coupling'
  | 'missing_abstraction'
  | 'anemic_domain_model'
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
  file_count: number | null
  smell_count: number | null
  patch_count: number | null
  repo_url: string | null
}

export interface Job extends JobSummary {
  updated_at: string
  total_lines: number | null
  archive_size_bytes: number | null
  config: Partial<JobConfig>
  current_stage: string | null
  stage_progress: Record<string, 'pending' | 'running' | 'complete' | 'failed' | 'skipped'>
  error: string | null
  ucg_stats: { node_count: number; edge_count: number } | null
  repo_url: string | null
  repo_path?: string | null
  fix_branch: string | null
  fix_pr_url: string | null
  deferred_stages: string[]
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
  estimated_hours: number | null
  automated: boolean
  status: TaskStatus
  notes: string | null
}

export interface Plan {
  plan_id: string
  job_id: string
  status: string
  estimated_effort_hours: number | null
  risk_level: Severity | null
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
  prompt: string | null
  applied_at: string | null
  applied_by: string | null
  reverted_at: string | null
  reverted_reason: string | null
}

// --- Validation ---

export interface ValidationCheck {
  check_name: string
  check_type: 'syntax' | 'lint' | 'test' | 'semantic' | 'security'
  passed: boolean
  output: string
  duration_ms: number
}

export interface ValidationResultResponse {
  result_id: string
  patch_id: string
  passed: boolean
  overall_score: number
  checks: ValidationCheck[]
  created_at: string
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

// --- Cytoscape.js ---

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

// --- Job Logs ---

export interface JobLogEntry {
  seq: number
  stage: string
  message: string
  percent: number
  created_at: string
}

export interface JobLogsResponse {
  job_id: string
  total: number
  logs: JobLogEntry[]
}

// --- LLM Settings ---

export interface LLMSettings {
  provider: string
  model: string
  embed_model: string
  base_url: string | null
  available_models: string[]
}

// --- VCS ---

export type VCSProviderType = 'github' | 'gitlab' | 'bitbucket' | 'other'

export interface VCSProvider {
  id: string
  name: string
  provider: VCSProviderType
  base_url: string | null
  username: string | null
  token_hint: string
  created_at: string
  updated_at: string
}

export interface VCSPushResult {
  branch: string
  commits: number
  patches_applied: number
  pr_url: string | null
  message: string
}
