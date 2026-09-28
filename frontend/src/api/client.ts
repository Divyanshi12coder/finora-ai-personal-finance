/**
 * The single HTTP client for the whole app.
 *
 * Nothing else in the frontend calls `fetch` directly. Centralising it means
 * auth headers, error shapes, timeouts and the 401 handler exist in exactly one
 * place — and it keeps the rule that the frontend talks only to the API, never
 * to a database and never to a third-party service holding a secret.
 */

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'
const TOKEN_KEY = 'finora.token'
const DEFAULT_TIMEOUT_MS = 30_000

export class ApiError extends Error {
  readonly status: number
  /** Field-level validation errors from FastAPI, keyed by field name. */
  readonly fieldErrors: Record<string, string>
  readonly isNetworkError: boolean

  constructor(
    message: string,
    status: number,
    fieldErrors: Record<string, string> = {},
    isNetworkError = false,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fieldErrors = fieldErrors
    this.isNetworkError = isNetworkError
  }

  get isUnauthorized() {
    return this.status === 401
  }

  get isValidation() {
    return this.status === 422
  }
}

// --- Token storage ----------------------------------------------------------
// localStorage is used rather than a cookie because the API is stateless and
// token-based; the token is short-lived and carries no financial data itself.
export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(token: string) {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      /* private browsing: the session simply won't persist across reloads */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
}

/** Called when the API rejects our token, so the app can route to /login. */
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
  timeoutMs?: number
  /** Set for multipart uploads, where the browser must set Content-Type. */
  formData?: FormData
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${BASE_URL}${path}`
  if (!query) return url

  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.append(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

function extractFieldErrors(payload: unknown): Record<string, string> {
  const errors: Record<string, string> = {}
  if (
    payload &&
    typeof payload === 'object' &&
    'errors' in payload &&
    Array.isArray((payload as { errors: unknown }).errors)
  ) {
    for (const entry of (payload as { errors: { field?: string; message?: string }[] }).errors) {
      if (entry.field && entry.message && !errors[entry.field]) {
        errors[entry.field] = entry.message
      }
    }
  }
  return errors
}

function extractMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string }
      if (first?.msg) return first.msg
    }
  }
  if (status === 401) return 'Your session has expired. Please log in again.'
  if (status === 403) return 'You do not have permission to do that.'
  if (status === 404) return 'That item could not be found.'
  if (status === 429) return 'Too many requests. Please slow down.'
  if (status >= 500) return 'The server had a problem. Please try again shortly.'
  return 'Something went wrong.'
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal, timeoutMs = DEFAULT_TIMEOUT_MS, formData } = options

  const headers: Record<string, string> = { Accept: 'application/json' }
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined && !formData) headers['Content-Type'] = 'application/json'

  // Combine the caller's abort signal with our own timeout.
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal: controller.signal,
    })
  } catch (error) {
    clearTimeout(timeout)
    if (signal?.aborted) throw error // a deliberate cancellation, not a failure
    const aborted = (error as Error)?.name === 'AbortError'
    throw new ApiError(
      aborted
        ? 'The request timed out. Check that the backend is running.'
        : 'Could not reach the server. Check your connection and that the backend is running.',
      0,
      {},
      true,
    )
  } finally {
    clearTimeout(timeout)
  }

  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : await response.text().catch(() => null)

  if (!response.ok) {
    if (response.status === 401) {
      tokenStore.clear()
      onUnauthorized?.()
    }
    throw new ApiError(
      extractMessage(payload, response.status),
      response.status,
      extractFieldErrors(payload),
    )
  }

  return payload as T
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal) =>
    request<T>(path, { method: 'GET', query, signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', body, signal }),
  put: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'PUT', body, signal }),
  patch: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'PATCH', body, signal }),
  delete: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { method: 'DELETE', signal }),
  upload: <T>(path: string, formData: FormData, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', formData, signal, timeoutMs: 60_000 }),
}

/** Absolute URL for an authenticated binary resource (e.g. a receipt image). */
export function resourceUrl(path: string): string {
  return path.startsWith('http') ? path : `${BASE_URL.replace(/\/api$/, '')}${path}`
}
