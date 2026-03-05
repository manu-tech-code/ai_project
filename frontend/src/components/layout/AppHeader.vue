<template>
  <header
    class="flex items-center h-14 px-5 gap-4 flex-shrink-0 border-b"
    :style="{
      background: 'var(--color-card)',
      borderColor: 'var(--color-border)',
    }"
  >
    <!-- Hamburger (mobile) -->
    <button
      @click="uiStore.sidebarCollapsed = !uiStore.sidebarCollapsed"
      class="flex items-center justify-center w-8 h-8 rounded-md transition-colors"
      :style="{ color: 'var(--color-text-muted)' }"
      title="Toggle sidebar"
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
      </svg>
    </button>

    <!-- Breadcrumb -->
    <nav class="flex items-center gap-1.5 flex-1 min-w-0 text-sm">
      <RouterLink
        to="/"
        class="transition-colors hover:opacity-80 flex-shrink-0"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        ALM
      </RouterLink>

      <template v-if="breadcrumbs.length">
        <span :style="{ color: 'var(--color-text-muted)' }">/</span>
        <template v-for="(crumb, i) in breadcrumbs" :key="i">
          <RouterLink
            v-if="i < breadcrumbs.length - 1 && crumb.to"
            :to="crumb.to"
            class="transition-colors hover:opacity-80 truncate"
            :style="{ color: 'var(--color-text-muted)' }"
          >
            {{ crumb.label }}
          </RouterLink>
          <span
            v-else
            class="font-medium truncate"
            :style="{ color: 'var(--color-text)' }"
          >
            {{ crumb.label }}
          </span>
          <span
            v-if="i < breadcrumbs.length - 1"
            :style="{ color: 'var(--color-text-muted)' }"
          >/</span>
        </template>
      </template>
    </nav>

    <!-- Right side controls -->
    <div class="flex items-center gap-3 flex-shrink-0">
      <!-- Active job status -->
      <div v-if="analysisStore.activeJob" class="flex items-center gap-2">
        <StatusBadge :status="analysisStore.activeJob.status" />
        <span
          class="text-xs hidden sm:block truncate max-w-[120px]"
          :style="{ color: 'var(--color-text-muted)' }"
        >
          {{ analysisStore.activeJob.label || shortId(analysisStore.activeJob.job_id) }}
        </span>
      </div>

      <!-- Notification count -->
      <button
        v-if="uiStore.notifications.length"
        class="relative flex items-center justify-center w-8 h-8 rounded-md transition-colors"
        :style="{ color: 'var(--color-text-secondary)' }"
        title="Notifications"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>
        <span
          class="absolute -top-0.5 -right-0.5 flex items-center justify-center w-4 h-4 text-xs font-bold rounded-full text-white"
          style="background: var(--color-error); font-size: 10px"
        >
          {{ uiStore.notifications.length }}
        </span>
      </button>

      <!-- API Key indicator -->
      <div
        class="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs"
        :style="{
          background: hasApiKey ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
          color: hasApiKey ? 'var(--color-success)' : 'var(--color-error)',
        }"
        :title="hasApiKey ? 'API key configured' : 'No API key — set alm_api_key in localStorage'"
      >
        <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :style="{ background: hasApiKey ? 'var(--color-success)' : 'var(--color-error)' }" />
        <span class="hidden sm:block">{{ hasApiKey ? 'Connected' : 'No Key' }}</span>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useUIStore } from '@/stores/ui'

const uiStore = useUIStore()
const analysisStore = useAnalysisStore()
const route = useRoute()

const hasApiKey = computed(() => !!(localStorage.getItem('alm_api_key') || import.meta.env.VITE_API_KEY))

interface Crumb { label: string; to?: string }

const breadcrumbs = computed<Crumb[]>(() => {
  const name = route.name as string | undefined
  const jobId = route.params.jobId as string | undefined

  if (!name || name === 'home') return []

  const crumbs: Crumb[] = []

  if (name === 'analyze') {
    crumbs.push({ label: 'New Analysis' })
  } else if (jobId) {
    const shortId = jobId.slice(0, 8)
    const jobLabel = analysisStore.activeJob?.label

    crumbs.push({
      label: jobLabel ? `${jobLabel} (${shortId})` : `Job ${shortId}`,
      to: `/jobs/${jobId}/graph`,
    })

    const pageMap: Record<string, string> = {
      graph: 'Graph',
      smells: 'Smells',
      plan: 'Plan',
      patches: 'Patches',
      report: 'Report',
    }
    if (pageMap[name]) {
      crumbs.push({ label: pageMap[name] })
    }
  }

  return crumbs
})

function shortId(id: string): string {
  return id.slice(0, 8) + '…'
}
</script>
