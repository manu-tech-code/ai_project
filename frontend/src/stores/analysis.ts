/**
 * Analysis Pinia store.
 *
 * Manages all job-related state: active job, job list, polling, and errors.
 * See docs/frontend-spec.md section 3.1 for the full store definition.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { analyzeApi } from '@/api/endpoints'
import type { Job, JobConfig, JobSummary, PaginationMeta } from '@/types'

export const useAnalysisStore = defineStore('analysis', () => {
  // --- State ---
  const jobs = ref<JobSummary[]>([])
  const activeJob = ref<Job | null>(null)
  const activeJobId = ref<string | null>(null)
  const isLoading = ref(false)
  const isPolling = ref(false)
  const error = ref<string | null>(null)
  const pagination = ref<PaginationMeta | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null
  const POLL_INTERVAL_MS = 3000

  // --- Getters ---
  const activeJobStatus = computed(() => activeJob.value?.status ?? null)

  const isJobComplete = computed(() =>
    ['complete', 'failed', 'cancelled'].includes(activeJob.value?.status ?? ''),
  )

  const isJobRunning = computed(() =>
    !isJobComplete.value && activeJob.value !== null,
  )

  const jobsByStatus = computed(() => {
    const result: Record<string, JobSummary[]> = {}
    for (const job of jobs.value) {
      if (!result[job.status]) result[job.status] = []
      result[job.status].push(job)
    }
    return result
  })

  // --- Actions ---
  async function submitJob(
    archive: File,
    label?: string,
    config?: Partial<JobConfig>,
  ): Promise<Job> {
    isLoading.value = true
    error.value = null
    try {
      const formData = new FormData()
      formData.append('archive', archive)
      if (label) formData.append('label', label)
      if (config) formData.append('config', JSON.stringify(config))
      const { data } = await analyzeApi.submit(formData)
      // Set active job immediately after submission
      activeJob.value = data
      activeJobId.value = data.job_id
      // Prepend to jobs list
      jobs.value.unshift(data as unknown as JobSummary)
      return data
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function fetchJob(jobId: string): Promise<Job> {
    const { data } = await analyzeApi.getJob(jobId)
    activeJob.value = data
    activeJobId.value = data.job_id
    // Update the matching entry in jobs list
    const idx = jobs.value.findIndex((j) => j.job_id === jobId)
    if (idx !== -1) {
      jobs.value[idx] = data as unknown as JobSummary
    }
    return data
  }

  async function fetchJobs(page = 1): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const { data } = await analyzeApi.listJobs({ page, page_size: 50 })
      jobs.value = data.data
      pagination.value = data.pagination
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
    } finally {
      isLoading.value = false
    }
  }

  function startPolling(jobId: string): void {
    stopPolling()
    isPolling.value = true
    activeJobId.value = jobId
    pollTimer = setInterval(async () => {
      try {
        await fetchJob(jobId)
        if (isJobComplete.value) stopPolling()
      } catch {
        // Polling errors are silent; will retry next interval
      }
    }, POLL_INTERVAL_MS)
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    isPolling.value = false
  }

  async function cancelJob(jobId: string): Promise<void> {
    try {
      await analyzeApi.deleteJob(jobId)
      if (activeJobId.value === jobId) {
        activeJob.value = null
        activeJobId.value = null
        stopPolling()
      }
      jobs.value = jobs.value.filter((j) => j.job_id !== jobId)
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      throw err
    }
  }

  function setActiveJob(job: Job): void {
    activeJob.value = job
    activeJobId.value = job.job_id
  }

  function clearError(): void {
    error.value = null
  }

  return {
    // State
    jobs,
    activeJob,
    activeJobId,
    isLoading,
    isPolling,
    error,
    pagination,
    // Getters
    activeJobStatus,
    isJobComplete,
    isJobRunning,
    jobsByStatus,
    // Actions
    submitJob,
    fetchJob,
    fetchJobs,
    startPolling,
    stopPolling,
    cancelJob,
    setActiveJob,
    clearError,
  }
})
