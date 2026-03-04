<template>
  <div
    class="rounded-xl border overflow-hidden transition-shadow"
    :style="{
      background: 'var(--color-card)',
      borderColor: 'var(--color-border)',
    }"
  >
    <!-- Task header -->
    <div class="flex items-start gap-4 px-4 pt-4 pb-3">
      <!-- Order number -->
      <div
        class="flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold flex-shrink-0 mt-0.5"
        :style="{
          background: 'var(--color-elevated)',
          color: statusColor,
          border: `1px solid ${statusColor}40`,
        }"
      >
        {{ task.status === 'pending' ? order : statusIcon }}
      </div>

      <!-- Content -->
      <div class="flex-1 min-w-0">
        <!-- Badges row -->
        <div class="flex flex-wrap items-center gap-1.5 mb-2">
          <BaseBadge :label="formatPattern(task.refactor_pattern)" color="indigo" />
          <BaseBadge v-if="task.automated" label="Automated" color="green" />
          <StatusBadge v-if="task.status !== 'pending'" :status="task.status" />
        </div>

        <!-- Title -->
        <h3 class="text-sm font-semibold leading-snug" style="color: var(--color-text)">
          {{ task.title }}
        </h3>

        <!-- Description -->
        <p
          v-if="!showFull"
          class="mt-1.5 text-xs leading-relaxed line-clamp-2"
          style="color: var(--color-text-secondary)"
        >
          {{ task.description }}
        </p>
        <p
          v-else
          class="mt-1.5 text-xs leading-relaxed"
          style="color: var(--color-text-secondary)"
        >
          {{ task.description }}
        </p>
        <button
          @click="showFull = !showFull"
          class="mt-1 text-xs transition-colors"
          style="color: var(--color-primary)"
        >
          {{ showFull ? 'Show less' : 'Show more' }}
        </button>
      </div>

      <!-- Actions -->
      <div v-if="!readonly" class="flex items-center gap-2 flex-shrink-0">
        <template v-if="task.status === 'pending'">
          <button
            @click="$emit('approve', task.task_id)"
            class="px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
            style="background: rgba(34,197,94,0.15); color: #86efac; border: 1px solid rgba(34,197,94,0.3)"
          >
            Approve
          </button>
          <button
            @click="$emit('reject', task.task_id)"
            class="px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
            :style="{
              background: 'var(--color-elevated)',
              color: 'var(--color-text-muted)',
              border: '1px solid var(--color-border)',
            }"
          >
            Reject
          </button>
        </template>
        <template v-else>
          <StatusBadge :status="task.status" />
        </template>
      </div>
    </div>

    <!-- Meta bar -->
    <div
      class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 pb-3 text-xs"
      style="color: var(--color-text-muted)"
    >
      <span v-if="task.estimated_hours != null" class="flex items-center gap-1">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" stroke-width="2" />
          <path stroke-linecap="round" stroke-width="2" d="M12 6v6l4 2" />
        </svg>
        {{ task.estimated_hours }}h
      </span>
      <span class="flex items-center gap-1">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        {{ task.affected_files.length }} file{{ task.affected_files.length === 1 ? '' : 's' }}
      </span>
      <span v-if="task.smell_ids.length" class="flex items-center gap-1">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        {{ task.smell_ids.length }} smell{{ task.smell_ids.length === 1 ? '' : 's' }}
      </span>
      <span v-if="depNames.length">
        Depends on:
        <span
          v-for="(dep, i) in depNames"
          :key="i"
          class="font-mono"
          style="color: var(--color-text-secondary)"
        >{{ dep }}{{ i < depNames.length - 1 ? ', ' : '' }}</span>
      </span>
    </div>

    <!-- Notes -->
    <div
      v-if="task.notes"
      class="px-4 pb-3"
    >
      <p
        class="text-xs p-2 rounded-md italic"
        :style="{
          background: 'var(--color-elevated)',
          color: 'var(--color-text-secondary)',
        }"
      >
        Note: {{ task.notes }}
      </p>
    </div>

    <!-- Affected files (collapsed) -->
    <div
      v-if="task.affected_files.length"
      class="border-t"
      :style="{ borderColor: 'var(--color-border)' }"
    >
      <button
        @click="showFiles = !showFiles"
        class="flex items-center justify-between w-full px-4 py-2 text-xs transition-colors"
        :style="{ color: 'var(--color-text-muted)' }"
      >
        <span>Affected files ({{ task.affected_files.length }})</span>
        <svg
          class="w-3.5 h-3.5 transition-transform"
          :class="showFiles ? 'rotate-180' : ''"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div v-if="showFiles" class="px-4 pb-3 space-y-1">
        <p
          v-for="f in task.affected_files"
          :key="f"
          class="text-xs font-mono truncate"
          style="color: var(--color-text-secondary)"
          :title="f"
        >
          {{ f }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import type { PlanTask } from '@/types'

const props = defineProps<{
  task: PlanTask
  allTasks?: PlanTask[]
  readonly?: boolean
  order?: number
}>()

defineEmits<{
  approve: [taskId: string]
  reject: [taskId: string]
}>()

const showFull  = ref(false)
const showFiles = ref(false)

const statusColor = computed(() => {
  const map: Record<string, string> = {
    pending:  '#94a3b8',
    approved: '#22c55e',
    rejected: '#ef4444',
    applied:  '#6366f1',
  }
  return map[props.task.status] ?? '#94a3b8'
})

const statusIcon = computed(() => {
  const map: Record<string, string> = {
    approved: '✓',
    rejected: '✕',
    applied:  '★',
  }
  return map[props.task.status] ?? '?'
})

function formatPattern(pattern: string): string {
  return pattern.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

const depNames = computed(() => {
  if (!props.task.dependencies.length || !props.allTasks?.length) return []
  return props.task.dependencies.map((id) => {
    const dep = props.allTasks?.find((t) => t.task_id === id)
    return dep ? dep.title.slice(0, 20) + (dep.title.length > 20 ? '…' : '') : id.slice(0, 8)
  })
})
</script>
