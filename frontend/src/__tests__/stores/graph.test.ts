/**
 * Unit tests for the graph Pinia store.
 *
 * The graphApi is fully mocked. Tests verify state management,
 * cytoscapeElements computed property, and filtering logic.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGraphStore } from '@/stores/graph'
import type { UCGNode, UCGEdge } from '@/types'

// ---------------------------------------------------------------------------
// Mock the API layer
// ---------------------------------------------------------------------------

vi.mock('@/api/endpoints', () => ({
  graphApi: {
    getGraph: vi.fn(),
    getNodes: vi.fn(),
    getNode: vi.fn(),
    getEdges: vi.fn(),
    getMetrics: vi.fn(),
    getSubgraph: vi.fn(),
  },
}))

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeNode(overrides: Partial<UCGNode> = {}): UCGNode {
  return {
    id: 'node-1',
    node_type: 'CLASS',
    qualified_name: 'com.example.OrderService',
    language: 'java',
    file_path: 'src/OrderService.java',
    line_start: 1,
    line_end: 100,
    col_start: null,
    col_end: null,
    properties: {},
    ...overrides,
  }
}

function makeEdge(overrides: Partial<UCGEdge> = {}): UCGEdge {
  return {
    id: 'edge-1',
    edge_type: 'CALLS',
    source_node_id: 'node-1',
    target_node_id: 'node-2',
    weight: 1.0,
    properties: {},
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useGraphStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // --- Initial state ---

  it('initializes with empty nodes array', () => {
    const store = useGraphStore()
    expect(store.nodes).toEqual([])
  })

  it('initializes with empty edges array', () => {
    const store = useGraphStore()
    expect(store.edges).toEqual([])
  })

  it('initializes with null metrics', () => {
    const store = useGraphStore()
    expect(store.metrics).toBeNull()
  })

  it('initializes with null selectedNodeId', () => {
    const store = useGraphStore()
    expect(store.selectedNodeId).toBeNull()
  })

  it('initializes with null selectedNode', () => {
    const store = useGraphStore()
    expect(store.selectedNode).toBeNull()
  })

  it('initializes with isLoading false', () => {
    const store = useGraphStore()
    expect(store.isLoading).toBe(false)
  })

  it('initializes with null error', () => {
    const store = useGraphStore()
    expect(store.error).toBeNull()
  })

  it('initializes with hasData false', () => {
    const store = useGraphStore()
    expect(store.hasData).toBe(false)
  })

  // --- cytoscapeElements when empty ---

  it('cytoscapeElements returns empty array when no data', () => {
    const store = useGraphStore()
    expect(store.cytoscapeElements).toEqual([])
  })

  // --- cytoscapeElements with data ---

  it('cytoscapeElements returns node elements', () => {
    const store = useGraphStore()
    store.nodes = [makeNode({ id: 'n1', qualified_name: 'com.example.OrderService' })]

    const elements = store.cytoscapeElements
    const nodeElements = elements.filter((e) => e.group === 'nodes')
    expect(nodeElements).toHaveLength(1)
  })

  it('cytoscapeElements maps node id correctly', () => {
    const store = useGraphStore()
    store.nodes = [makeNode({ id: 'node-abc' })]

    const elements = store.cytoscapeElements
    const nodeEl = elements.find((e) => e.group === 'nodes')
    expect(nodeEl?.data.id).toBe('node-abc')
  })

  it('cytoscapeElements uses last segment of qualified_name as label', () => {
    const store = useGraphStore()
    store.nodes = [makeNode({ id: 'n1', qualified_name: 'com.example.OrderService' })]

    const elements = store.cytoscapeElements
    const nodeEl = elements.find((e) => e.group === 'nodes')
    expect(nodeEl?.data.label).toBe('OrderService')
  })

  it('cytoscapeElements includes node_type in data', () => {
    const store = useGraphStore()
    store.nodes = [makeNode({ id: 'n1', node_type: 'METHOD' })]

    const elements = store.cytoscapeElements
    const nodeEl = elements.find((e) => e.group === 'nodes')
    expect(nodeEl?.data.node_type).toBe('METHOD')
  })

  it('cytoscapeElements includes language in node data', () => {
    const store = useGraphStore()
    store.nodes = [makeNode({ id: 'n1', language: 'python' })]

    const elements = store.cytoscapeElements
    const nodeEl = elements.find((e) => e.group === 'nodes')
    expect(nodeEl?.data.language).toBe('python')
  })

  it('cytoscapeElements computes lines correctly', () => {
    const store = useGraphStore()
    store.nodes = [makeNode({ id: 'n1', line_start: 10, line_end: 60 })]

    const elements = store.cytoscapeElements
    const nodeEl = elements.find((e) => e.group === 'nodes')
    expect(nodeEl?.data.lines).toBe(50)
  })

  it('cytoscapeElements returns edge elements for connected nodes', () => {
    const store = useGraphStore()
    store.nodes = [
      makeNode({ id: 'n1' }),
      makeNode({ id: 'n2', qualified_name: 'com.example.UserService' }),
    ]
    store.edges = [makeEdge({ id: 'e1', source_node_id: 'n1', target_node_id: 'n2' })]

    const elements = store.cytoscapeElements
    const edgeElements = elements.filter((e) => e.group === 'edges')
    expect(edgeElements).toHaveLength(1)
    expect(edgeElements[0].data.id).toBe('e1')
    expect(edgeElements[0].data.source).toBe('n1')
    expect(edgeElements[0].data.target).toBe('n2')
  })

  it('cytoscapeElements excludes edges with nodes not in filtered set', () => {
    const store = useGraphStore()
    // Only n1 is in nodes; edge references n1 -> n3 (not present)
    store.nodes = [makeNode({ id: 'n1' })]
    store.edges = [makeEdge({ id: 'e1', source_node_id: 'n1', target_node_id: 'n3' })]

    const elements = store.cytoscapeElements
    const edgeElements = elements.filter((e) => e.group === 'edges')
    expect(edgeElements).toHaveLength(0)
  })

  // --- filteredNodes ---

  it('filteredNodes returns all nodes when no filters active', () => {
    const store = useGraphStore()
    store.nodes = [
      makeNode({ id: 'n1', node_type: 'CLASS' }),
      makeNode({ id: 'n2', node_type: 'METHOD' }),
    ]

    expect(store.filteredNodes).toHaveLength(2)
  })

  it('filteredNodes filters by nodeType', () => {
    const store = useGraphStore()
    store.nodes = [
      makeNode({ id: 'n1', node_type: 'CLASS' }),
      makeNode({ id: 'n2', node_type: 'METHOD' }),
    ]
    store.filters.nodeTypes = ['CLASS']

    expect(store.filteredNodes).toHaveLength(1)
    expect(store.filteredNodes[0].node_type).toBe('CLASS')
  })

  it('filteredNodes filters by language', () => {
    const store = useGraphStore()
    store.nodes = [
      makeNode({ id: 'n1', language: 'java' }),
      makeNode({ id: 'n2', language: 'python' }),
    ]
    store.filters.languages = ['python']

    expect(store.filteredNodes).toHaveLength(1)
    expect(store.filteredNodes[0].language).toBe('python')
  })

  it('filteredNodes filters by searchQuery (case insensitive)', () => {
    const store = useGraphStore()
    store.nodes = [
      makeNode({ id: 'n1', qualified_name: 'com.example.OrderService' }),
      makeNode({ id: 'n2', qualified_name: 'com.example.UserController' }),
    ]
    store.filters.searchQuery = 'order'

    expect(store.filteredNodes).toHaveLength(1)
    expect(store.filteredNodes[0].id).toBe('n1')
  })

  it('filteredNodes with searchQuery is case insensitive', () => {
    const store = useGraphStore()
    store.nodes = [
      makeNode({ id: 'n1', qualified_name: 'com.example.OrderService' }),
    ]
    store.filters.searchQuery = 'ORDERSERVICE'

    expect(store.filteredNodes).toHaveLength(1)
  })

  it('filteredNodes returns empty when no match', () => {
    const store = useGraphStore()
    store.nodes = [
      makeNode({ id: 'n1', qualified_name: 'com.example.OrderService' }),
    ]
    store.filters.searchQuery = 'zzz-no-match'

    expect(store.filteredNodes).toHaveLength(0)
  })

  // --- hasData ---

  it('hasData is true when nodes are present', () => {
    const store = useGraphStore()
    store.nodes = [makeNode()]
    expect(store.hasData).toBe(true)
  })

  it('hasData is false when nodes are empty', () => {
    const store = useGraphStore()
    store.nodes = []
    expect(store.hasData).toBe(false)
  })

  // --- selectNode action ---

  it('selectNode sets selectedNodeId', () => {
    const store = useGraphStore()
    store.selectNode('node-abc')
    expect(store.selectedNodeId).toBe('node-abc')
  })

  it('selectNode with null clears selectedNode', () => {
    const store = useGraphStore()
    store.selectedNode = { node: makeNode(), incoming_edges: [], outgoing_edges: [] }
    store.selectNode(null)
    expect(store.selectedNode).toBeNull()
    expect(store.selectedNodeId).toBeNull()
  })

  // --- setFilter action ---

  it('setFilter merges partial filter update', () => {
    const store = useGraphStore()
    store.setFilter({ searchQuery: 'test' })
    expect(store.filters.searchQuery).toBe('test')
    // Other filters should remain at defaults
    expect(store.filters.nodeTypes).toEqual([])
  })

  it('setFilter can update nodeTypes', () => {
    const store = useGraphStore()
    store.setFilter({ nodeTypes: ['CLASS', 'METHOD'] })
    expect(store.filters.nodeTypes).toEqual(['CLASS', 'METHOD'])
  })

  // --- resetFilters action ---

  it('resetFilters clears all filters', () => {
    const store = useGraphStore()
    store.setFilter({ searchQuery: 'test', nodeTypes: ['CLASS'] })
    store.resetFilters()

    expect(store.filters.nodeTypes).toEqual([])
    expect(store.filters.languages).toEqual([])
    expect(store.filters.searchQuery).toBe('')
    expect(store.filters.showOrphans).toBe(true)
  })

  // --- fetchGraph action ---

  it('fetchGraph populates nodes and edges', async () => {
    const { graphApi } = await import('@/api/endpoints')
    const mockNodes = [makeNode({ id: 'n1' })]
    const mockEdges = [makeEdge({ id: 'e1' })]

    vi.mocked(graphApi.getGraph).mockResolvedValueOnce({
      data: {
        job_id: 'job-1',
        nodes: mockNodes,
        edges: mockEdges,
        pagination: { page: 1, page_size: 100, total_items: 1, total_pages: 1, has_next: false, has_prev: false },
      },
    } as any)

    const store = useGraphStore()
    await store.fetchGraph('job-1')

    expect(store.nodes).toHaveLength(1)
    expect(store.edges).toHaveLength(1)
    expect(store.isLoading).toBe(false)
  })

  it('fetchGraph sets error on failure', async () => {
    const { graphApi } = await import('@/api/endpoints')
    vi.mocked(graphApi.getGraph).mockRejectedValueOnce(new Error('Graph fetch failed'))

    const store = useGraphStore()
    await store.fetchGraph('job-fail')

    expect(store.error).toContain('Graph fetch failed')
    expect(store.isLoading).toBe(false)
  })
})
