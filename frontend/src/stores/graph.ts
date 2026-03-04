/**
 * Graph Pinia store.
 *
 * Manages UCG graph data and Cytoscape.js element state.
 * See docs/frontend-spec.md section 3.2 for the full store definition.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { graphApi } from '@/api/endpoints'
import type {
  CytoscapeElement,
  GraphMetrics,
  NodeType,
  UCGEdge,
  UCGNode,
  UCGNodeDetail,
} from '@/types'

interface GraphFilters {
  nodeTypes: NodeType[]
  languages: string[]
  searchQuery: string
  showOrphans: boolean
}

export const useGraphStore = defineStore('graph', () => {
  // --- State ---
  const nodes = ref<UCGNode[]>([])
  const edges = ref<UCGEdge[]>([])
  const metrics = ref<GraphMetrics | null>(null)
  const selectedNodeId = ref<string | null>(null)
  const selectedNode = ref<UCGNodeDetail | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const filters = ref<GraphFilters>({
    nodeTypes: [],
    languages: [],
    searchQuery: '',
    showOrphans: true,
  })

  // --- Getters ---

  /**
   * Transform nodes and edges into Cytoscape.js element format.
   * Node color and size are mapped from node_type and LOC.
   */
  const cytoscapeElements = computed<CytoscapeElement[]>(() => {
    const nodeElements = filteredNodes.value.map((n) => ({
      group: 'nodes' as const,
      data: {
        id: n.id,
        label: n.qualified_name.split('.').pop() ?? n.qualified_name,
        node_type: n.node_type,
        language: n.language,
        lines: (n.line_end ?? 0) - (n.line_start ?? 0),
        qualified_name: n.qualified_name,
      },
    }))

    const nodeIds = new Set(filteredNodes.value.map((n) => n.id))
    const edgeElements = edges.value
      .filter((e) => nodeIds.has(e.source_node_id) && nodeIds.has(e.target_node_id))
      .map((e) => ({
        group: 'edges' as const,
        data: {
          id: e.id,
          source: e.source_node_id,
          target: e.target_node_id,
          edge_type: e.edge_type,
          weight: e.weight,
        },
      }))

    return [...nodeElements, ...edgeElements]
  })

  const filteredNodes = computed(() => {
    return nodes.value.filter((n) => {
      if (filters.value.nodeTypes.length > 0 && !filters.value.nodeTypes.includes(n.node_type)) {
        return false
      }
      if (filters.value.languages.length > 0 && !filters.value.languages.includes(n.language as any)) {
        return false
      }
      if (
        filters.value.searchQuery &&
        !n.qualified_name.toLowerCase().includes(filters.value.searchQuery.toLowerCase())
      ) {
        return false
      }
      return true
    })
  })

  const hasData = computed(() => nodes.value.length > 0)

  // --- Actions ---
  async function fetchGraph(jobId: string, page = 1): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      // TODO: implement pagination, append vs replace
      const { data } = await graphApi.getGraph(jobId, { page, include_edges: true })
      nodes.value = data.nodes
      edges.value = data.edges
    } catch (err) {
      error.value = String(err)
    } finally {
      isLoading.value = false
    }
  }

  async function fetchNodeDetail(jobId: string, nodeId: string, depth = 1): Promise<void> {
    selectedNodeId.value = nodeId
    const { data } = await graphApi.getNode(jobId, nodeId, depth)
    selectedNode.value = data
  }

  async function fetchMetrics(jobId: string): Promise<void> {
    const { data } = await graphApi.getMetrics(jobId)
    metrics.value = data
  }

  function selectNode(nodeId: string | null): void {
    selectedNodeId.value = nodeId
    if (!nodeId) selectedNode.value = null
  }

  function setFilter(newFilter: Partial<GraphFilters>): void {
    filters.value = { ...filters.value, ...newFilter }
  }

  function resetFilters(): void {
    filters.value = { nodeTypes: [], languages: [], searchQuery: '', showOrphans: true }
  }

  return {
    nodes,
    edges,
    metrics,
    selectedNodeId,
    selectedNode,
    isLoading,
    error,
    filters,
    cytoscapeElements,
    filteredNodes,
    hasData,
    fetchGraph,
    fetchNodeDetail,
    fetchMetrics,
    selectNode,
    setFilter,
    resetFilters,
  }
})
