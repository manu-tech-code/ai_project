/**
 * ALM API endpoint functions — organized by resource.
 *
 * All functions are typed with request/response generics.
 * See docs/api-spec.md for the full endpoint reference.
 */

import client from './client'
import type {
  GraphMetrics,
  Job,
  JobConfig,
  JobSummary,
  PaginatedResponse,
  PatchDetail,
  PatchSummary,
  Plan,
  PlanTask,
  Report,
  SmellDetail,
  SmellSummary,
  UCGNode,
  UCGNodeDetail,
  ValidationResultResponse,
  VCSProvider,
  VCSPushResult,
} from '@/types'

// --- Analysis ---

export const analyzeApi = {
  submit: (formData: FormData) =>
    client.post<Job>('/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  getJob: (jobId: string) =>
    client.get<Job>(`/analyze/${jobId}`),

  listJobs: (params?: { page?: number; status?: string; page_size?: number }) =>
    client.get<PaginatedResponse<JobSummary>>('/analyze', { params }),

  fromUrl: (body: {
    repo_url: string
    branch?: string | null
    provider_id?: string | null
    token?: string | null
    label?: string | null
    config?: Record<string, unknown>
  }) => client.post<Job>('/analyze/from-url', body),

  stopJob: (jobId: string) =>
    client.post(`/analyze/${jobId}/stop`),

  deleteJob: (jobId: string) =>
    client.delete(`/analyze/${jobId}`),
}

// --- Settings ---

export const settingsApi = {
  getLLM: () =>
    client.get<{ provider: string; model: string; embed_model: string; base_url: string | null; available_models: string[] }>('/settings/llm'),

  patchLLM: (body: { model?: string; provider?: string }) =>
    client.patch<{ provider: string; model: string; embed_model: string; base_url: string | null; available_models: string[] }>('/settings/llm', body),
}

// --- Graph ---

export const graphApi = {
  getGraph: (
    jobId: string,
    params?: { page?: number; page_size?: number; include_edges?: boolean },
  ) => client.get<{ job_id: string; nodes: UCGNode[]; edges: any[]; pagination: any }>(
    `/graph/${jobId}`,
    { params },
  ),

  getNodes: (
    jobId: string,
    params?: { node_type?: string; language?: string; search?: string; page?: number },
  ) => client.get<PaginatedResponse<UCGNode>>(`/graph/${jobId}/nodes`, { params }),

  getNode: (jobId: string, nodeId: string, depth?: number) =>
    client.get<UCGNodeDetail>(`/graph/${jobId}/nodes/${nodeId}`, { params: { depth } }),

  getEdges: (jobId: string, params?: object) =>
    client.get(`/graph/${jobId}/edges`, { params }),

  getMetrics: (jobId: string) =>
    client.get<GraphMetrics>(`/graph/${jobId}/metrics`),

  getSubgraph: (
    jobId: string,
    body: { seed_node_ids: string[]; depth?: number; edge_types?: string[]; direction?: string },
  ) => client.post(`/graph/${jobId}/subgraph`, body),
}

// --- Smells ---

export const smellsApi = {
  listSmells: (
    jobId: string,
    params?: { severity?: string; smell_type?: string; dismissed?: boolean; page?: number },
  ) => client.get<PaginatedResponse<SmellDetail>>(`/smells/${jobId}`, { params }),

  getSmell: (jobId: string, smellId: string) =>
    client.get<SmellDetail>(`/smells/${jobId}/${smellId}`),

  dismissSmell: (jobId: string, smellId: string, body: { reason: string; dismissed_by?: string }) =>
    client.post(`/smells/${jobId}/${smellId}/dismiss`, body),

  getSummary: (jobId: string) =>
    client.get<SmellSummary>(`/smells/${jobId}/summary`),
}

// --- Plan ---

export const planApi = {
  getPlan: (jobId: string) =>
    client.get<Plan>(`/plan/${jobId}`),

  listTasks: (jobId: string, params?: { status?: string; automated?: boolean }) =>
    client.get<PaginatedResponse<PlanTask>>(`/plan/${jobId}/tasks`, { params }),

  getTask: (jobId: string, taskId: string) =>
    client.get<PlanTask>(`/plan/${jobId}/tasks/${taskId}`),

  updateTask: (jobId: string, taskId: string, body: Partial<PlanTask> & { notes?: string }) =>
    client.patch<PlanTask>(`/plan/${jobId}/tasks/${taskId}`, body),

  regenerate: (
    jobId: string,
    body?: { focus_smell_types?: string[]; exclude_task_ids?: string[]; max_tasks?: number },
  ) => client.post(`/plan/${jobId}/regenerate`, body),
}

// --- Patches ---

export const patchesApi = {
  listPatches: (
    jobId: string,
    params?: { status?: string; language?: string; task_id?: string; page?: number },
  ) => client.get<PaginatedResponse<PatchSummary>>(`/patches/${jobId}`, { params }),

  getPatch: (jobId: string, patchId: string) =>
    client.get<PatchDetail>(`/patches/${jobId}/${patchId}`),

  applyPatch: (jobId: string, patchId: string, body: { applied_by?: string; notes?: string }) =>
    client.post(`/patches/${jobId}/${patchId}/apply`, body),

  revertPatch: (jobId: string, patchId: string, body: { reason: string }) =>
    client.post(`/patches/${jobId}/${patchId}/revert`, body),

  exportPatches: (jobId: string) =>
    client.get(`/patches/${jobId}/export`, { responseType: 'blob' }),

  pushToRepo: (jobId: string, body: {
    branch_name?: string | null
    provider_id?: string | null
    token?: string | null
    create_pr?: boolean
    patch_ids?: string[] | null
  }) => client.post<VCSPushResult>(`/patches/${jobId}/push`, body),
}

// --- Validation ---

export const validationApi = {
  listResults: (jobId: string) =>
    client.get<PaginatedResponse<ValidationResultResponse>>(`/validate/${jobId}`),

  getResult: (jobId: string, resultId: string) =>
    client.get<ValidationResultResponse>(`/validate/${jobId}/${resultId}`),

  rerun: (jobId: string) =>
    client.post(`/validate/${jobId}/rerun`),
}

// --- VCS ---

export const vcsApi = {
  listProviders: () =>
    client.get<VCSProvider[]>('/vcs/providers'),

  createProvider: (body: {
    name: string
    provider: string
    base_url?: string | null
    token: string
    username?: string | null
  }) => client.post<VCSProvider>('/vcs/providers', body),

  updateProvider: (id: string, body: {
    name?: string
    base_url?: string | null
    token?: string
    username?: string | null
  }) => client.patch<VCSProvider>(`/vcs/providers/${id}`, body),

  deleteProvider: (id: string) =>
    client.delete(`/vcs/providers/${id}`),

  testConnection: (body: {
    provider: string
    base_url?: string | null
    token: string
    repo_url?: string | null
  }) => client.post<{ success: boolean; message: string }>('/vcs/test', body),
}

// --- Report ---

export const reportApi = {
  listReports: (params?: { page?: number }) =>
    client.get<PaginatedResponse<Report>>('/report', { params }),

  getReport: (jobId: string) =>
    client.get<Report>(`/report/${jobId}`),

  exportPDF: (jobId: string) =>
    client.get(`/report/${jobId}/pdf`, { responseType: 'blob' }),

  exportMarkdown: (jobId: string) =>
    client.get(`/report/${jobId}/markdown`, { responseType: 'text' }),
}
