<template>
  <span :class="['inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold', colorClass]">
    <!-- Animated pulse for active statuses -->
    <span
      v-if="isActive"
      class="w-1.5 h-1.5 rounded-full animate-pulse-dot flex-shrink-0"
      :style="dotStyle"
    />
    {{ displayLabel }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const ACTIVE_STATUSES = new Set([
  'pending', 'detecting', 'mapping', 'analyzing', 'planning', 'transforming', 'validating',
])

const STATUS_MAP: Record<string, { classes: string; dot: string; label: string }> = {
  // Job statuses
  pending:      { classes: 'bg-slate-500/15 text-slate-300',   dot: '#94a3b8', label: 'Pending' },
  detecting:    { classes: 'bg-blue-500/15 text-blue-300',     dot: '#93c5fd', label: 'Detecting' },
  mapping:      { classes: 'bg-blue-500/15 text-blue-300',     dot: '#93c5fd', label: 'Mapping' },
  analyzing:    { classes: 'bg-yellow-500/15 text-yellow-300', dot: '#fde047', label: 'Analyzing' },
  planning:     { classes: 'bg-yellow-500/15 text-yellow-300', dot: '#fde047', label: 'Planning' },
  transforming: { classes: 'bg-purple-500/15 text-purple-300', dot: '#d8b4fe', label: 'Transforming' },
  validating:   { classes: 'bg-purple-500/15 text-purple-300', dot: '#d8b4fe', label: 'Validating' },
  complete:     { classes: 'bg-green-500/15 text-green-300',   dot: '#86efac', label: 'Complete' },
  failed:       { classes: 'bg-red-500/15 text-red-400',       dot: '#f87171', label: 'Failed' },
  cancelled:    { classes: 'bg-slate-500/15 text-slate-400',   dot: '#94a3b8', label: 'Cancelled' },
  // Patch/task statuses
  applied:      { classes: 'bg-green-500/15 text-green-300',   dot: '#86efac', label: 'Applied' },
  reverted:     { classes: 'bg-orange-500/15 text-orange-300', dot: '#fdba74', label: 'Reverted' },
  approved:     { classes: 'bg-green-500/15 text-green-300',   dot: '#86efac', label: 'Approved' },
  rejected:     { classes: 'bg-red-500/15 text-red-400',       dot: '#f87171', label: 'Rejected' },
}

const props = defineProps<{ status: string }>()

const entry = computed(() => STATUS_MAP[props.status] ?? {
  classes: 'bg-slate-500/15 text-slate-300',
  dot: '#94a3b8',
  label: props.status,
})

const colorClass = computed(() => entry.value.classes)
const dotStyle   = computed(() => ({ background: entry.value.dot }))
const displayLabel = computed(() => entry.value.label)
const isActive   = computed(() => ACTIVE_STATUSES.has(props.status))
</script>
