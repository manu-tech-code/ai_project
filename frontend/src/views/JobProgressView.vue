<template>
  <div class="p-6 max-w-4xl mx-auto space-y-6">
    <!-- Back link -->
    <RouterLink
      to="/"
      class="inline-flex items-center gap-1.5 text-xs transition-colors hover:opacity-80"
      style="color: var(--color-text-muted)"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
      Dashboard
    </RouterLink>

    <!-- Loading spinner (initial fetch) -->
    <div v-if="loading" class="flex justify-center py-16">
      <svg class="w-8 h-8 animate-spin" style="color: var(--color-primary)" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
      </svg>
    </div>

    <template v-else-if="job">
      <!-- Job header -->
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="flex items-center gap-2.5 flex-wrap">
            <h1 class="text-xl font-bold" style="color: var(--color-text)">
              {{ job.label || '(unlabeled job)' }}
            </h1>
            <!-- Status badge -->
            <span
              class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold"
              :style="statusStyle(job.status)"
            >
              <span v-if="isRunning" class="relative flex h-1.5 w-1.5">
                <span
                  class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                  style="background: currentColor"
                />
                <span class="relative inline-flex rounded-full h-1.5 w-1.5" style="background: currentColor" />
              </span>
              {{ job.status }}
            </span>
          </div>
          <p class="text-xs font-mono mt-1" style="color: var(--color-text-muted)">{{ job.job_id }}</p>
        </div>

        <!-- Actions -->
        <div class="flex items-center gap-2 flex-shrink-0">
          <!-- Elapsed / duration display -->
          <span class="text-xs font-mono" style="color: var(--color-text-muted)">
            <template v-if="job.duration_seconds != null">{{ formatDuration(job.duration_seconds) }}</template>
            <template v-else-if="isRunning && elapsedSeconds > 0">{{ formatDuration(elapsedSeconds) }}</template>
          </span>
          <BaseButton v-if="isRunning" variant="danger" size="sm" @click="handleStop">Stop</BaseButton>
          <template v-if="isComplete">
            <RouterLink
              :to="{ name: 'graph', params: { jobId: job.job_id } }"
              @click="store.activeJobId = job.job_id"
            >
              <BaseButton variant="primary" size="sm">
                View Results &rarr;
              </BaseButton>
            </RouterLink>
            <RouterLink :to="{ name: 'patches', params: { jobId: job.job_id } }">
              <BaseButton variant="secondary" size="sm">
                Apply to Repo &rarr;
              </BaseButton>
            </RouterLink>
          </template>
        </div>
      </div>

      <!-- Pipeline stage stepper -->
      <BaseCard>
        <div class="flex items-start">
          <template v-for="(stage, i) in PIPELINE_STAGES" :key="stage.key">
            <!-- Stage node -->
            <div class="flex flex-col items-center" style="min-width: 72px">
              <div
                class="w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all duration-300"
                :class="{ 'animate-pulse': stageState(stage.key) === 'running' }"
                :style="stageNodeStyle(stage.key)"
              >
                <svg v-if="stageState(stage.key) === 'complete'" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
                </svg>
                <svg v-else-if="stageState(stage.key) === 'running'" class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                <svg v-else-if="stageState(stage.key) === 'failed'" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
                <div v-else class="w-2 h-2 rounded-full" style="background: currentColor" />
              </div>
              <p
                class="text-xs mt-1.5 text-center leading-tight"
                :style="stageLabelStyle(stage.key)"
              >{{ stage.label }}</p>
            </div>
            <!-- Connector -->
            <div
              v-if="i < PIPELINE_STAGES.length - 1"
              class="flex-1 h-0.5 mt-4 transition-all duration-300"
              :style="{ background: stageState(stage.key) === 'complete' ? 'var(--color-success)' : 'var(--color-border)' }"
            />
          </template>
        </div>

        <!-- Stats bar -->
        <div
          v-if="job.file_count || job.total_lines || job.current_stage"
          class="flex gap-6 mt-4 pt-4"
          style="border-top: 1px solid var(--color-border)"
        >
          <div v-if="job.file_count" class="text-xs" style="color: var(--color-text-muted)">
            <span class="font-medium" style="color: var(--color-text)">{{ job.file_count.toLocaleString() }}</span> files
          </div>
          <div v-if="job.total_lines" class="text-xs" style="color: var(--color-text-muted)">
            <span class="font-medium" style="color: var(--color-text)">{{ job.total_lines.toLocaleString() }}</span> lines
          </div>
          <div v-if="job.current_stage" class="text-xs" style="color: var(--color-text-muted)">
            Stage: <span class="font-medium capitalize" style="color: var(--color-primary)">{{ job.current_stage }}</span>
          </div>
          <div v-if="job.smell_count != null" class="text-xs" style="color: var(--color-text-muted)">
            <span class="font-medium" :style="{ color: job.smell_count > 0 ? 'var(--color-error)' : 'var(--color-success)' }">
              {{ job.smell_count }}
            </span> smells
          </div>
          <div v-if="job.patch_count != null" class="text-xs" style="color: var(--color-text-muted)">
            <span class="font-medium" style="color: #86efac">{{ job.patch_count }}</span> patches
          </div>
        </div>
      </BaseCard>

      <!-- Error block (failed state) -->
      <div
        v-if="isFailed && job.error"
        class="rounded-lg p-4"
        style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3)"
      >
        <p class="text-sm font-semibold mb-1" style="color: var(--color-error)">Analysis failed</p>
        <p class="text-xs font-mono" style="color: var(--color-text-secondary)">{{ job.error }}</p>
      </div>

      <!-- Full-height log viewer -->
      <BaseCard>
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider" style="color: var(--color-text-muted)">
            Agent Logs
          </span>
          <button
            v-if="displayLogs.length > 0"
            @click="copyLogs"
            class="text-xs px-2 py-0.5 rounded transition-colors"
            :style="{
              background: logCopied ? 'rgba(34,197,94,0.15)' : 'transparent',
              color: logCopied ? '#86efac' : 'var(--color-text-muted)',
              border: '1px solid',
              borderColor: logCopied ? 'rgba(34,197,94,0.4)' : 'var(--color-border)',
            }"
          >
            {{ logCopied ? '&#x2713; Copied' : 'Copy logs' }}
          </button>
        </div>
        <JobLogViewer :logs="displayLogs" :is-running="isRunning" max-height="calc(100vh - 460px)" />
      </BaseCard>
    </template>

    <!-- Not found -->
    <div v-else class="py-16 text-center">
      <p class="text-sm" style="color: var(--color-text-muted)">Job not found.</p>
      <RouterLink to="/" class="mt-3 inline-block">
        <BaseButton variant="ghost" size="sm">Back to Dashboard</BaseButton>
      </RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import JobLogViewer from '@/components/analysis/JobLogViewer.vue'
import { analyzeApi } from '@/api/endpoints'
import { useAnalysisStore } from '@/stores/analysis'
import { useUIStore } from '@/stores/ui'
import type { Job, JobLogEntry } from '@/types'

// Elapsed time ticker
const elapsedSeconds = ref(0)
let elapsedTimer: ReturnType<typeof setInterval> | null = null

function startElapsedTimer(startedAt: string): void {
  stopElapsedTimer()
  const start = new Date(startedAt).getTime()
  elapsedSeconds.value = Math.floor((Date.now() - start) / 1000)
  elapsedTimer = setInterval(() => {
    elapsedSeconds.value = Math.floor((Date.now() - start) / 1000)
  }, 1000)
}

function stopElapsedTimer(): void {
  if (elapsedTimer !== null) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

// Copy logs
const logCopied = ref(false)
function copyLogs(): void {
  const text = displayLogs.value
    .map((e) => `[${e.created_at}] [${e.stage}] ${e.message}`)
    .join('\n')
  navigator.clipboard.writeText(text).then(() => {
    logCopied.value = true
    setTimeout(() => { logCopied.value = false }, 2000)
  }).catch(() => {/* silent */})
}

const route = useRoute()
const store = useAnalysisStore()
const ui = useUIStore()

const jobId = route.params.jobId as string

const TERMINAL = ['complete', 'failed', 'cancelled']

const PIPELINE_STAGES = [
  { key: 'detecting',    label: 'Detect' },
  { key: 'mapping',      label: 'Map' },
  { key: 'analyzing',    label: 'Analyze' },
  { key: 'planning',     label: 'Plan' },
  { key: 'transforming', label: 'Transform' },
  { key: 'validating',   label: 'Validate' },
]

// Is this the store's currently tracked job?
const isActiveJob = computed(() => store.activeJobId === jobId)

// Local state for non-active (completed/foreign) jobs
const localJob = ref<Job | null>(null)
const localLogs = ref<JobLogEntry[]>([])
const loading = ref(true)

// Display targets: prefer store when it's tracking this running job
const job = computed<Job | null>(() => isActiveJob.value ? store.activeJob : localJob.value)
const displayLogs = computed<JobLogEntry[]>(() =>
  isActiveJob.value && !TERMINAL.includes(store.activeJob?.status ?? '') ? store.logs : localLogs.value,
)

const isRunning = computed(() => !!job.value && !TERMINAL.includes(job.value.status))
const isComplete = computed(() => job.value?.status === 'complete')
const isFailed = computed(() => job.value?.status === 'failed')

// ── Stage helpers ──────────────────────────────────────────────────────────────

function stageState(stageKey: string): 'complete' | 'running' | 'failed' | 'pending' {
  const j = job.value
  if (!j) return 'pending'
  if (j.stage_progress?.[stageKey]) {
    return j.stage_progress[stageKey] as 'complete' | 'running' | 'failed' | 'pending'
  }
  // Derive from current_stage / status position
  const keys = PIPELINE_STAGES.map((s) => s.key)
  const current = j.current_stage ?? j.status
  const currentIdx = keys.indexOf(current)
  const stageIdx = keys.indexOf(stageKey)
  if (currentIdx < 0) {
    if (j.status === 'complete') return 'complete'
    return 'pending'
  }
  if (stageIdx < currentIdx) return 'complete'
  if (stageIdx === currentIdx) return j.status === 'failed' ? 'failed' : 'running'
  return 'pending'
}

function stageNodeStyle(stageKey: string): string {
  const s = stageState(stageKey)
  if (s === 'complete') return 'border-color: var(--color-success); color: var(--color-success); background: rgba(34,197,94,0.1)'
  if (s === 'running')  return 'border-color: var(--color-primary); color: var(--color-primary); background: rgba(99,102,241,0.15)'
  if (s === 'failed')   return 'border-color: var(--color-error); color: var(--color-error); background: rgba(239,68,68,0.1)'
  return 'border-color: var(--color-border); color: var(--color-text-muted); background: var(--color-elevated)'
}

function stageLabelStyle(stageKey: string): string {
  const s = stageState(stageKey)
  if (s === 'complete') return 'color: var(--color-success)'
  if (s === 'running')  return 'color: var(--color-primary); font-weight: 600'
  if (s === 'failed')   return 'color: var(--color-error)'
  return 'color: var(--color-text-muted)'
}

function statusStyle(status: string): string {
  if (status === 'complete')   return 'background: rgba(34,197,94,0.15); color: #86efac'
  if (status === 'failed')     return 'background: rgba(239,68,68,0.15); color: #fca5a5'
  if (status === 'cancelled')  return 'background: rgba(107,114,128,0.15); color: #9ca3af'
  return 'background: rgba(99,102,241,0.15); color: #a5b4fc'
}

// ── Actions ────────────────────────────────────────────────────────────────────

async function handleStop(): Promise<void> {
  if (!job.value) return
  try {
    await store.stopJob(job.value.job_id)
    ui.notify({ type: 'warning', title: 'Job stopped', message: 'The analysis was cancelled.', duration: 4000 })
  } catch {
    ui.notify({ type: 'error', title: 'Stop failed', message: 'Could not stop the job. Try again.', duration: 5000 })
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

async function loadLogsForCompleted(): Promise<void> {
  try {
    const { data } = await analyzeApi.getLogs(jobId, 0, 1000)
    localLogs.value = data.logs
  } catch {
    // silent
  }
}

// ── Watch for job completion ────────────────────────────────────────────────────

watch(
  () => store.activeJob?.status,
  async (status) => {
    if (!isActiveJob.value || !TERMINAL.includes(status ?? '')) return
    // Job just finished — stop the elapsed timer and fetch all logs
    stopElapsedTimer()
    await loadLogsForCompleted()
    if (status === 'complete') {
      ui.notify({ type: 'success', title: 'Analysis complete', message: 'Pipeline finished successfully.', duration: 5000 })
    } else if (status === 'failed') {
      const err = store.activeJob?.error ?? 'An error occurred during analysis.'
      ui.notify({ type: 'error', title: 'Analysis failed', message: err, duration: 0 })
    }
  },
)

// ── Lifecycle ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  try {
    if (isActiveJob.value) {
      // Store is already tracking this job
      const alreadyDone = TERMINAL.includes(store.activeJob?.status ?? '')
      if (!alreadyDone && !store.isPolling) {
        // Page refreshed while job was running — restart polling
        store.startPolling(jobId)
        store.startLogPolling(jobId)
      }
      if (alreadyDone) {
        await loadLogsForCompleted()
      } else if (store.activeJob?.created_at) {
        startElapsedTimer(store.activeJob.created_at)
      }
    } else {
      // Non-active job (completed or foreign) — fetch independently
      const { data } = await analyzeApi.getJob(jobId)
      localJob.value = data
      if (TERMINAL.includes(data.status)) {
        await loadLogsForCompleted()
      } else {
        // Running job not tracked by store — adopt it
        store.setActiveJob(data)
        store.startPolling(jobId)
        store.clearLogs()
        store.startLogPolling(jobId)
        startElapsedTimer(data.created_at)
      }
    }
  } catch {
    // localJob stays null → shows "not found" state
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  stopElapsedTimer()
  // Active job polling continues for HomeView's stage stepper
})
</script>
