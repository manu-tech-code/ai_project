<template>
  <span
    :class="[
      'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold',
      colorClass,
    ]"
  >
    <span v-if="showDot" class="w-1.5 h-1.5 rounded-full flex-shrink-0" :style="dotStyle" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Severity } from '@/types'

const props = withDefaults(
  defineProps<{
    severity: Severity
    showDot?: boolean
    label?: string
  }>(),
  { showDot: false },
)

const SEV_MAP: Record<Severity, { classes: string; dot: string; displayLabel: string }> = {
  critical: { classes: 'bg-red-500/15 text-red-300 ring-1 ring-red-500/30',       dot: '#f87171', displayLabel: 'CRITICAL' },
  high:     { classes: 'bg-orange-500/15 text-orange-300 ring-1 ring-orange-500/30', dot: '#fb923c', displayLabel: 'HIGH' },
  medium:   { classes: 'bg-yellow-500/15 text-yellow-300 ring-1 ring-yellow-500/30', dot: '#fde047', displayLabel: 'MEDIUM' },
  low:      { classes: 'bg-green-500/15 text-green-300 ring-1 ring-green-500/30',  dot: '#86efac', displayLabel: 'LOW' },
}

const entry = computed(() => SEV_MAP[props.severity] ?? SEV_MAP.low)
const colorClass = computed(() => entry.value.classes)
const dotStyle = computed(() => ({ background: entry.value.dot }))
const label = computed(() => props.label ?? entry.value.displayLabel)
</script>
