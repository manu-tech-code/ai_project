<template>
  <div
    class="flex flex-col gap-4 overflow-y-auto"
    :style="{ color: 'var(--color-text)' }"
  >
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-semibold uppercase tracking-widest" style="color: var(--color-text-muted)">
        Graph Controls
      </h3>
      <button
        v-if="isFiltered"
        @click="graphStore.resetFilters()"
        class="text-xs transition-colors"
        style="color: var(--color-primary)"
      >
        Reset
      </button>
    </div>

    <!-- Search -->
    <div class="relative">
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
        v-model="graphStore.filters.searchQuery"
        type="text"
        placeholder="Search nodes…"
        class="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border focus:outline-none transition-colors"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }"
      />
    </div>

    <!-- Node type filters -->
    <div>
      <p class="text-xs font-medium mb-2" style="color: var(--color-text-muted)">Node Types</p>
      <div class="space-y-1">
        <label
          v-for="nt in NODE_TYPES"
          :key="nt.type"
          class="flex items-center gap-2 px-1 py-0.5 rounded cursor-pointer group"
          :class="{ 'opacity-50': !isTypeVisible(nt.type) }"
        >
          <input
            type="checkbox"
            :value="nt.type"
            v-model="graphStore.filters.nodeTypes"
            class="w-3 h-3 rounded accent-indigo-500"
          />
          <!-- Color dot -->
          <span
            class="w-2 h-2 rounded-full flex-shrink-0"
            :style="{ background: nt.color }"
          />
          <span class="text-xs flex-1" style="color: var(--color-text-secondary)">{{ nt.type }}</span>
          <span class="text-xs" style="color: var(--color-text-muted)">
            {{ nodeTypeCount(nt.type) }}
          </span>
        </label>
      </div>
    </div>

    <!-- Language filters -->
    <div v-if="availableLanguages.length > 0">
      <p class="text-xs font-medium mb-2" style="color: var(--color-text-muted)">Languages</p>
      <div class="space-y-1">
        <label
          v-for="lang in availableLanguages"
          :key="lang"
          class="flex items-center gap-2 px-1 py-0.5 rounded cursor-pointer"
        >
          <input
            type="checkbox"
            :value="lang"
            v-model="graphStore.filters.languages"
            class="w-3 h-3 rounded accent-indigo-500"
          />
          <span class="text-xs" style="color: var(--color-text-secondary)">{{ lang }}</span>
        </label>
      </div>
    </div>

    <!-- Layout selector -->
    <div>
      <p class="text-xs font-medium mb-2" style="color: var(--color-text-muted)">Layout</p>
      <select
        v-model="selectedLayout"
        @change="$emit('relayout', selectedLayout)"
        class="w-full px-2 py-1.5 text-xs rounded-md border"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text)',
        }"
      >
        <option value="dagre">Dagre (hierarchical)</option>
        <option value="cose">CoSE (force-directed)</option>
        <option value="breadthfirst">Breadth-first tree</option>
        <option value="circle">Circle</option>
        <option value="grid">Grid</option>
      </select>
    </div>

    <!-- Action buttons -->
    <div class="flex flex-col gap-2 pt-1">
      <button
        @click="$emit('fit')"
        class="flex items-center gap-2 px-3 py-1.5 text-xs rounded-md border transition-colors"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-secondary)',
        }"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
        </svg>
        Fit to screen
      </button>

      <button
        @click="$emit('export-png')"
        class="flex items-center gap-2 px-3 py-1.5 text-xs rounded-md border transition-colors"
        :style="{
          background: 'var(--color-elevated)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-secondary)',
        }"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        Export PNG
      </button>
    </div>

    <!-- Stats summary -->
    <div
      class="rounded-md px-3 py-2 space-y-1"
      :style="{ background: 'var(--color-elevated)' }"
    >
      <div class="flex justify-between text-xs">
        <span style="color: var(--color-text-muted)">Visible nodes</span>
        <span class="font-medium" style="color: var(--color-text)">{{ graphStore.filteredNodes.length }}</span>
      </div>
      <div class="flex justify-between text-xs">
        <span style="color: var(--color-text-muted)">Total nodes</span>
        <span class="font-medium" style="color: var(--color-text)">{{ graphStore.nodes.length }}</span>
      </div>
      <div class="flex justify-between text-xs">
        <span style="color: var(--color-text-muted)">Total edges</span>
        <span class="font-medium" style="color: var(--color-text)">{{ graphStore.edges.length }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGraphStore } from '@/stores/graph'

defineEmits<{
  fit: []
  'export-png': []
  relayout: [layoutName: string]
}>()

const graphStore = useGraphStore()
const selectedLayout = ref('dagre')

const NODE_TYPES = [
  { type: 'CLASS',      color: '#6366f1' },
  { type: 'INTERFACE',  color: '#6366f1' },
  { type: 'METHOD',     color: '#22c55e' },
  { type: 'FUNCTION',   color: '#22c55e' },
  { type: 'FILE',       color: '#a855f7' },
  { type: 'MODULE',     color: '#a855f7' },
  { type: 'FIELD',      color: '#f97316' },
  { type: 'VARIABLE',   color: '#f97316' },
  { type: 'IMPORT',     color: '#9ca3af' },
  { type: 'ANNOTATION', color: '#14b8a6' },
  { type: 'CALL_SITE',  color: '#f59e0b' },
]

const availableLanguages = computed(() => {
  const langs = new Set(graphStore.nodes.map((n) => n.language))
  return [...langs].sort()
})

const isFiltered = computed(
  () =>
    graphStore.filters.nodeTypes.length > 0 ||
    graphStore.filters.languages.length > 0 ||
    graphStore.filters.searchQuery.length > 0,
)

function nodeTypeCount(type: string): number {
  return graphStore.nodes.filter((n) => n.node_type === type).length
}

function isTypeVisible(type: string): boolean {
  return (
    graphStore.filters.nodeTypes.length === 0 ||
    graphStore.filters.nodeTypes.includes(type as any)
  )
}
</script>
