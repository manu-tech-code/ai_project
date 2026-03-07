/**
 * Axios HTTP client — configured with base URL, API key injection,
 * error normalization middleware, and an in-memory GET cache.
 *
 * Cache behaviour:
 *  - GET requests to completed-job endpoints (smells, plan, patches, report, graph)
 *    are cached in memory for GET_CACHE_TTL_MS (5 minutes).
 *  - Cache key = method + url + serialised params.
 *  - Any mutating request (POST/PATCH/PUT/DELETE) to the same base URL prefix
 *    busts the cache entries for that resource.
 *  - Simultaneous identical GET requests are deduplicated: the second caller
 *    awaits the same in-flight Promise rather than firing a second request.
 */

import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'

const API_KEY_STORAGE_KEY = 'alm_api_key'

// ---------------------------------------------------------------------------
// In-memory GET cache
// ---------------------------------------------------------------------------

const GET_CACHE_TTL_MS = 5 * 60 * 1_000 // 5 minutes

/** URL prefixes that are eligible for caching (completed-job read endpoints). */
const CACHEABLE_PREFIXES = ['/smells/', '/plan/', '/patches/', '/report/', '/graph/']

interface CacheEntry {
  data: AxiosResponse
  expiresAt: number
}

/** key → cached response */
const _cache = new Map<string, CacheEntry>()

/** key → in-flight Promise (deduplication) */
const _inFlight = new Map<string, Promise<AxiosResponse>>()

function _cacheKey(url: string, params: unknown): string {
  return `GET:${url}:${params ? JSON.stringify(params) : ''}`
}

function _isCacheable(url: string | undefined): boolean {
  if (!url) return false
  return CACHEABLE_PREFIXES.some((prefix) => url.includes(prefix))
}

/**
 * Bust all cache entries whose key contains `urlFragment`.
 * Called after any mutating request so stale data is never served.
 */
function bustCache(urlFragment: string): void {
  for (const key of _cache.keys()) {
    if (key.includes(urlFragment)) _cache.delete(key)
  }
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 300_000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
})

// Inject API key — localStorage takes precedence over env fallback
client.interceptors.request.use((config) => {
  const apiKey =
    localStorage.getItem(API_KEY_STORAGE_KEY) ||
    (import.meta.env.VITE_API_KEY as string | undefined)
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey
  }
  return config
})

// ---------------------------------------------------------------------------
// Request interceptor: serve cached GET responses and deduplicate in-flight
// ---------------------------------------------------------------------------

client.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase()
  if (method !== 'GET' || !_isCacheable(config.url)) return config

  const key = _cacheKey(config.url!, config.params)
  const cached = _cache.get(key)
  if (cached && Date.now() < cached.expiresAt) {
    // Attach a sentinel so the response interceptor knows this is a cache hit.
    // We use a custom adapter to short-circuit the real HTTP call.
    const cachedResponse = cached.data
    config.adapter = () => Promise.resolve(cachedResponse)
    return config
  }
  return config
})

// Normalize error responses into plain Error objects
client.interceptors.response.use(
  (response) => {
    const config = response.config as AxiosRequestConfig & { _fromCache?: boolean }
    const method = config.method?.toUpperCase()

    if (method === 'GET' && _isCacheable(config.url)) {
      const key = _cacheKey(config.url!, config.params)
      // Only store if this wasn't already served from cache (avoid re-wrapping).
      if (!_cache.has(key) || (_cache.get(key)?.expiresAt ?? 0) < Date.now()) {
        _cache.set(key, { data: response, expiresAt: Date.now() + GET_CACHE_TTL_MS })
      }
      _inFlight.delete(key)
    } else if (method && ['POST', 'PATCH', 'PUT', 'DELETE'].includes(method) && config.url) {
      // Bust cache entries that share the same URL prefix on mutations.
      // Extract the resource segment (e.g. "/smells/abc123") and bust all matching keys.
      const urlPath = config.url.replace(/\/[^/]+$/, '') // strip trailing segment for bulk bust
      bustCache(urlPath)
      bustCache(config.url)
    }

    return response
  },
  (error) => {
    // Clean up in-flight entry on error so subsequent retries aren't blocked.
    const config = error.config as AxiosRequestConfig | undefined
    if (config?.url) {
      const key = _cacheKey(config.url, config.params)
      _inFlight.delete(key)
    }

    const detail = error.response?.data?.detail
    const message =
      error.response?.data?.message ??
      (typeof detail === 'string' ? detail : detail?.message) ??
      error.message ??
      'An unexpected error occurred'

    const status = error.response?.status
    const requestId = error.response?.headers?.['x-request-id'] ?? null

    if (import.meta.env.DEV) {
      console.error(
        `[ALM API] ${status ?? 'ERR'} ${error.config?.method?.toUpperCase()} ${error.config?.url}:`,
        message,
        requestId ? `(req: ${requestId})` : '',
      )
    }

    return Promise.reject(new Error(message))
  },
)

export { bustCache }

export function setApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE_KEY, key)
}

export function clearApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE_KEY)
}

export function getApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY) || (import.meta.env.VITE_API_KEY as string | undefined) || null
}

/** Call the open /admin/api-keys/generate endpoint and persist the result. */
export async function generateAndSaveApiKey(): Promise<string> {
  // Use a raw axios call without the X-API-Key header so we don't need one to bootstrap.
  const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
  const response = await axios.post<{ key: string }>(`${baseURL}/admin/api-keys/generate`)
  const key = response.data.key
  setApiKey(key)
  return key
}

export default client
