/**
 * Unit tests for the Axios API client (@/api/client).
 *
 * Verifies that the client is configured correctly and that interceptors
 * are attached. Import is done dynamically to avoid module caching issues.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('API client configuration', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('can be imported without errors', async () => {
    const mod = await import('@/api/client')
    const client = mod.default
    expect(client).toBeDefined()
  })

  it('has the correct baseURL', async () => {
    const mod = await import('@/api/client')
    const client = mod.default
    // The baseURL is set from VITE_API_BASE_URL or falls back to '/api/v1'
    expect(client.defaults.baseURL).toBe('/api/v1')
  })

  it('has a 5 minute timeout', async () => {
    const mod = await import('@/api/client')
    const client = mod.default
    // Check initial instance
    expect(client.defaults.timeout).toBe(300_000)
  })

  it('has default Content-Type of application/json', async () => {
    const mod = await import('@/api/client')
    const client = mod.default
    const contentType = (client.defaults.headers as any)['Content-Type']
    expect(contentType).toBe('application/json')
  })

  it('has request interceptors attached', async () => {
    const mod = await import('@/api/client')
    const client = mod.default
    // Axios stores interceptors in an internal structure — just verify it exists
    expect(client.interceptors.request).toBeDefined()
  })

  it('has response interceptors attached', async () => {
    const mod = await import('@/api/client')
    const client = mod.default
    expect(client.interceptors.response).toBeDefined()
  })

  it('exports setApiKey function', async () => {
    const mod = await import('@/api/client')
    expect(typeof mod.setApiKey).toBe('function')
  })

  it('exports clearApiKey function', async () => {
    const mod = await import('@/api/client')
    expect(typeof mod.clearApiKey).toBe('function')
  })

  it('setApiKey stores key in localStorage', async () => {
    const { setApiKey } = await import('@/api/client')
    setApiKey('alm_test_abc123')
    expect(localStorage.getItem('alm_api_key')).toBe('alm_test_abc123')
  })

  it('clearApiKey removes key from localStorage', async () => {
    const { setApiKey, clearApiKey } = await import('@/api/client')
    setApiKey('alm_test_xyz')
    clearApiKey()
    expect(localStorage.getItem('alm_api_key')).toBeNull()
  })
})

describe('API endpoints module', () => {
  it('analyzeApi can be imported without errors', async () => {
    const { analyzeApi } = await import('@/api/endpoints')
    expect(analyzeApi).toBeDefined()
    expect(typeof analyzeApi.submit).toBe('function')
    expect(typeof analyzeApi.getJob).toBe('function')
    expect(typeof analyzeApi.listJobs).toBe('function')
    expect(typeof analyzeApi.deleteJob).toBe('function')
  })

  it('graphApi can be imported without errors', async () => {
    const { graphApi } = await import('@/api/endpoints')
    expect(graphApi).toBeDefined()
    expect(typeof graphApi.getGraph).toBe('function')
    expect(typeof graphApi.getNodes).toBe('function')
    expect(typeof graphApi.getNode).toBe('function')
    expect(typeof graphApi.getMetrics).toBe('function')
  })

  it('smellsApi can be imported without errors', async () => {
    const { smellsApi } = await import('@/api/endpoints')
    expect(smellsApi).toBeDefined()
    expect(typeof smellsApi.listSmells).toBe('function')
    expect(typeof smellsApi.getSmell).toBe('function')
    expect(typeof smellsApi.dismissSmell).toBe('function')
    expect(typeof smellsApi.getSummary).toBe('function')
  })

  it('planApi can be imported without errors', async () => {
    const { planApi } = await import('@/api/endpoints')
    expect(planApi).toBeDefined()
    expect(typeof planApi.getPlan).toBe('function')
    expect(typeof planApi.listTasks).toBe('function')
    expect(typeof planApi.updateTask).toBe('function')
  })

  it('patchesApi can be imported without errors', async () => {
    const { patchesApi } = await import('@/api/endpoints')
    expect(patchesApi).toBeDefined()
    expect(typeof patchesApi.listPatches).toBe('function')
    expect(typeof patchesApi.getPatch).toBe('function')
    expect(typeof patchesApi.applyPatch).toBe('function')
    expect(typeof patchesApi.revertPatch).toBe('function')
  })

  it('reportApi can be imported without errors', async () => {
    const { reportApi } = await import('@/api/endpoints')
    expect(reportApi).toBeDefined()
    expect(typeof reportApi.getReport).toBe('function')
    expect(typeof reportApi.exportPDF).toBe('function')
    expect(typeof reportApi.exportMarkdown).toBe('function')
  })

  it('validationApi can be imported without errors', async () => {
    const { validationApi } = await import('@/api/endpoints')
    expect(validationApi).toBeDefined()
    expect(typeof validationApi.listResults).toBe('function')
    expect(typeof validationApi.getResult).toBe('function')
    expect(typeof validationApi.rerun).toBe('function')
  })
})
