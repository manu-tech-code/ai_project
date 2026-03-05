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

      <!-- API Key indicator / generate button -->
      <div
        v-if="hasApiKey"
        class="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs"
        :style="{ background: 'rgba(34,197,94,0.1)', color: 'var(--color-success)' }"
        title="API key configured"
      >
        <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" style="background: var(--color-success)" />
        <span class="hidden sm:block">Connected</span>
      </div>
      <button
        v-else
        class="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-opacity"
        :style="{ background: 'rgba(99,102,241,0.15)', color: 'var(--color-accent, #6366f1)' }"
        :disabled="generatingKey"
        title="Click to generate and save an API key"
        @click="handleGenerateKey"
      >
        <svg v-if="generatingKey" class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        <svg v-else class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"
          />
        </svg>
        <span class="hidden sm:block">{{ generatingKey ? 'Generating…' : 'Generate Key' }}</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useAnalysisStore } from '@/stores/analysis'
import { useUIStore } from '@/stores/ui'
import { generateAndSaveApiKey, getApiKey } from '@/api/client'

const uiStore = useUIStore()
const analysisStore = useAnalysisStore()
const route = useRoute()

const apiKeyPresent = ref(!!(getApiKey()))
const hasApiKey = computed(() => apiKeyPresent.value)
const generatingKey = ref(false)

async function handleGenerateKey() {
  generatingKey.value = true
  try {
    await generateAndSaveApiKey()
    apiKeyPresent.value = true
    uiStore.notify({ type: 'success', title: 'API Key Generated', message: 'Your API key has been saved.', duration: 4000 })
  } catch {
    uiStore.notify({ type: 'error', title: 'Key Generation Failed', message: 'Could not generate an API key.', duration: 5000 })
  } finally {
    generatingKey.value = false
  }
}

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
