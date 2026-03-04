<template>
  <div class="flex h-full overflow-hidden" style="background: var(--color-bg)">
    <!-- Controls panel (left sidebar) -->
    <aside
      class="flex-shrink-0 border-r overflow-y-auto p-4"
      :style="{
        width: '240px',
        background: 'var(--color-card)',
        borderColor: 'var(--color-border)',
      }"
    >
      <GraphControls
        @fit="graphRef?.fitGraph()"
        @export-png="doExportPng"
        @relayout="onRelayout"
      />
    </aside>

    <!-- Main graph area -->
    <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <!-- Stats bar -->
      <div
        class="flex items-center gap-6 px-5 py-2.5 border-b flex-shrink-0 text-xs"
        :style="{
          background: 'var(--color-card)',
          borderColor: 'var(--color-border)',
          color: 'var(--color-text-muted)',
        }"
      >
        <template v-if="graphStore.metrics">
          <span>
            <span class="font-semibold" style="color: var(--color-text)">
              {{ graphStore.metrics.summary.total_nodes.toLocaleString() }}
            </span> nodes
          </span>
          <span>
            <span class="font-semibold" style="color: var(--color-text)">
              {{ graphStore.metrics.summary.total_edges.toLocaleString() }}
            </span> edges
          </span>
          <span>
            Avg coupling:
            <span class="font-semibold" style="color: var(--color-text)">
              {{ graphStore.metrics.summary.average_coupling.toFixed(1) }}
            </span>
          </span>
          <span>
            Circular deps:
            <span
              class="font-semibold"
              :style="{
                color: graphStore.metrics.summary.circular_dependency_count > 0
                  ? 'var(--color-error)' : 'var(--color-success)'
              }"
            >
              {{ graphStore.metrics.summary.circular_dependency_count }}
            </span>
          </span>
          <span>
            Dead code:
            <span
              class="font-semibold"
              :style="{
                color: graphStore.metrics.summary.dead_code_node_count > 0
                  ? 'var(--color-warning)' : 'var(--color-success)'
              }"
            >
              {{ graphStore.metrics.summary.dead_code_node_count }}
            </span>
          </span>
        </template>
        <span v-else-if="graphStore.isLoading">Loading metrics…</span>

        <!-- Languages detected -->
        <div class="ml-auto flex items-center gap-1.5">
          <span>Languages:</span>
          <BaseBadge
            v-for="lang in detectedLanguages"
            :key="lang"
            :label="lang"
            color="blue"
          />
        </div>
      </div>

      <!-- Graph canvas + node detail panel -->
      <div class="flex flex-1 overflow-hidden relative">
        <!-- Cytoscape canvas -->
        <UCGGraph
          ref="graphRef"
          :job-id="jobId"
          class="flex-1"
          @node-click="onNodeClick"
          @background-click="closeNodeDetail"
        />

        <!-- Node detail panel (slide-in from right) -->
        <Transition name="slide-right">
          <aside
            v-if="graphStore.selectedNode"
            class="absolute right-0 top-0 bottom-0 w-80 border-l overflow-y-auto flex flex-col"
            :style="{
              background: 'var(--color-card)',
              borderColor: 'var(--color-border)',
            }"
          >
            <!-- Header -->
            <div
              class="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
              :style="{ borderColor: 'var(--color-border)' }"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span
                  class="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  :style="{ background: nodeTypeColor(graphStore.selectedNode.node.node_type) }"
                />
                <p class="text-sm font-semibold truncate" style="color: var(--color-text)">
                  {{ shortName(graphStore.selectedNode.node.qualified_name) }}
                </p>
              </div>
              <button
                @click="closeNodeDetail"
                class="w-6 h-6 flex items-center justify-center text-base flex-shrink-0 transition-colors"
                style="color: var(--color-text-muted)"
              >
                &times;
              </button>
            </div>

            <!-- Node info -->
            <div class="px-4 py-3 space-y-4 flex-1">
              <!-- Type + language badges -->
              <div class="flex flex-wrap gap-1.5">
                <BaseBadge :label="graphStore.selectedNode.node.node_type" color="indigo" />
                <BaseBadge :label="graphStore.selectedNode.node.language" color="blue" />
              </div>

              <!-- Qualified name -->
              <div>
                <p class="text-xs font-medium mb-1" style="color: var(--color-text-muted)">Qualified Name</p>
                <p
                  class="text-xs font-mono break-all"
                  style="color: var(--color-text-secondary)"
                >
                  {{ graphStore.selectedNode.node.qualified_name }}
                </p>
              </div>

              <!-- File location -->
              <div v-if="graphStore.selectedNode.node.file_path">
                <p class="text-xs font-medium mb-1" style="color: var(--color-text-muted)">Location</p>
                <p
                  class="text-xs font-mono break-all"
                  style="color: var(--color-text-secondary)"
                >
                  {{ graphStore.selectedNode.node.file_path }}
                  <template v-if="graphStore.selectedNode.node.line_start">
                    :{{ graphStore.selectedNode.node.line_start }}
                    <template v-if="graphStore.selectedNode.node.line_end">
                      –{{ graphStore.selectedNode.node.line_end }}
                    </template>
                  </template>
                </p>
              </div>

              <!-- LOC metric -->
              <div v-if="graphStore.selectedNode.node.line_start && graphStore.selectedNode.node.line_end">
                <p class="text-xs font-medium mb-1" style="color: var(--color-text-muted)">Lines of Code</p>
                <p class="text-sm font-semibold" style="color: var(--color-text)">
                  {{ graphStore.selectedNode.node.line_end - graphStore.selectedNode.node.line_start }}
                </p>
              </div>

              <!-- Properties -->
              <div v-if="nodeProperties.length">
                <p class="text-xs font-medium mb-1.5" style="color: var(--color-text-muted)">Properties</p>
                <table class="w-full text-xs">
                  <tbody>
                    <tr
                      v-for="[k, v] in nodeProperties"
                      :key="k"
                      class="border-b last:border-0"
                      :style="{ borderColor: 'var(--color-border)' }"
                    >
                      <td class="py-1 pr-2 font-mono" style="color: var(--color-text-muted)">{{ k }}</td>
                      <td class="py-1 font-medium" style="color: var(--color-text)">{{ String(v) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- Incoming edges -->
              <div v-if="graphStore.selectedNode.incoming_edges.length">
                <p class="text-xs font-medium mb-1.5" style="color: var(--color-text-muted)">
                  Incoming ({{ graphStore.selectedNode.incoming_edges.length }})
                </p>
                <div class="space-y-1">
                  <div
                    v-for="e in graphStore.selectedNode.incoming_edges.slice(0, 8)"
                    :key="e.source_node_id"
                    class="flex items-center gap-1.5 text-xs"
                  >
                    <BaseBadge :label="e.edge_type" color="purple" />
                    <span class="font-mono truncate" style="color: var(--color-text-secondary)" :title="e.source_qualified_name">
                      {{ shortName(e.source_qualified_name) }}
                    </span>
                  </div>
                  <p
                    v-if="graphStore.selectedNode.incoming_edges.length > 8"
                    class="text-xs"
                    style="color: var(--color-text-muted)"
                  >
                    +{{ graphStore.selectedNode.incoming_edges.length - 8 }} more
                  </p>
                </div>
              </div>

              <!-- Outgoing edges -->
              <div v-if="graphStore.selectedNode.outgoing_edges.length">
                <p class="text-xs font-medium mb-1.5" style="color: var(--color-text-muted)">
                  Outgoing ({{ graphStore.selectedNode.outgoing_edges.length }})
                </p>
                <div class="space-y-1">
                  <div
                    v-for="e in graphStore.selectedNode.outgoing_edges.slice(0, 8)"
                    :key="e.target_node_id"
                    class="flex items-center gap-1.5 text-xs"
                  >
                    <BaseBadge :label="e.edge_type" color="teal" />
                    <span class="font-mono truncate" style="color: var(--color-text-secondary)" :title="e.target_qualified_name">
                      {{ shortName(e.target_qualified_name) }}
                    </span>
                  </div>
                  <p
                    v-if="graphStore.selectedNode.outgoing_edges.length > 8"
                    class="text-xs"
                    style="color: var(--color-text-muted)"
                  >
                    +{{ graphStore.selectedNode.outgoing_edges.length - 8 }} more
                  </p>
                </div>
              </div>
            </div>
          </aside>
        </Transition>
      </div>

      <!-- Legend bar (bottom) -->
      <div
        class="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2 border-t flex-shrink-0"
        :style="{
          background: 'var(--color-card)',
          borderColor: 'var(--color-border)',
        }"
      >
        <p class="text-xs font-medium mr-2" style="color: var(--color-text-muted)">Legend:</p>
        <div
          v-for="item in LEGEND"
          :key="item.label"
          class="flex items-center gap-1.5 text-xs"
          style="color: var(--color-text-muted)"
        >
          <span class="w-2.5 h-2.5 rounded-full" :style="{ background: item.color }" />
          {{ item.label }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import UCGGraph from '@/components/graph/UCGGraph.vue'
import GraphControls from '@/components/graph/GraphControls.vue'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import { useGraphStore } from '@/stores/graph'
import type { NodeType } from '@/types'

const route = useRoute()
const graphStore = useGraphStore()
const jobId = route.params.jobId as string

const graphRef = ref<InstanceType<typeof UCGGraph> | null>(null)

onMounted(async () => {
  await Promise.all([
    graphStore.fetchGraph(jobId),
    graphStore.fetchMetrics(jobId).catch(() => {}),
  ])
})

function onNodeClick(nodeId: string): void {
  graphStore.fetchNodeDetail(jobId, nodeId).catch(() => {})
}

function closeNodeDetail(): void {
  graphStore.selectNode(null)
}

function doExportPng(): void {
  const dataUrl = graphRef.value?.exportPng()
  if (!dataUrl) return
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = `ucg-${jobId.slice(0, 8)}.png`
  a.click()
}

function onRelayout(name: string): void {
  // Expose relayout through store or directly if needed
  // For now just refit
  graphRef.value?.fitGraph()
}

// ── Node colors ──────────────────────────────────────────────────────────────
const NODE_COLORS: Partial<Record<NodeType, string>> = {
  CLASS:     '#6366f1',
  INTERFACE: '#6366f1',
  METHOD:    '#22c55e',
  FUNCTION:  '#22c55e',
  FILE:      '#a855f7',
  MODULE:    '#a855f7',
  FIELD:     '#f97316',
  VARIABLE:  '#f97316',
  IMPORT:    '#9ca3af',
}

function nodeTypeColor(type: NodeType): string {
  return NODE_COLORS[type] ?? '#6b7280'
}

function shortName(qn: string): string {
  return qn.split('.').pop() ?? qn
}

const nodeProperties = computed(() => {
  const props = graphStore.selectedNode?.node.properties ?? {}
  return Object.entries(props).filter(([, v]) => v !== null).slice(0, 10)
})

const detectedLanguages = computed(() => {
  const langs = new Set(graphStore.nodes.map((n) => n.language))
  return [...langs]
})

const LEGEND = [
  { label: 'Class / Interface', color: '#6366f1' },
  { label: 'Method / Function',  color: '#22c55e' },
  { label: 'File / Module',      color: '#a855f7' },
  { label: 'Field / Variable',   color: '#f97316' },
  { label: 'Import',             color: '#9ca3af' },
  { label: 'Annotation',         color: '#14b8a6' },
]
</script>

<style scoped>
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
