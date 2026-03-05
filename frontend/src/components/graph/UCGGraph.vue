<template>
  <div class="relative w-full h-full">
    <!-- Loading overlay -->
    <div
      v-if="graphStore.isLoading"
      class="absolute inset-0 flex flex-col items-center justify-center z-10"
      style="background: rgba(15,17,23,0.85)"
    >
      <svg class="w-8 h-8 animate-spin mb-3" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-20" cx="12" cy="12" r="10" stroke="#6366f1" stroke-width="3" />
        <path class="opacity-90" fill="#6366f1"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <p class="text-sm" style="color: var(--color-text-secondary)">Loading graph…</p>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!graphStore.hasData"
      class="absolute inset-0 flex flex-col items-center justify-center"
    >
      <div
        class="flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
        style="background: var(--color-elevated)"
      >
        <svg class="w-8 h-8" style="color: var(--color-text-muted)" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="3" stroke-width="2" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M12 3v2m0 14v2M3 12h2m14 0h2M5.636 5.636l1.414 1.414M16.95 16.95l1.414 1.414M5.636 18.364l1.414-1.414M16.95 7.05l1.414-1.414" />
        </svg>
      </div>
      <p class="text-sm font-medium" style="color: var(--color-text)">No graph data</p>
      <p class="mt-1 text-xs text-center max-w-[200px]" style="color: var(--color-text-muted)">
        The UCG will appear here once analysis completes.
      </p>
    </div>

    <!-- Cytoscape canvas -->
    <div
      ref="containerRef"
      class="w-full h-full"
      style="background: #0f1117"
    />

    <!-- Node count overlay -->
    <div
      v-if="graphStore.hasData"
      class="absolute bottom-3 left-3 flex items-center gap-3 px-3 py-1.5 rounded-lg text-xs pointer-events-none"
      style="background: rgba(26,29,39,0.9); border: 1px solid var(--color-border); color: var(--color-text-secondary)"
    >
      <span>{{ graphStore.filteredNodes.length }} nodes</span>
      <span class="opacity-40">|</span>
      <span>{{ visibleEdgeCount }} edges</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import cytoscape from 'cytoscape'
// @ts-ignore — no types for cytoscape-dagre
import dagre from 'cytoscape-dagre'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useGraphStore } from '@/stores/graph'

// Register dagre layout (safe to call multiple times)
try { cytoscape.use(dagre) } catch { /* already registered */ }

const props = withDefaults(
  defineProps<{
    jobId: string
    height?: string
  }>(),
  { height: '100%' },
)

const emit = defineEmits<{
  nodeClick: [nodeId: string]
  edgeClick: [edgeId: string]
  backgroundClick: []
}>()

const graphStore = useGraphStore()
const containerRef = ref<HTMLDivElement | null>(null)
let cy: cytoscape.Core | null = null

// ── Color palette by node type ──────────────────────────────────────────────
const NODE_COLORS: Record<string, string> = {
  CLASS:      '#6366f1',  // indigo
  INTERFACE:  '#6366f1',  // indigo
  METHOD:     '#22c55e',  // green
  FUNCTION:   '#22c55e',  // green
  FILE:       '#a855f7',  // purple
  MODULE:     '#a855f7',  // purple
  FIELD:      '#f97316',  // orange
  VARIABLE:   '#f97316',  // orange
  PARAMETER:  '#f97316',  // orange (lighter variant)
  IMPORT:     '#9ca3af',  // gray
  ANNOTATION: '#14b8a6',  // teal
  BLOCK:      '#64748b',  // slate
  CALL_SITE:  '#f59e0b',  // amber
  TYPE_REF:   '#3b82f6',  // blue
  COMMENT:    '#475569',  // slate-muted
}

function getNodeColor(nodeType: string): string {
  return NODE_COLORS[nodeType] ?? '#6b7280'
}

// LOC → size in px (clamped 20–72px)
function getNodeSize(lines: number): number {
  return Math.min(72, Math.max(20, 20 + lines / 8))
}

// ── Cytoscape stylesheet ─────────────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildStyle(): any[] {
  return [
    {
      selector: 'node',
      style: {
        'background-color': (ele: cytoscape.NodeSingular) => getNodeColor(ele.data('node_type')),
        'width': (ele: cytoscape.NodeSingular) => getNodeSize(ele.data('lines') ?? 0),
        'height': (ele: cytoscape.NodeSingular) => getNodeSize(ele.data('lines') ?? 0),
        'label': 'data(label)',
        'font-size': '10px',
        'font-family': 'Inter, sans-serif',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'color': '#f1f5f9',
        'text-margin-y': '4px',
        'text-outline-width': 1,
        'text-outline-color': '#0f1117',
        'border-width': 2,
        'border-color': 'rgba(255,255,255,0)',
        'transition-property': 'border-color, width, height',
        'transition-duration': '0.15s' as any,
      },
    },
    {
      selector: 'edge',
      style: {
        'line-color': '#2d3148',
        'target-arrow-color': '#2d3148',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'width': (ele: cytoscape.EdgeSingular) => Math.max(1, (ele.data('weight') ?? 1) * 1.5),
        'opacity': 0.7,
        'label': '',
      },
    },
    {
      selector: 'node:selected',
      style: {
        'border-color': '#6366f1',
        'border-width': 3,
      },
    },
    {
      selector: 'node:active',
      style: {
        'overlay-color': '#6366f1',
        'overlay-opacity': 0.15,
      },
    },
    {
      selector: 'edge:selected',
      style: {
        'line-color': '#6366f1',
        'target-arrow-color': '#6366f1',
        'opacity': 1,
      },
    },
  ]
}

// ── Layout options ───────────────────────────────────────────────────────────
const LAYOUT_OPTIONS: cytoscape.LayoutOptions = {
  name: 'dagre',
  // @ts-ignore
  rankDir: 'LR',
  nodeSep: 40,
  rankSep: 80,
  padding: 20,
  animate: false,
}

// ── Init graph ───────────────────────────────────────────────────────────────
function initGraph(): void {
  if (!containerRef.value) return

  cy = cytoscape({
    container: containerRef.value,
    elements: graphStore.cytoscapeElements as cytoscape.ElementDefinition[],
    style: buildStyle(),
    layout: LAYOUT_OPTIONS,
    wheelSensitivity: 0.3,
    minZoom: 0.05,
    maxZoom: 5,
    boxSelectionEnabled: true,
    selectionType: 'single',
  })

  // Events
  cy.on('tap', 'node', (evt) => {
    graphStore.selectNode(evt.target.id())
    emit('nodeClick', evt.target.id())
  })
  cy.on('tap', 'edge', (evt) => {
    emit('edgeClick', evt.target.id())
  })
  cy.on('tap', (evt) => {
    if (evt.target === cy) {
      graphStore.selectNode(null)
      emit('backgroundClick')
    }
  })
}

// ── Fit to view (called from parent via ref) ─────────────────────────────────
function fitGraph(): void {
  cy?.fit(undefined, 30)
}

function resetZoom(): void {
  cy?.reset()
}

function exportPng(): string | undefined {
  return cy?.png({ scale: 2, full: true })
}

defineExpose({ fitGraph, resetZoom, exportPng })

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(initGraph)

watch(
  () => graphStore.cytoscapeElements,
  (elements) => {
    if (!cy) return
    cy.elements().remove()
    cy.add(elements as cytoscape.ElementDefinition[])
    cy.layout(LAYOUT_OPTIONS).run()
  },
  { deep: true },
)

onUnmounted(() => {
  cy?.destroy()
  cy = null
})

// ── Computed ─────────────────────────────────────────────────────────────────
const visibleEdgeCount = computed(() => {
  const nodeIds = new Set(graphStore.filteredNodes.map((n) => n.id))
  return graphStore.edges.filter(
    (e) => nodeIds.has(e.source_node_id) && nodeIds.has(e.target_node_id),
  ).length
})
</script>
