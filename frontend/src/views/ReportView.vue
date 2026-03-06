<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold" style="color: var(--color-text)">Modernization Report</h1>
        <p v-if="report" class="mt-0.5 text-xs" style="color: var(--color-text-muted)">
          Generated {{ formatDate(report.generated_at) }}
          <template v-if="report.job_label"> · {{ report.job_label }}</template>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <BaseButton variant="secondary" size="sm" :loading="isExportingMd" @click="exportMarkdown">
          Export Markdown
        </BaseButton>
        <BaseButton variant="primary" size="sm" :loading="isExportingPdf" @click="exportPdf">
          Export PDF
        </BaseButton>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="space-y-4">
      <div class="h-48 rounded-xl animate-pulse" style="background: var(--color-card)" />
      <div class="grid grid-cols-4 gap-4">
        <div v-for="i in 4" :key="i" class="h-24 rounded-xl animate-pulse" style="background: var(--color-card)" />
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="loadError" class="text-center py-10">
      <p class="text-sm" style="color: var(--color-error)">{{ loadError }}</p>
      <button @click="loadReport" class="mt-2 text-xs underline" style="color: var(--color-primary)">Retry</button>
    </div>

    <template v-else-if="report">
      <!-- Modernization score hero -->
      <div
        class="flex flex-col sm:flex-row items-center gap-6 p-6 rounded-2xl border"
        :style="{
          background: 'var(--color-card)',
          borderColor: scoreGradientBorder,
        }"
      >
        <!-- Circular score display -->
        <div class="flex-shrink-0 relative">
          <svg width="120" height="120" viewBox="0 0 120 120" class="-rotate-90">
            <!-- Background circle -->
            <circle cx="60" cy="60" r="50" fill="none" stroke="#1a1d27" stroke-width="10" />
            <!-- Score arc -->
            <circle
              cx="60" cy="60" r="50"
              fill="none"
              :stroke="scoreColor"
              stroke-width="10"
              stroke-linecap="round"
              :stroke-dasharray="`${(report.executive_summary.modernization_score / 100) * 314} 314`"
              style="transition: stroke-dasharray 0.8s ease"
            />
          </svg>
          <div class="absolute inset-0 flex flex-col items-center justify-center">
            <span class="text-3xl font-bold" :style="{ color: scoreColor }">
              {{ report.executive_summary.modernization_score }}
            </span>
            <span class="text-xs" style="color: var(--color-text-muted)">/ 100</span>
          </div>
        </div>

        <!-- Score details -->
        <div class="flex-1">
          <h2 class="text-lg font-bold" style="color: var(--color-text)">
            {{ scoreLabel }}
          </h2>
          <p class="mt-1 text-sm" style="color: var(--color-text-secondary)">
            {{ scoreDescription }}
          </p>
          <div class="mt-3 flex flex-wrap gap-3 text-xs" style="color: var(--color-text-muted)">
            <span>
              <span class="font-semibold" style="color: var(--color-text)">
                {{ report.executive_summary.total_files_analyzed.toLocaleString() }}
              </span> files
            </span>
            <span>
              <span class="font-semibold" style="color: var(--color-text)">
                {{ report.executive_summary.total_lines_analyzed.toLocaleString() }}
              </span> lines
            </span>
            <span>
              Languages:
              <span v-for="lang in report.executive_summary.languages" :key="lang" class="ml-1">
                <BaseBadge :label="lang" color="blue" />
              </span>
            </span>
          </div>
        </div>
      </div>

      <!-- Key metrics grid -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricCard
          label="Smells Found"
          :value="report.executive_summary.smells_found"
          :sub="`${report.executive_summary.smells_critical} critical`"
          icon="⚠"
          color="red"
        />
        <MetricCard
          label="Patches Generated"
          :value="report.executive_summary.patches_generated"
          :sub="`${report.executive_summary.patches_passed_validation} validated`"
          icon="⊞"
          color="indigo"
        />
        <MetricCard
          label="Tech Debt"
          :value="`${report.executive_summary.estimated_tech_debt_hours}h`"
          sub="estimated hours"
          icon="⏱"
          color="orange"
        />
        <MetricCard
          label="Validation Rate"
          :value="`${Math.round(report.patch_summary.validation_pass_rate * 100)}%`"
          sub="patches passed"
          icon="✓"
          color="green"
        />
      </div>

      <!-- Smell breakdown -->
      <BaseCard title="Smell Breakdown">
        <div class="grid sm:grid-cols-2 gap-6">
          <!-- By severity -->
          <div>
            <p class="text-xs font-semibold mb-3" style="color: var(--color-text-muted)">By Severity</p>
            <div class="space-y-2">
              <div
                v-for="[sev, count] in Object.entries(report.smell_breakdown.by_severity)"
                :key="sev"
                class="flex items-center gap-3"
              >
                <span class="text-xs w-16 capitalize" style="color: var(--color-text-secondary)">{{ sev }}</span>
                <div class="flex-1 h-2 rounded-full overflow-hidden" style="background: var(--color-elevated)">
                  <div
                    class="h-full rounded-full transition-all"
                    :style="{
                      width: `${(count / Math.max(...Object.values(report.smell_breakdown.by_severity))) * 100}%`,
                      background: sevColor(sev),
                    }"
                  />
                </div>
                <span class="text-xs font-semibold w-6 text-right" :style="{ color: sevColor(sev) }">{{ count }}</span>
              </div>
            </div>
          </div>

          <!-- By type -->
          <div>
            <p class="text-xs font-semibold mb-3" style="color: var(--color-text-muted)">Top Smell Types</p>
            <div class="space-y-2">
              <div
                v-for="[type, count] in topSmellTypes"
                :key="type"
                class="flex items-center justify-between text-xs"
              >
                <span style="color: var(--color-text-secondary)" class="capitalize">
                  {{ type.replace(/_/g, ' ') }}
                </span>
                <span class="font-semibold" style="color: var(--color-text)">{{ count }}</span>
              </div>
            </div>
          </div>
        </div>
      </BaseCard>

      <!-- Plan summary -->
      <BaseCard title="Refactor Plan Summary">
        <div class="grid sm:grid-cols-3 gap-4">
          <div class="text-center py-3">
            <p class="text-2xl font-bold" style="color: var(--color-text)">{{ report.plan_summary.total_tasks }}</p>
            <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">Total Tasks</p>
          </div>
          <div class="text-center py-3">
            <p class="text-2xl font-bold" style="color: var(--color-primary)">{{ report.plan_summary.automated_tasks }}</p>
            <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">Automated</p>
          </div>
          <div class="text-center py-3">
            <p class="text-2xl font-bold" :style="{ color: riskColor(report.plan_summary.risk_level) }">
              {{ report.plan_summary.risk_level?.toUpperCase() }}
            </p>
            <p class="text-xs mt-0.5" style="color: var(--color-text-muted)">Risk Level</p>
          </div>
        </div>
      </BaseCard>

      <!-- Recommendations -->
      <BaseCard v-if="report.recommendations.length" title="Recommendations">
        <div class="space-y-3">
          <div
            v-for="rec in report.recommendations"
            :key="rec.priority"
            class="flex items-start gap-4 p-3 rounded-lg"
            :style="{ background: 'var(--color-elevated)' }"
          >
            <div
              class="flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold flex-shrink-0"
              style="background: rgba(99,102,241,0.2); color: #a5b4fc"
            >
              {{ rec.priority }}
            </div>
            <div class="flex-1">
              <p class="text-sm font-medium" style="color: var(--color-text)">{{ rec.title }}</p>
              <p class="text-xs mt-0.5" style="color: var(--color-text-secondary)">{{ rec.impact }}</p>
            </div>
            <span class="text-xs flex-shrink-0" style="color: var(--color-text-muted)">
              ~{{ rec.effort_hours }}h
            </span>
          </div>
        </div>
      </BaseCard>

      <!-- Similar jobs -->
      <BaseCard v-if="report.similar_jobs.length" title="Similar Past Jobs">
        <div class="space-y-2">
          <div
            v-for="job in report.similar_jobs"
            :key="job.job_id"
            class="flex items-center gap-4 p-3 rounded-lg"
            :style="{ background: 'var(--color-elevated)' }"
          >
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium truncate" style="color: var(--color-text)">
                {{ job.label ?? job.job_id.slice(0, 12) }}
              </p>
              <p class="text-xs mt-0.5" style="color: var(--color-text-secondary)">{{ job.key_finding }}</p>
            </div>
            <div class="flex-shrink-0 text-right">
              <p class="text-sm font-bold" style="color: var(--color-primary)">
                {{ Math.round(job.similarity_score * 100) }}%
              </p>
              <p class="text-xs" style="color: var(--color-text-muted)">similar</p>
            </div>
          </div>
        </div>
      </BaseCard>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import { reportApi } from '@/api/endpoints'
import { useUIStore } from '@/stores/ui'
import type { Report, Severity } from '@/types'

// Module-level per-jobId cache — survives route navigation without re-fetching.
const _reportCache = new Map<string, Report>()
const _reportInFlight = new Map<string, Promise<void>>()

const route  = useRoute()
const uiStore = useUIStore()
const jobId = route.params.jobId as string

const report      = ref<Report | null>(null)
const isLoading   = ref(false)
const loadError   = ref<string | null>(null)
const isExportingPdf = ref(false)
const isExportingMd  = ref(false)

// ── Score helpers ─────────────────────────────────────────────────────────────
const scoreColor = computed(() => {
  const s = report.value?.executive_summary.modernization_score ?? 0
  if (s >= 80) return '#22c55e'
  if (s >= 60) return '#f59e0b'
  if (s >= 40) return '#f97316'
  return '#ef4444'
})

const scoreGradientBorder = computed(() => {
  const s = report.value?.executive_summary.modernization_score ?? 0
  if (s >= 80) return 'rgba(34,197,94,0.3)'
  if (s >= 60) return 'rgba(245,158,11,0.3)'
  return 'rgba(239,68,68,0.3)'
})

const scoreLabel = computed(() => {
  const s = report.value?.executive_summary.modernization_score ?? 0
  if (s >= 80) return 'Excellent Modernization Score'
  if (s >= 60) return 'Good Modernization Score'
  if (s >= 40) return 'Moderate Modernization Score'
  return 'Low Modernization Score — Action Required'
})

const scoreDescription = computed(() => {
  const s = report.value?.executive_summary.modernization_score ?? 0
  if (s >= 80) return 'The codebase is in excellent shape with minimal technical debt.'
  if (s >= 60) return 'Some improvements are recommended but the codebase is manageable.'
  if (s >= 40) return 'Significant architectural issues detected — refactoring is advised.'
  return 'Critical issues exist throughout the codebase. Immediate refactoring is strongly recommended.'
})

// ── Smell helpers ─────────────────────────────────────────────────────────────
function sevColor(sev: string): string {
  const map: Record<string, string> = {
    critical: '#f87171', high: '#fb923c', medium: '#fde047', low: '#86efac',
  }
  return map[sev] ?? '#94a3b8'
}

function riskColor(sev: Severity | null): string {
  const map: Record<string, string> = {
    low: '#22c55e', medium: '#f59e0b', high: '#f97316', critical: '#ef4444',
  }
  return map[sev ?? ''] ?? 'var(--color-text-muted)'
}

const topSmellTypes = computed(() => {
  if (!report.value) return []
  return Object.entries(report.value.smell_breakdown.by_type)
    .sort(([, a], [, b]) => (b ?? 0) - (a ?? 0))
    .slice(0, 6)
})

// ── Export ────────────────────────────────────────────────────────────────────
async function exportPdf(): Promise<void> {
  isExportingPdf.value = true
  try {
    const { data } = await reportApi.exportPDF(jobId)
    const url = URL.createObjectURL(data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `alm-report-${jobId.slice(0, 8)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'PDF export failed', message: String(err), duration: 5000 })
  } finally {
    isExportingPdf.value = false
  }
}

async function exportMarkdown(): Promise<void> {
  isExportingMd.value = true
  try {
    const { data } = await reportApi.exportMarkdown(jobId)
    const blob = new Blob([data as string], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `alm-report-${jobId.slice(0, 8)}.md`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    uiStore.notify({ type: 'error', title: 'Markdown export failed', message: String(err), duration: 5000 })
  } finally {
    isExportingMd.value = false
  }
}

// ── Data load ─────────────────────────────────────────────────────────────────
async function loadReport(force = false): Promise<void> {
  if (!force && _reportCache.has(jobId)) {
    report.value = _reportCache.get(jobId)!
    return
  }
  const inflight = _reportInFlight.get(jobId)
  if (inflight) {
    await inflight
    report.value = _reportCache.get(jobId) ?? null
    return
  }
  isLoading.value = true
  loadError.value = null
  const promise = reportApi.getReport(jobId)
    .then(({ data }) => {
      report.value = data
      _reportCache.set(jobId, data)
    })
    .catch((err) => {
      loadError.value = err instanceof Error ? err.message : String(err)
    })
    .finally(() => {
      isLoading.value = false
      _reportInFlight.delete(jobId)
    })
  _reportInFlight.set(jobId, promise)
  await promise
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

onMounted(() => loadReport())

// ── MetricCard inline component ───────────────────────────────────────────────
type CardColor = 'red' | 'indigo' | 'orange' | 'green'
const CARD_BG: Record<CardColor, string> = {
  red:    'rgba(239,68,68,0.12)',
  indigo: 'rgba(99,102,241,0.12)',
  orange: 'rgba(249,115,22,0.12)',
  green:  'rgba(34,197,94,0.12)',
}
const CARD_COLOR: Record<CardColor, string> = {
  red:    '#fca5a5',
  indigo: '#a5b4fc',
  orange: '#fdba74',
  green:  '#86efac',
}

const MetricCard = defineComponent({
  name: 'MetricCard',
  props: {
    label: String,
    value: [String, Number],
    sub: String,
    icon: String,
    color: { type: String as () => CardColor, default: 'indigo' },
  },
  setup(props) {
    return () =>
      h(
        'div',
        {
          class: 'flex flex-col items-center justify-center p-5 rounded-xl border text-center',
          style: `background: var(--color-card); border-color: var(--color-border)`,
        },
        [
          h(
            'div',
            {
              class: 'flex items-center justify-center w-10 h-10 rounded-xl text-lg mb-3',
              style: `background: ${CARD_BG[props.color!]}; color: ${CARD_COLOR[props.color!]}`,
            },
            props.icon,
          ),
          h('p', { class: 'text-2xl font-bold', style: `color: ${CARD_COLOR[props.color!]}` }, String(props.value)),
          h('p', { class: 'text-xs font-medium mt-0.5', style: 'color: var(--color-text)' }, props.label),
          h('p', { class: 'text-xs mt-0.5', style: 'color: var(--color-text-muted)' }, props.sub),
        ],
      )
  },
})
</script>
