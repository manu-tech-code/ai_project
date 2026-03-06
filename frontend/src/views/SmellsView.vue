<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold" style="color: var(--color-text)">Architectural Smells</h1>
        <p class="mt-0.5 text-sm" style="color: var(--color-text-secondary)">
          <template v-if="summary">
            {{ summary.active_smells }} active smells ·
            {{ summary.dismissed_smells }} dismissed ·
            ~{{ summary.estimated_tech_debt_hours }}h tech debt
          </template>
          <template v-else-if="!isLoadingSummary">
            {{ smells.length }} smells detected
          </template>
        </p>
      </div>
      <button
        @click="forceReload"
        class="flex items-center gap-2 text-xs px-3 py-2 rounded-md border transition-colors"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-muted)',
        }"
        :disabled="isLoading"
      >
        <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': isLoading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Refresh
      </button>
    </div>

    <!-- Summary severity bar -->
    <div v-if="summary" class="grid grid-cols-4 gap-3">
      <button
        v-for="sev in SEVERITIES"
        :key="sev.key"
        @click="toggleSeverityFilter(sev.key)"
        class="flex flex-col items-center justify-center p-3 rounded-xl border transition-all"
        :style="{
          background: activeSeverityFilters.includes(sev.key) ? sev.activeBg : 'var(--color-card)',
          borderColor: activeSeverityFilters.includes(sev.key) ? sev.borderColor : 'var(--color-border)',
        }"
      >
        <span class="text-2xl font-bold" :style="{ color: sev.color }">
          {{ summary.by_severity[sev.key] ?? 0 }}
        </span>
        <span class="text-xs mt-0.5 font-medium" :style="{ color: sev.color }">
          {{ sev.label }}
        </span>
      </button>
    </div>

    <!-- Filter bar -->
    <div
      class="flex flex-wrap items-center gap-3 p-3 rounded-lg border"
      :style="{
        background: 'var(--color-card)',
        borderColor: 'var(--color-border)',
      }"
    >
      <!-- Search -->
      <div class="relative flex-1 min-w-40">
        <svg
          class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
          style="color: var(--color-text-muted)"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search smells…"
          class="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border"
          :style="{
            background: 'var(--color-elevated)',
            borderColor: 'var(--color-border)',
            color: 'var(--color-text)',
          }"
        />
      </div>

      <!-- Type filter -->
      <select
        v-model="typeFilter"
        class="px-2 py-1.5 text-xs rounded-md border"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }"
      >
        <option value="">All types</option>
        <option v-for="t in availableTypes" :key="t" :value="t">{{ formatSmellType(t) }}</option>
      </select>

      <!-- Sort -->
      <select
        v-model="sortBy"
        class="px-2 py-1.5 text-xs rounded-md border"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }"
      >
        <option value="severity">Sort: Severity</option>
        <option value="confidence">Sort: Confidence</option>
        <option value="type">Sort: Type</option>
      </select>

      <!-- Show dismissed toggle -->
      <label class="flex items-center gap-2 text-xs cursor-pointer" style="color: var(--color-text-secondary)">
        <input v-model="showDismissed" type="checkbox" class="w-3 h-3 accent-indigo-500" />
        Show dismissed
      </label>

      <!-- Reset filters -->
      <button
        v-if="isFiltered"
        @click="resetFilters"
        class="text-xs px-2 py-1.5 rounded-md transition-colors"
        style="color: var(--color-primary)"
      >
        Reset filters
      </button>

      <span class="ml-auto text-xs" style="color: var(--color-text-muted)">
        {{ filteredSmells.length }} of {{ smells.length }}
      </span>
    </div>

    <!-- Loading skeleton -->
    <div v-if="isLoading" class="space-y-4">
      <div
        v-for="i in 4"
        :key="i"
        class="h-32 rounded-xl animate-pulse"
        style="background: var(--color-card)"
      />
    </div>

    <!-- Error -->
    <div v-else-if="loadError" class="text-center py-10">
      <p class="text-sm" style="color: var(--color-error)">{{ loadError }}</p>
      <button @click="forceReload" class="mt-2 text-xs underline" style="color: var(--color-primary)">Retry</button>
    </div>

    <!-- Empty -->
    <div v-else-if="filteredSmells.length === 0" class="text-center py-16">
      <svg
        class="w-12 h-12 mx-auto mb-3"
        style="color: var(--color-text-muted)"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1"
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p class="text-sm font-medium" style="color: var(--color-text)">
        {{ isFiltered ? 'No smells match your filters' : 'No smells detected' }}
      </p>
      <p class="text-xs mt-1" style="color: var(--color-text-muted)">
        {{ isFiltered ? 'Try broadening your filter criteria.' : 'This is a clean codebase!' }}
      </p>
      <button v-if="isFiltered" @click="resetFilters" class="mt-3 text-xs underline" style="color: var(--color-primary)">
        Clear filters
      </button>
    </div>

    <!-- Smell cards -->
    <div v-else class="space-y-4">
      <SmellCard
        v-for="smell in filteredSmells"
        :key="smell.smell_id"
        :smell="smell"
        @dismiss="onDismiss"
        @node-click="onNodeClick"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SmellCard from '@/components/smells/SmellCard.vue'
import { smellsApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { Severity, SmellDetail, SmellSummary, SmellType } from '@/types'

const route  = useRoute()
const router = useRouter()
const uiStore = useUIStore()
const jobId = route.params.jobId as string

/**
 * Module-level per-jobId cache so navigating away and back doesn't re-fetch
 * data that hasn't changed. Keyed by jobId. Cleared when a new job is submitted
 * (the analysis store calls bustCache on its invalidate()).
 */
interface SmellsCache { smells: SmellDetail[]; summary: SmellSummary }
const _smellsCache = new Map<string, SmellsCache>()

/** In-flight deduplication: if a fetch is already running for this jobId, don't start another. */
let _inFlightFetch: Promise<void> | null = null

const smells       = ref<SmellDetail[]>([])
const summary      = ref<SmellSummary | null>(null)
const isLoading    = ref(false)
const isLoadingSummary = ref(false)
const loadError    = ref<string | null>(null)

const searchQuery          = ref('')
const typeFilter           = ref<SmellType | ''>('')
const activeSeverityFilters = ref<Severity[]>([])
const sortBy               = ref<'severity' | 'confidence' | 'type'>('severity')
const showDismissed        = ref(false)

const SEVERITIES: { key: Severity; label: string; color: string; activeBg: string; borderColor: string }[] = [
  { key: 'critical', label: 'Critical', color: '#f87171', activeBg: 'rgba(239,68,68,0.1)',  borderColor: '#ef4444' },
  { key: 'high',     label: 'High',     color: '#fb923c', activeBg: 'rgba(249,115,22,0.1)', borderColor: '#f97316' },
  { key: 'medium',   label: 'Medium',   color: '#fde047', activeBg: 'rgba(234,179,8,0.1)',  borderColor: '#eab308' },
  { key: 'low',      label: 'Low',      color: '#86efac', activeBg: 'rgba(34,197,94,0.1)',  borderColor: '#22c55e' },
]

const SEV_ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 }

const availableTypes = computed(() => {
  const set = new Set(smells.value.map((s) => s.smell_type))
  return [...set].sort()
})

const isFiltered = computed(
  () =>
    searchQuery.value.length > 0 ||
    typeFilter.value !== '' ||
    activeSeverityFilters.value.length > 0 ||
    showDismissed.value,
)

const filteredSmells = computed(() => {
  let list = smells.value.filter((s) => {
    if (!showDismissed.value && s.dismissed) return false
    if (activeSeverityFilters.value.length > 0 && !activeSeverityFilters.value.includes(s.severity)) return false
    if (typeFilter.value && s.smell_type !== typeFilter.value) return false
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      const inType = s.smell_type.includes(q)
      const inDesc = s.description.toLowerCase().includes(q)
      const inNode = s.affected_nodes.some((n) => n.qualified_name.toLowerCase().includes(q))
      if (!inType && !inDesc && !inNode) return false
    }
    return true
  })

  list = [...list].sort((a, b) => {
    if (sortBy.value === 'severity') return SEV_ORDER[a.severity] - SEV_ORDER[b.severity]
    if (sortBy.value === 'confidence') return b.confidence - a.confidence
    return a.smell_type.localeCompare(b.smell_type)
  })

  return list
})

function toggleSeverityFilter(sev: Severity): void {
  const idx = activeSeverityFilters.value.indexOf(sev)
  if (idx === -1) activeSeverityFilters.value.push(sev)
  else activeSeverityFilters.value.splice(idx, 1)
}

function resetFilters(): void {
  searchQuery.value = ''
  typeFilter.value = ''
  activeSeverityFilters.value = []
  showDismissed.value = false
}

function formatSmellType(type: string): string {
  return type.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

async function reload(force = false): Promise<void> {
  // Serve from module-level cache if we already have data for this jobId and
  // the caller didn't explicitly force a refresh.
  if (!force && _smellsCache.has(jobId)) {
    const cached = _smellsCache.get(jobId)!
    smells.value = cached.smells
    summary.value = cached.summary
    return
  }

  // Deduplicate simultaneous fetches (e.g. from HMR double-mount in dev).
  if (_inFlightFetch) {
    await _inFlightFetch
    return
  }

  isLoading.value = true
  loadError.value = null

  _inFlightFetch = (async () => {
    try {
      const [smellsRes, summaryRes] = await Promise.all([
        smellsApi.listSmells(jobId, { page_size: 200 } as any),
        smellsApi.getSummary(jobId),
      ])
      smells.value = smellsRes.data.data
      summary.value = summaryRes.data
      _smellsCache.set(jobId, { smells: smells.value, summary: summary.value })
    } catch (err) {
      loadError.value = err instanceof Error ? err.message : String(err)
    } finally {
      isLoading.value = false
      _inFlightFetch = null
    }
  })()

  await _inFlightFetch
}

async function onDismiss(smellId: string, reason: string): Promise<void> {
  try {
    await smellsApi.dismissSmell(jobId, smellId, { reason })
    const idx = smells.value.findIndex((s) => s.smell_id === smellId)
    if (idx !== -1) {
      smells.value[idx] = {
        ...smells.value[idx],
        dismissed: true,
        dismissed_at: new Date().toISOString(),
        dismissed_reason: reason,
      }
    }
    uiStore.notify({ type: 'success', title: 'Smell dismissed', duration: 3000 })
  } catch (err) {
    uiStore.notify({
      type: 'error',
      title: 'Failed to dismiss smell',
      message: err instanceof Error ? err.message : String(err),
      duration: 5000,
    })
  }
}

function onNodeClick(nodeId: string): void {
  router.push({ name: 'graph', params: { jobId }, query: { node: nodeId } })
}

// The Refresh button in the template calls `reload` without arguments, which
// maps to force=false. We need the button to bust the cache, so we expose a
// separate forced reload for the template.
async function forceReload(): Promise<void> {
  _smellsCache.delete(jobId)
  await reload(true)
}

onMounted(() => reload())
</script>
