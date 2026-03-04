/**
 * Global Vitest test setup.
 *
 * - Mocks DOM-dependent libraries (cytoscape, cytoscape-dagre) that can't
 *   run in jsdom.
 * - Mocks @vueuse/core's useStorage to avoid localStorage issues in tests.
 */

import { vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mock cytoscape — it requires a real canvas context unavailable in jsdom
// ---------------------------------------------------------------------------

vi.mock('cytoscape', () => ({
  default: vi.fn(() => ({
    add: vi.fn(),
    remove: vi.fn(),
    elements: vi.fn(() => ({
      remove: vi.fn(),
      forEach: vi.fn(),
    })),
    layout: vi.fn(() => ({ run: vi.fn(), stop: vi.fn() })),
    on: vi.fn(),
    off: vi.fn(),
    destroy: vi.fn(),
    fit: vi.fn(),
    zoom: vi.fn(),
    pan: vi.fn(),
    getElementById: vi.fn(() => ({
      select: vi.fn(),
      deselect: vi.fn(),
      data: vi.fn(() => ({})),
    })),
  })),
}))

vi.mock('cytoscape-dagre', () => ({
  default: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Mock @vueuse/core's useStorage to use a simple ref instead of localStorage
// ---------------------------------------------------------------------------

vi.mock('@vueuse/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@vueuse/core')>()
  const { ref } = await import('vue')
  return {
    ...actual,
    useStorage: vi.fn((_key: string, defaultValue: unknown) => ref(defaultValue)),
  }
})
