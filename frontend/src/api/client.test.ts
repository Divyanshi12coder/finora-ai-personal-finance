import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, request, setUnauthorizedHandler, tokenStore } from './client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('api client', () => {
  beforeEach(() => {
    tokenStore.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('attaches the bearer token when one is stored', async () => {
    tokenStore.set('test-token')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await request('/transactions')

    const headers = fetchMock.mock.calls[0][1].headers
    expect(headers.Authorization).toBe('Bearer test-token')
  })

  it('omits the auth header when there is no token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await request('/health')

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })

  it('builds a query string and drops empty values', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await request('/transactions', {
      query: { page: 1, search: '', type: 'expense', category_id: undefined },
    })

    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('page=1')
    expect(url).toContain('type=expense')
    expect(url).not.toContain('search=')
    expect(url).not.toContain('category_id')
  })

  it('throws a typed ApiError carrying the server message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Category not found' }, 404)),
    )

    await expect(request('/categories/xyz')).rejects.toMatchObject({
      status: 404,
      message: 'Category not found',
    })
  })

  it('extracts field-level validation errors for inline display', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: 'Validation failed',
            errors: [
              { field: 'amount', message: 'Input should be greater than 0', type: 'value_error' },
              { field: 'email', message: 'not a valid email', type: 'value_error' },
            ],
          },
          422,
        ),
      ),
    )

    try {
      await request('/transactions', { method: 'POST', body: {} })
      expect.unreachable('should have thrown')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      const apiError = error as ApiError
      expect(apiError.isValidation).toBe(true)
      expect(apiError.fieldErrors.amount).toBe('Input should be greater than 0')
      expect(apiError.fieldErrors.email).toBe('not a valid email')
    }
  })

  it('clears the token and notifies on 401', async () => {
    tokenStore.set('expired-token')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ detail: 'Not authenticated' }, 401)),
    )

    await expect(request('/dashboard')).rejects.toThrow()
    expect(tokenStore.get()).toBeNull()
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('reports a network failure distinctly from an HTTP error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    try {
      await request('/health')
      expect.unreachable('should have thrown')
    } catch (error) {
      const apiError = error as ApiError
      expect(apiError.isNetworkError).toBe(true)
      expect(apiError.status).toBe(0)
      expect(apiError.message).toMatch(/could not reach the server/i)
    }
  })

  it('falls back to a friendly message when the server sends no detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 500)))

    await expect(request('/dashboard')).rejects.toMatchObject({
      message: expect.stringMatching(/server had a problem/i),
    })
  })

  it('handles a 204 with no body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request('/transactions/abc')).resolves.toBeUndefined()
  })
})
