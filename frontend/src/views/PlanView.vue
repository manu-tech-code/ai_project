<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold" style="color: var(--color-text)">Refactor Plan</h1>
        <p class="mt-0.5 text-sm" style="color: var(--color-text-secondary)">
          AI-generated task sequence to modernize the codebase
        </p>
      </div>
      <div class="flex items-center gap-3">
        <BaseButton variant="secondary" size="sm" :loading="isRegenerating" @click="regenerate">
          Regenerate Plan
        </BaseButton>
        <BaseButton variant="ghost" size="sm" @click="exportJson">
          Export JSON
        </BaseButton>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="space-y-4">
      <div class="h-24 rounded-xl animate-pulse" style="background: var(--color-card)" />
      <div v-for="i in 3" :key="i" class="h-36 rounded-xl animate-pulse" style="background: var(--color-card)" />
    </div>

    <!-- Error -->
    <div v-else-if="loadError" class="text-center py-10">
      <p class="text-sm" style="color: var(--color-error)">{{ loadError }}</p>
      <button @click="loadPlan" class="mt-2 text-xs underline" style="color: var(--color-primary)">Retry</button>
    </div>

    <!-- Plan content -->
    <template v-else-if="plan">
      <!-- Summary card -->
      <div
        class="grid grid-cols-2 sm:grid-cols-4 gap-4 p-5 rounded-xl border"
        :style="{
          background: 'var(--color-card)',
          borderColor: 'var(--color-border)',
        }"
      >
        <div class="text-center">
          <p class="text-2xl font-bold" style="color: var(--color-text)">
            {{ plan.task_count }}
          </p>
          <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">Total Tasks</p>
        </div>
        <div class="text-center">
          <p class="text-2xl font-bold" style="color: var(--color-primary)">
            {{ plan.automated_task_count }}
          </p>
          <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">Automated</p>
        </div>
        <div class="text-center">
          <p class="text-2xl font-bold" style="color: var(--color-warning)">
            {{ plan.estimated_effort_hours ?? '?' }}h
          </p>
          <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">Effort</p>
        </div>
        <div class="text-center">
          <p
            class="text-2xl font-bold"
            :style="{ color: riskColor }"
          >
            {{ plan.risk_level?.toUpperCase() ?? '?' }}
          </p>
          <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">Risk Level</p>
        </div>
      </div>

      <!-- Filter controls -->
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex gap-1">
          <button
            v-for="status in TASK_STATUSES"
            :key="status.key"
            @click="toggleStatusFilter(status.key)"
            class="px-3 py-1.5 text-xs rounded-full border transition-all font-medium"
            :style="{
              background: activeStatusFilters.includes(status.key) ? status.activeBg : 'var(--color-elevated)',
              borderColor: activeStatusFilters.includes(status.key) ? status.borderColor : 'var(--color-border)',
              color: activeStatusFilters.includes(status.key) ? status.textColor : 'var(--color-text-muted)',
            }"
          >
            {{ status.label }} ({{ taskCountByStatus(status.key) }})
          </button>
        </div>

        <label class="flex items-center gap-2 text-xs cursor-pointer ml-2" style="color: var(--color-text-secondary)">
          <input v-model="showAutomatedOnly" type="checkbox" class="w-3 h-3 accent-indigo-500" />
          Automated only
        </label>

        <button
          v-if="pendingCount > 0"
          @click="approveAll"
          class="ml-auto text-xs px-3 py-1.5 rounded-md font-medium transition-colors"
          style="background: rgba(34,197,94,0.15); color: #86efac; border: 1px solid rgba(34,197,94,0.3)"
        >
          Approve All Pending ({{ pendingCount }})
        </button>
      </div>

      <!-- Empty filtered state -->
      <div v-if="filteredTasks.length === 0" class="text-center py-10">
        <p class="text-sm" style="color: var(--color-text-muted)">No tasks match the current filter.</p>
      </div>

      <!-- Plan timeline -->
      <PlanTimeline
        v-else
        :tasks="filteredTasks"
        :priority-order="plan.priority_order"
        @approve="onApprove"
        @reject="onReject"
      />
    </template>

    <!-- No plan yet -->
    <div v-else class="text-center py-16">
      <svg
        class="w-12 h-12 mx-auto mb-3"
        style="color: var(--color-text-muted)"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1"
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
      </svg>
      <p class="text-sm font-medium" style="color: var(--color-text)">No refactor plan yet</p>
      <p class="text-xs mt-1" style="color: var(--color-text-muted)">
        The plan is generated after smell detection completes.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import PlanTimeline from '@/components/plan/PlanTimeline.vue'
import { planApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { Plan, TaskStatus } from '@/types'

const route = useRoute()
const uiStore = useUIStore()
const jobId = route.params.jobId as string

/**
 * Module-level per-jobId cache — navigating between views and back skips the
 * network round-trip when we already have the plan for this job.
 */
const _planCache = new Map<string, Plan>()

/** In-flight deduplication guard. */
let _inFlightFetch: Promise<void> | null = null

const plan       = ref<Plan | null>(null)
const isLoading  = ref(false)
const loadError  = ref<string | null>(null)
const isRegenerating = ref(false)

const activeStatusFilters = ref<TaskStatus[]>([])
const showAutomatedOnly   = ref(false)

const TASK_STATUSES: { key: TaskStatus; label: string; activeBg: string; borderColor: string; textColor: string }[] = [
  { key: 'pending',  label: 'Pending',  activeBg: 'rgba(148,163,184,0.15)', borderColor: '#64748b', textColor: '#cbd5e1' },
  { key: 'approved', label: 'Approved', activeBg: 'rgba(34,197,94,0.15)',  borderColor: '#22c55e', textColor: '#86efac' },
  { key: 'rejected', label: 'Rejected', activeBg: 'rgba(239,68,68,0.15)',  borderColor: '#ef4444', textColor: '#fca5a5' },
  { key: 'applied',  label: 'Applied',  activeBg: 'rgba(99,102,241,0.15)', borderColor: '#6366f1', textColor: '#a5b4fc' },
]

const riskColor = computed(() => {
  const map: Record<string, string> = {
    low: 'var(--color-success)', medium: 'var(--color-warning)',
    high: 'var(--color-error)', critical: 'var(--color-error)',
  }
  return map[plan.value?.risk_level ?? ''] ?? 'var(--color-text-muted)'
})

const pendingCount = computed(() => plan.value?.tasks.filter((t) => t.status === 'pending').length ?? 0)

function taskCountByStatus(status: TaskStatus): number {
  return plan.value?.tasks.filter((t) => t.status === status).length ?? 0
}

function toggleStatusFilter(status: TaskStatus): void {
  const idx = activeStatusFilters.value.indexOf(status)
  if (idx === -1) activeStatusFilters.value.push(status)
  else activeStatusFilters.value.splice(idx, 1)
}

const filteredTasks = computed(() => {
  if (!plan.value) return []
  return plan.value.tasks.filter((t) => {
    if (activeStatusFilters.value.length > 0 && !activeStatusFilters.value.includes(t.status)) return false
    if (showAutomatedOnly.value && !t.automated) return false
    return true
  })
})

async function loadPlan(force = false): Promise<void> {
  // Serve from cache when we already have the plan for this job.
  if (!force && _planCache.has(jobId)) {
    plan.value = _planCache.get(jobId)!
    return
  }

  // Deduplicate simultaneous fetches.
  if (_inFlightFetch) {
    await _inFlightFetch
    return
  }

  isLoading.value = true
  loadError.value = null

  _inFlightFetch = (async () => {
    try {
      const { data } = await planApi.getPlan(jobId)
      plan.value = data
      _planCache.set(jobId, data)
    } catch (err) {
      loadError.value = err instanceof Error ? err.message : String(err)
    } finally {
      isLoading.value = false
      _inFlightFetch = null
    }
  })()

  await _inFlightFetch
}

async function onApprove(taskId: string): Promise<void> {
  try {
    await planApi.updateTask(jobId, taskId, { status: 'approved' })
    const task = plan.value?.tasks.find((t) => t.task_id === taskId)
    if (task) task.status = 'approved'
    uiStore.notify({ type: 'success', title: 'Task approved', duration: 3000 })
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to approve task', message: String(err), duration: 5000 })
  }
}

async function onReject(taskId: string): Promise<void> {
  try {
    await planApi.updateTask(jobId, taskId, { status: 'rejected' })
    const task = plan.value?.tasks.find((t) => t.task_id === taskId)
    if (task) task.status = 'rejected'
    uiStore.notify({ type: 'success', title: 'Task rejected', duration: 3000 })
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Failed to reject task', message: String(err), duration: 5000 })
  }
}

async function approveAll(): Promise<void> {
  const pending = plan.value?.tasks.filter((t) => t.status === 'pending') ?? []
  await Promise.allSettled(pending.map((t) => onApprove(t.task_id)))
}

async function regenerate(): Promise<void> {
  isRegenerating.value = true
  try {
    await planApi.regenerate(jobId)
    // Bust cache so the next loadPlan call fetches fresh data.
    _planCache.delete(jobId)
    uiStore.notify({ type: 'info', title: 'Plan regeneration queued', message: 'Refresh in a moment.', duration: 4000 })
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Regeneration failed', message: String(err), duration: 5000 })
  } finally {
    isRegenerating.value = false
  }
}

function exportJson(): void {
  if (!plan.value) return
  const blob = new Blob([JSON.stringify(plan.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `alm-plan-${jobId.slice(0, 8)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(loadPlan)
</script>
