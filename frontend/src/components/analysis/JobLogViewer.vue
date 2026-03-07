<template>
  <div
    class="rounded-lg overflow-hidden font-mono text-xs"
    style="background: #0d1117; border: 1px solid var(--color-border)"
  >
    <!-- Header bar -->
    <div
      class="flex items-center justify-between px-3 py-2"
      style="background: #161b22; border-bottom: 1px solid var(--color-border)"
    >
      <div class="flex items-center gap-2">
        <!-- Pulsing dot when running -->
        <span v-if="isRunning" class="relative flex h-2 w-2">
          <span
            class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
            style="background: var(--color-primary)"
          />
          <span
            class="relative inline-flex rounded-full h-2 w-2"
            style="background: var(--color-primary)"
          />
        </span>
        <span v-else class="h-2 w-2 rounded-full" style="background: var(--color-border)" />
        <span style="color: var(--color-text-secondary)">Agent Output</span>
      </div>
      <button
        v-if="logs.length > 0"
        @click="scrollLocked = !scrollLocked"
        class="text-xs px-2 py-0.5 rounded transition-colors"
        :style="{
          background: scrollLocked ? 'rgba(99,102,241,0.2)' : 'transparent',
          color: scrollLocked ? 'var(--color-primary)' : 'var(--color-text-muted)',
          border: '1px solid',
          borderColor: scrollLocked ? 'rgba(99,102,241,0.4)' : 'var(--color-border)',
        }"
      >
        {{ scrollLocked ? 'Locked' : 'Lock scroll' }}
      </button>
    </div>

    <!-- Log body -->
    <div
      ref="logContainer"
      class="overflow-y-auto px-3 py-2 space-y-0.5"
      :style="{ maxHeight: maxHeight ?? '300px' }"
      @scroll="onScroll"
    >
      <!-- Empty state -->
      <div
        v-if="logs.length === 0"
        class="py-6 text-center"
        style="color: var(--color-text-muted)"
      >
        Waiting for agent output...
      </div>

      <!-- Log lines -->
      <div
        v-for="entry in logs"
        :key="entry.seq"
        class="flex items-start gap-2 leading-5"
      >
        <!-- Timestamp -->
        <span class="flex-shrink-0" style="color: #484f58">
          {{ formatTime(entry.created_at) }}
        </span>

        <!-- Stage label -->
        <span
          class="flex-shrink-0 w-16 truncate"
          :style="{ color: stageColor(entry.stage) }"
        >
          [{{ entry.stage }}]
        </span>

        <!-- Message -->
        <span class="flex-1 break-all" style="color: #e6edf3">{{ entry.message }}</span>

        <!-- Percent -->
        <span v-if="entry.percent > 0" class="flex-shrink-0" style="color: #484f58">
          {{ entry.percent }}%
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { JobLogEntry } from '@/types'

const props = defineProps<{
  logs: JobLogEntry[]
  isRunning: boolean
  maxHeight?: string
}>()

const logContainer = ref<HTMLElement | null>(null)
const scrollLocked = ref(false)

function formatTime(iso: string): string {
  const d = new Date(iso)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

function stageColor(stage: string): string {
  const s = stage.toLowerCase()
  if (s === 'analyzing' || s === 'detecting')  return 'var(--color-primary)'
  if (s === 'validating' || s === 'complete')  return 'var(--color-success)'
  if (s === 'failed' || s === 'error')         return 'var(--color-error)'
  if (s === 'planning' || s === 'mapping')     return '#f59e0b'
  if (s === 'transforming')                    return '#a78bfa'
  return 'var(--color-text-secondary)'
}

function onScroll(): void {
  if (!logContainer.value) return
  const el = logContainer.value
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8
  // If user scrolled up manually, unlock auto-scroll
  if (!atBottom && !scrollLocked.value) {
    scrollLocked.value = true
  }
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (logContainer.value && !scrollLocked.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

watch(() => props.logs.length, scrollToBottom)
</script>
