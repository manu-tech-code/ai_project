<template>
  <div class="p-6 max-w-6xl mx-auto space-y-8">
    <!-- Hero section -->
    <div class="text-center py-8">
      <div
        class="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
        style="background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.3)"
      >
        <svg class="w-8 h-8" style="color: var(--color-primary)" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
        </svg>
      </div>
      <h1 class="text-3xl font-bold tracking-tight" style="color: var(--color-text)">
        AI Legacy Modernization Platform
      </h1>
      <p class="mt-2 max-w-xl mx-auto text-base" style="color: var(--color-text-secondary)">
        Analyze legacy codebases, detect architectural smells, generate refactor plans, and produce
        AI-powered code patches — all in one automated pipeline.
      </p>
      <div class="mt-6 flex items-center justify-center gap-3">
        <RouterLink to="/analyze">
          <BaseButton variant="primary" size="lg">
            <template #icon>
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
            </template>
            New Analysis
          </BaseButton>
        </RouterLink>
      </div>
    </div>

    <!-- Stats row -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <StatCard
        label="Total Jobs"
        :value="store.jobs.length"
        icon="≡"
        color="indigo"
      />
      <StatCard
        label="Completed"
        :value="completedCount"
        icon="✓"
        color="green"
      />
      <StatCard
        label="In Progress"
        :value="runningCount"
        icon="↻"
        color="yellow"
      />
      <StatCard
        label="Failed"
        :value="failedCount"
        icon="✕"
        color="red"
      />
    </div>

    <!-- Recent jobs table -->
    <BaseCard title="Recent Jobs">
      <template #header-actions>
        <button
          @click="refresh"
          class="flex items-center gap-1.5 text-xs transition-colors"
          :style="{ color: 'var(--color-text-muted)' }"
          :disabled="store.isLoading"
        >
          <svg
            class="w-3.5 h-3.5"
            :class="{ 'animate-spin': store.isLoading }"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </template>

      <!-- Loading skeleton -->
      <div v-if="store.isLoading" class="space-y-3">
        <div
          v-for="i in 3"
          :key="i"
          class="h-14 rounded-lg animate-pulse"
          style="background: var(--color-elevated)"
        />
      </div>

      <!-- Error -->
      <div v-else-if="store.error" class="py-4">
        <p class="text-sm text-center" style="color: var(--color-error)">
          {{ store.error }}
          <button @click="refresh" class="ml-2 underline">Retry</button>
        </p>
      </div>

      <!-- Empty state -->
      <div v-else-if="!store.jobs.length" class="py-12 text-center">
        <svg
          class="w-12 h-12 mx-auto mb-3"
          style="color: var(--color-text-muted)"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1"
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <p class="text-sm font-medium" style="color: var(--color-text)">No analyses yet</p>
        <p class="text-xs mt-1" style="color: var(--color-text-muted)">
          Submit your first legacy codebase to get started.
        </p>
        <RouterLink to="/analyze" class="mt-3 inline-block">
          <BaseButton variant="primary" size="sm">Start Analysis</BaseButton>
        </RouterLink>
      </div>

      <!-- Jobs table -->
      <div v-else class="overflow-x-auto -mx-5 -mb-4">
        <table class="w-full text-sm">
          <thead>
            <tr :style="{ borderBottom: '1px solid var(--color-border)' }">
              <th
                v-for="col in COLUMNS"
                :key="col.key"
                class="px-5 py-2.5 text-left text-xs font-semibold uppercase tracking-wider"
                style="color: var(--color-text-muted)"
              >
                {{ col.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="job in store.jobs"
              :key="job.job_id"
              class="transition-colors cursor-pointer"
              :style="{ borderBottom: '1px solid var(--color-border)' }"
              @click="openJob(job)"
            >
              <!-- Status -->
              <td class="px-5 py-3">
                <StatusBadge :status="job.status" />
              </td>
              <!-- Label / ID -->
              <td class="px-5 py-3">
                <p class="text-xs font-medium" style="color: var(--color-text)">
                  {{ job.label || '(unlabeled)' }}
                </p>
                <p class="text-xs font-mono mt-0.5" style="color: var(--color-text-muted)">
                  {{ job.job_id.slice(0, 12) }}…
                </p>
              </td>
              <!-- Languages -->
              <td class="px-5 py-3">
                <div class="flex flex-wrap gap-1">
                  <BaseBadge
                    v-for="lang in (job.languages ?? []).slice(0, 3)"
                    :key="lang"
                    :label="lang"
                    color="blue"
                  />
                </div>
              </td>
              <!-- Files -->
              <td class="px-5 py-3 text-xs" style="color: var(--color-text-secondary)">
                {{ job.file_count ?? '—' }}
              </td>
              <!-- Smells -->
              <td class="px-5 py-3">
                <span
                  v-if="job.smell_count != null"
                  class="text-xs font-semibold"
                  :style="{ color: job.smell_count > 0 ? 'var(--color-error)' : 'var(--color-success)' }"
                >
                  {{ job.smell_count }}
                </span>
                <span v-else class="text-xs" style="color: var(--color-text-muted)">—</span>
              </td>
              <!-- Created -->
              <td class="px-5 py-3 text-xs" style="color: var(--color-text-muted)">
                {{ formatDate(job.created_at) }}
              </td>
              <!-- Actions -->
              <td class="px-5 py-3" @click.stop>
                <div class="flex items-center gap-2">
                  <BaseButton
                    v-if="isCompleted(job.status)"
                    variant="ghost"
                    size="xs"
                    @click="openJob(job)"
                  >
                    View
                  </BaseButton>
                  <BaseButton
                    v-if="canCancel(job.status)"
                    variant="ghost"
                    size="xs"
                    @click="cancelJob(job.job_id)"
                  >
                    Cancel
                  </BaseButton>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useAnalysisStore } from '@/stores/analysis'
import type { JobSummary, JobStatus } from '@/types'

const store = useAnalysisStore()
const router = useRouter()

const COLUMNS = [
  { key: 'status',    label: 'Status' },
  { key: 'label',     label: 'Job' },
  { key: 'languages', label: 'Languages' },
  { key: 'files',     label: 'Files' },
  { key: 'smells',    label: 'Smells' },
  { key: 'created',   label: 'Created' },
  { key: 'actions',   label: '' },
]

const completedCount = computed(() => store.jobs.filter((j) => j.status === 'complete').length)
const runningCount = computed(() =>
  store.jobs.filter((j) => !['complete', 'failed', 'cancelled'].includes(j.status)).length,
)
const failedCount = computed(() => store.jobs.filter((j) => j.status === 'failed').length)

async function refresh(): Promise<void> {
  await store.fetchJobs()
}

onMounted(refresh)

function openJob(job: JobSummary): void {
  store.activeJobId = job.job_id
  router.push({ name: 'graph', params: { jobId: job.job_id } })
}

function isCompleted(status: JobStatus): boolean {
  return ['complete', 'failed', 'cancelled'].includes(status)
}

function canCancel(status: JobStatus): boolean {
  return status === 'pending'
}

async function cancelJob(jobId: string): Promise<void> {
  await store.cancelJob(jobId)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── StatCard inline component ────────────────────────────────────────────────
type StatColor = 'indigo' | 'green' | 'yellow' | 'red'
const STAT_STYLES: Record<StatColor, string> = {
  indigo: 'rgba(99,102,241,0.15)',
  green:  'rgba(34,197,94,0.15)',
  yellow: 'rgba(245,158,11,0.15)',
  red:    'rgba(239,68,68,0.15)',
}
const STAT_TEXT: Record<StatColor, string> = {
  indigo: '#a5b4fc',
  green:  '#86efac',
  yellow: '#fde047',
  red:    '#fca5a5',
}

const StatCard = defineComponent({
  name: 'StatCard',
  props: {
    label: String,
    value: Number,
    icon: String,
    color: { type: String as () => StatColor, default: 'indigo' },
  },
  setup(props) {
    return () =>
      h(
        'div',
        {
          class: 'rounded-xl border px-5 py-4 flex items-center gap-4',
          style: `background: var(--color-card); border-color: var(--color-border)`,
        },
        [
          h(
            'div',
            {
              class: 'flex items-center justify-center w-10 h-10 rounded-lg text-lg flex-shrink-0',
              style: `background: ${STAT_STYLES[props.color!]}; color: ${STAT_TEXT[props.color!]}`,
            },
            props.icon,
          ),
          h('div', {}, [
            h('p', { class: 'text-2xl font-bold', style: `color: var(--color-text)` }, String(props.value ?? 0)),
            h('p', { class: 'text-xs', style: 'color: var(--color-text-muted)' }, props.label),
          ]),
        ],
      )
  },
})
</script>
