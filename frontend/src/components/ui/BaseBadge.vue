<template>
  <span
    :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', colorClass]"
  >
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Color =
  | 'indigo'
  | 'blue'
  | 'green'
  | 'red'
  | 'yellow'
  | 'orange'
  | 'purple'
  | 'pink'
  | 'teal'
  | 'gray'

const props = withDefaults(
  defineProps<{ label?: string; color?: Color }>(),
  { color: 'gray', label: '' },
)

const colorClass = computed(() => {
  const map: Record<Color, string> = {
    indigo:  'bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/30',
    blue:    'bg-blue-500/15 text-blue-300 ring-1 ring-blue-500/30',
    green:   'bg-green-500/15 text-green-300 ring-1 ring-green-500/30',
    red:     'bg-red-500/15 text-red-300 ring-1 ring-red-500/30',
    yellow:  'bg-yellow-500/15 text-yellow-300 ring-1 ring-yellow-500/30',
    orange:  'bg-orange-500/15 text-orange-300 ring-1 ring-orange-500/30',
    purple:  'bg-purple-500/15 text-purple-300 ring-1 ring-purple-500/30',
    pink:    'bg-pink-500/15 text-pink-300 ring-1 ring-pink-500/30',
    teal:    'bg-teal-500/15 text-teal-300 ring-1 ring-teal-500/30',
    gray:    'bg-slate-500/15 text-slate-300 ring-1 ring-slate-500/30',
  }
  return map[props.color]
})
</script>
