/**
 * Axios HTTP client — configured with base URL, API key injection,
 * and error normalization middleware.
 */

import axios, { type AxiosInstance } from 'axios'

const API_KEY_STORAGE_KEY = 'alm_api_key'

const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  timeout: 60_000,
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

// Normalize error responses into plain Error objects
client.interceptors.response.use(
  (response) => response,
  (error) => {
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
