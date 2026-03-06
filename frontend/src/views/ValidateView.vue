<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold" style="color: var(--color-text)">Validation Results</h1>
        <p class="mt-0.5 text-sm" style="color: var(--color-text-secondary)">
          {{ results.length }} validation result{{ results.length !== 1 ? 's' : '' }}
          <span v-if="passCount + failCount > 0">
            —
            <span style="color: var(--color-success)">{{ passCount }} passed</span>,
            <span style="color: var(--color-error)">{{ failCount }} failed</span>
          </span>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <BaseButton variant="primary" size="sm" :loading="rerunLoading" @click="rerunValidation">
          Re-run Validation
        </BaseButton>
        <BaseButton variant="ghost" size="sm" :loading="isLoading" @click="load(true)">
          Refresh
        </BaseButton>
      </div>
    </div>

    <!-- Filter bar -->
    <div
      class="flex flex-wrap items-center gap-3 p-3 rounded-lg border"
      :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
    >
      <div class="flex gap-1.5">
        <button
          v-for="f in FILTERS"
          :key="f.key"
          @click="activeFilter = f.key"
          class="px-2.5 py-1 text-xs rounded-full border transition-all font-medium"
          :style="{
            background: activeFilter === f.key ? f.activeBg : 'var(--color-elevated)',
            borderColor: activeFilter === f.key ? f.borderColor : 'var(--color-border)',
            color: activeFilter === f.key ? f.textColor : 'var(--color-text-muted)',
          }"
        >
          {{ f.label }} ({{ f.count() }})
        </button>
      </div>
      <span class="text-xs ml-auto" style="color: var(--color-text-muted)">
        {{ filteredResults.length }} of {{ results.length }}
      </span>
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-3">
      <div v-for="i in 5" :key="i" class="h-14 rounded-lg animate-pulse" style="background: var(--color-card)" />
    </div>

    <!-- Empty -->
    <div v-else-if="filteredResults.length === 0" class="text-center py-16">
      <p class="text-sm" style="color: var(--color-text-muted)">
        {{ results.length === 0 ? 'No validation results yet. Run validation to see results here.' : 'No results match the current filter.' }}
      </p>
    </div>

    <!-- Results table -->
    <div
      v-else
      class="rounded-xl border overflow-hidden"
      :style="{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }"
    >
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr :style="{ borderBottom: '1px solid var(--color-border)' }">
              <th
                v-for="col in COLUMNS"
                :key="col.key"
                class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                style="color: var(--color-text-muted)"
              >
                {{ col.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="r in filteredResults" :key="r.result_id">
              <!-- Summary row -->
              <tr
                class="transition-colors cursor-pointer"
                :style="{ borderBottom: expanded === r.result_id ? 'none' : '1px solid var(--color-border)' }"
                @click="toggleExpand(r.result_id)"
              >
                <!-- Patch ID -->
                <td class="px-4 py-3">
                  <span class="text-xs font-mono" style="color: var(--color-text)">
                    {{ r.patch_id.slice(0, 8) }}…
                  </span>
                </td>
                <!-- Overall -->
                <td class="px-4 py-3">
                  <span
                    class="inline-flex items-center gap-1.5 text-xs font-semibold"
                    :style="{ color: r.passed ? 'var(--color-success)' : 'var(--color-error)' }"
                  >
                    <span>{{ r.passed ? '✓' : '✕' }}</span>
                    <span>{{ r.passed ? 'Passed' : 'Failed' }}</span>
                  </span>
                </td>
                <!-- Score -->
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <div class="w-16 h-1.5 rounded-full overflow-hidden" style="background: var(--color-elevated)">
                      <div
                        class="h-full rounded-full transition-all"
                        :style="{
                          width: `${Math.round(r.overall_score * 100)}%`,
                          background: scoreColor(r.overall_score),
                        }"
                      />
                    </div>
                    <span class="text-xs tabular-nums" style="color: var(--color-text-secondary)">
                      {{ Math.round(r.overall_score * 100) }}%
                    </span>
                  </div>
                </td>
                <!-- Checks summary -->
                <td class="px-4 py-3">
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <span
                      v-for="check in r.checks"
                      :key="check.check_name"
                      class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium"
                      :style="{
                        background: check.passed ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                        color: check.passed ? 'var(--color-success)' : 'var(--color-error)',
                      }"
                      :title="check.check_name"
                    >
                      {{ CHECK_ICONS[check.check_type] ?? '?' }}
                      {{ check.check_type }}
                    </span>
                  </div>
                </td>
                <!-- Date -->
                <td class="px-4 py-3 text-xs" style="color: var(--color-text-muted)">
                  {{ formatDate(r.created_at) }}
                </td>
                <!-- Expand toggle -->
                <td class="px-4 py-3 text-center text-xs" style="color: var(--color-text-muted)">
                  {{ expanded === r.result_id ? '▲' : '▼' }}
                </td>
              </tr>

              <!-- Expanded check details -->
              <tr
                v-if="expanded === r.result_id"
                :style="{ borderBottom: '1px solid var(--color-border)' }"
              >
                <td colspan="6" class="px-4 pb-4 pt-0">
                  <div
                    class="rounded-lg overflow-hidden border"
                    :style="{ background: 'var(--color-elevated)', borderColor: 'var(--color-border)' }"
                  >
                    <div
                      v-for="(check, idx) in r.checks"
                      :key="check.check_name"
                      class="px-4 py-3 text-xs"
                      :style="{
                        borderTop: idx > 0 ? '1px solid var(--color-border)' : 'none',
                      }"
                    >
                      <div class="flex items-center justify-between mb-1">
                        <div class="flex items-center gap-2">
                          <span
                            class="font-semibold"
                            :style="{ color: check.passed ? 'var(--color-success)' : 'var(--color-error)' }"
                          >
                            {{ check.passed ? '✓' : '✕' }}
                          </span>
                          <span class="font-medium" style="color: var(--color-text)">{{ check.check_name }}</span>
                          <span
                            class="px-1.5 py-0.5 rounded text-xs"
                            style="background: rgba(99,102,241,0.12); color: #a5b4fc"
                          >
                            {{ check.check_type }}
                          </span>
                        </div>
                        <span style="color: var(--color-text-muted)">{{ check.duration_ms }}ms</span>
                      </div>
                      <pre
                        v-if="check.output"
                        class="mt-2 text-xs font-mono whitespace-pre-wrap rounded p-2 overflow-auto"
                        style="max-height: 200px; background: #0a0c12; color: var(--color-text-secondary); border: 1px solid var(--color-border)"
                      >{{ check.output }}</pre>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import { validationApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { ValidationResultResponse } from '@/types'

const route = useRoute()
const uiStore = useUIStore()
const jobId = route.params.jobId as string

const results = ref<ValidationResultResponse[]>([])
const isLoading = ref(false)
const rerunLoading = ref(false)
const expanded = ref<string | null>(null)
const activeFilter = ref<'all' | 'passed' | 'failed'>('all')

const CHECK_ICONS: Record<string, string> = {
  syntax: '{ }',
  lint: '⚑',
  test: '▶',
  semantic: '◈',
  security: '⚿',
}

const COLUMNS = [
  { key: 'patch',   label: 'Patch' },
  { key: 'result',  label: 'Result' },
  { key: 'score',   label: 'Score' },
  { key: 'checks',  label: 'Checks' },
  { key: 'date',    label: 'Date' },
  { key: 'expand',  label: '' },
]

const passCount = computed(() => results.value.filter((r) => r.passed).length)
const failCount = computed(() => results.value.filter((r) => !r.passed).length)

const FILTERS = [
  {
    key: 'all' as const,
    label: 'All',
    activeBg: 'rgba(148,163,184,0.15)',
    borderColor: '#64748b',
    textColor: '#cbd5e1',
    count: () => results.value.length,
  },
  {
    key: 'passed' as const,
    label: 'Passed',
    activeBg: 'rgba(34,197,94,0.15)',
    borderColor: '#22c55e',
    textColor: '#86efac',
    count: () => passCount.value,
  },
  {
    key: 'failed' as const,
    label: 'Failed',
    activeBg: 'rgba(239,68,68,0.15)',
    borderColor: '#ef4444',
    textColor: '#fca5a5',
    count: () => failCount.value,
  },
]

const filteredResults = computed(() => {
  if (activeFilter.value === 'passed') return results.value.filter((r) => r.passed)
  if (activeFilter.value === 'failed') return results.value.filter((r) => !r.passed)
  return results.value
})

function toggleExpand(id: string): void {
  expanded.value = expanded.value === id ? null : id
}

function scoreColor(score: number): string {
  if (score >= 0.8) return 'var(--color-success)'
  if (score >= 0.5) return 'var(--color-warning)'
  return 'var(--color-error)'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function load(force = false): Promise<void> {
  if (!force && results.value.length > 0) return
  isLoading.value = true
  try {
    const { data } = await validationApi.listResults(jobId)
    results.value = data.data
  } catch (err) {
    uiStore.notify({
      type: 'error',
      title: 'Failed to load validation results',
      message: err instanceof Error ? err.message : String(err),
      duration: 6000,
    })
  } finally {
    isLoading.value = false
  }
}

async function rerunValidation(): Promise<void> {
  rerunLoading.value = true
  try {
    await validationApi.rerun(jobId)
    uiStore.notify({ type: 'success', title: 'Validation re-started', duration: 4000 })
    results.value = []
    await load(true)
  } catch (err) {
    uiStore.notify({
      type: 'error',
      title: 'Failed to re-run validation',
      message: err instanceof Error ? err.message : String(err),
      duration: 5000,
    })
  } finally {
    rerunLoading.value = false
  }
}

onMounted(() => void load())
</script>
