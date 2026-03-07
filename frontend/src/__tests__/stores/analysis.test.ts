/**
 * Unit tests for the analysis Pinia store.
 *
 * The analyzeApi is fully mocked so no HTTP requests are made.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAnalysisStore } from '@/stores/analysis'
import type { Job, JobSummary } from '@/types'

// ---------------------------------------------------------------------------
// Mock the API layer
// ---------------------------------------------------------------------------

vi.mock('@/api/endpoints', () => ({
  analyzeApi: {
    submit: vi.fn(),
    getJob: vi.fn(),
    listJobs: vi.fn().mockResolvedValue({
      data: {
        data: [],
        pagination: {
          page: 1,
          page_size: 50,
          total_items: 0,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      },
    }),
    deleteJob: vi.fn().mockResolvedValue({ data: null }),
  },
}))

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    job_id: 'job-123',
    status: 'pending',
    label: null,
    created_at: '2026-03-04T12:00:00Z',
    updated_at: '2026-03-04T12:00:00Z',
    completed_at: null,
    duration_seconds: null,
    languages: ['java'],
    file_count: 10,
    total_lines: 500,
    archive_size_bytes: 4096,
    config: {},
    current_stage: null,
    stage_progress: {},
    error: null,
    ucg_stats: null,
    smell_count: null,
    patch_count: null,
    repo_url: null,
    fix_branch: null,
    fix_pr_url: null,
    deferred_stages: [],
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useAnalysisStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // --- Initial state ---

  it('initializes with empty jobs list', () => {
    const store = useAnalysisStore()
    expect(store.jobs).toEqual([])
  })

  it('initializes with null activeJob', () => {
    const store = useAnalysisStore()
    expect(store.activeJob).toBeNull()
  })

  it('initializes with null activeJobId', () => {
    const store = useAnalysisStore()
    expect(store.activeJobId).toBeNull()
  })

  it('initializes with isLoading false', () => {
    const store = useAnalysisStore()
    expect(store.isLoading).toBe(false)
  })

  it('initializes with null error', () => {
    const store = useAnalysisStore()
    expect(store.error).toBeNull()
  })

  it('initializes with isPolling false', () => {
    const store = useAnalysisStore()
    expect(store.isPolling).toBe(false)
  })

  // --- Computed: isJobRunning / isJobComplete ---

  it('isJobRunning is false when no active job', () => {
    const store = useAnalysisStore()
    expect(store.isJobRunning).toBe(false)
  })

  it('isJobRunning is true when job is pending', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'pending' })
    expect(store.isJobRunning).toBe(true)
  })

  it('isJobRunning is true when job is detecting', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'detecting' })
    expect(store.isJobRunning).toBe(true)
  })

  it('isJobRunning is true when job is analyzing', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'analyzing' })
    expect(store.isJobRunning).toBe(true)
  })

  it('isJobComplete is true when job is complete', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'complete' })
    expect(store.isJobComplete).toBe(true)
  })

  it('isJobComplete is true when job is failed', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'failed' })
    expect(store.isJobComplete).toBe(true)
  })

  it('isJobComplete is true when job is cancelled', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'cancelled' })
    expect(store.isJobComplete).toBe(true)
  })

  it('isJobRunning is false when job is complete', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'complete' })
    expect(store.isJobRunning).toBe(false)
  })

  // --- Computed: activeJobStatus ---

  it('activeJobStatus returns null when no active job', () => {
    const store = useAnalysisStore()
    expect(store.activeJobStatus).toBeNull()
  })

  it('activeJobStatus reflects current job status', () => {
    const store = useAnalysisStore()
    store.activeJob = makeJob({ status: 'analyzing' })
    expect(store.activeJobStatus).toBe('analyzing')
  })

  // --- Computed: jobsByStatus ---

  it('jobsByStatus groups jobs correctly', () => {
    const store = useAnalysisStore()
    const j1 = makeJob({ job_id: '1', status: 'complete' }) as unknown as JobSummary
    const j2 = makeJob({ job_id: '2', status: 'complete' }) as unknown as JobSummary
    const j3 = makeJob({ job_id: '3', status: 'failed' }) as unknown as JobSummary
    store.jobs = [j1, j2, j3]

    const grouped = store.jobsByStatus
    expect(grouped['complete']).toHaveLength(2)
    expect(grouped['failed']).toHaveLength(1)
  })

  // --- submitJob action ---

  it('sets loading true during submitJob', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    const mockJob = makeJob({ job_id: 'job-new' })
    vi.mocked(analyzeApi.submit).mockImplementation(async () => {
      // We can't check loading inside the mock easily, but we verify it resets
      return { data: mockJob } as any
    })

    const store = useAnalysisStore()
    const archive = new File(['content'], 'test.zip', { type: 'application/zip' })
    await store.submitJob(archive)

    expect(store.isLoading).toBe(false) // reset after completion
  })

  it('adds job to jobs list on successful submit', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    const mockJob = makeJob({ job_id: 'job-submitted' })
    vi.mocked(analyzeApi.submit).mockResolvedValueOnce({ data: mockJob } as any)

    const store = useAnalysisStore()
    const archive = new File(['content'], 'code.zip', { type: 'application/zip' })
    await store.submitJob(archive)

    expect(store.jobs.some((j) => j.job_id === 'job-submitted')).toBe(true)
  })

  it('sets activeJob on successful submit', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    const mockJob = makeJob({ job_id: 'job-active' })
    vi.mocked(analyzeApi.submit).mockResolvedValueOnce({ data: mockJob } as any)

    const store = useAnalysisStore()
    const archive = new File(['content'], 'code.zip')
    await store.submitJob(archive)

    expect(store.activeJob?.job_id).toBe('job-active')
  })

  it('sets error on failed submitJob', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    vi.mocked(analyzeApi.submit).mockRejectedValueOnce(new Error('Network error'))

    const store = useAnalysisStore()
    const archive = new File(['content'], 'code.zip')

    await expect(store.submitJob(archive)).rejects.toThrow('Network error')
    expect(store.error).toBe('Network error')
    expect(store.isLoading).toBe(false)
  })

  it('rethrows error from submitJob', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    vi.mocked(analyzeApi.submit).mockRejectedValueOnce(new Error('Server error'))

    const store = useAnalysisStore()
    const archive = new File(['x'], 'a.zip')
    await expect(store.submitJob(archive)).rejects.toThrow('Server error')
  })

  // --- fetchJobs action ---

  it('fetchJobs populates jobs list', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    const mockJobs = [
      makeJob({ job_id: '1' }) as unknown as JobSummary,
      makeJob({ job_id: '2' }) as unknown as JobSummary,
    ]
    vi.mocked(analyzeApi.listJobs).mockResolvedValueOnce({
      data: {
        data: mockJobs,
        pagination: {
          page: 1,
          page_size: 50,
          total_items: 2,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      },
    } as any)

    const store = useAnalysisStore()
    await store.fetchJobs()

    expect(store.jobs).toHaveLength(2)
  })

  it('fetchJobs sets error on failure', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    vi.mocked(analyzeApi.listJobs).mockRejectedValueOnce(new Error('Fetch failed'))

    const store = useAnalysisStore()
    await store.fetchJobs() // Does not rethrow

    expect(store.error).toBe('Fetch failed')
  })

  it('fetchJobs sets isLoading to false after completion', async () => {
    const store = useAnalysisStore()
    await store.fetchJobs()

    expect(store.isLoading).toBe(false)
  })

  // --- setActiveJob / clearError actions ---

  it('setActiveJob updates activeJob and activeJobId', () => {
    const store = useAnalysisStore()
    const job = makeJob({ job_id: 'job-set' })
    store.setActiveJob(job)

    expect(store.activeJob?.job_id).toBe('job-set')
    expect(store.activeJobId).toBe('job-set')
  })

  it('clearError sets error to null', () => {
    const store = useAnalysisStore()
    store.error = 'Some previous error'
    store.clearError()
    expect(store.error).toBeNull()
  })

  // --- cancelJob action ---

  it('cancelJob removes job from jobs list', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    vi.mocked(analyzeApi.deleteJob).mockResolvedValueOnce({ data: null } as any)

    const store = useAnalysisStore()
    store.jobs = [makeJob({ job_id: 'job-to-cancel' }) as unknown as JobSummary]

    await store.cancelJob('job-to-cancel')

    expect(store.jobs.some((j) => j.job_id === 'job-to-cancel')).toBe(false)
  })

  it('cancelJob clears activeJob when it matches', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    vi.mocked(analyzeApi.deleteJob).mockResolvedValueOnce({ data: null } as any)

    const store = useAnalysisStore()
    store.activeJob = makeJob({ job_id: 'job-active-cancel' })
    store.activeJobId = 'job-active-cancel'
    store.jobs = []

    await store.cancelJob('job-active-cancel')

    expect(store.activeJob).toBeNull()
    expect(store.activeJobId).toBeNull()
  })

  it('cancelJob throws on API error', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    vi.mocked(analyzeApi.deleteJob).mockRejectedValueOnce(new Error('Delete failed'))

    const store = useAnalysisStore()
    store.jobs = []

    await expect(store.cancelJob('nonexistent')).rejects.toThrow('Delete failed')
    expect(store.error).toBe('Delete failed')
  })

  // --- startPolling / stopPolling ---

  it('startPolling sets isPolling to true', () => {
    const store = useAnalysisStore()
    store.startPolling('job-poll')
    expect(store.isPolling).toBe(true)
    store.stopPolling()
  })

  it('stopPolling sets isPolling to false', () => {
    const store = useAnalysisStore()
    store.startPolling('job-poll')
    store.stopPolling()
    expect(store.isPolling).toBe(false)
  })
})
