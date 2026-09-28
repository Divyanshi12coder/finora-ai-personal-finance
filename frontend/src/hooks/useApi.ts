import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '@/api'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: ApiError | null
}

/**
 * Run an API call and expose loading / error / data plus a retry.
 *
 * Every API-backed view in Finora needs the same four states (loading, error
 * with retry, empty, loaded), so they are produced here once rather than being
 * re-implemented per page. In-flight requests are aborted on unmount and when
 * dependencies change, which prevents a slow response overwriting a newer one.
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
  options: { enabled?: boolean; initialData?: T | null } = {},
) {
  const { enabled = true, initialData = null } = options

  const [state, setState] = useState<AsyncState<T>>({
    data: initialData,
    loading: enabled,
    error: null,
  })

  // Keep the latest fetcher without making it a dependency, so callers can pass
  // an inline arrow function without causing an infinite refetch loop.
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const controllerRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      controllerRef.current?.abort()
    }
  }, [])

  const run = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setState((previous) => ({ ...previous, loading: true, error: null }))

    try {
      const data = await fetcherRef.current(controller.signal)
      if (!mountedRef.current || controller.signal.aborted) return
      setState({ data, loading: false, error: null })
    } catch (error) {
      if (!mountedRef.current || controller.signal.aborted) return
      if ((error as Error)?.name === 'AbortError') return
      setState({
        data: null,
        loading: false,
        error:
          error instanceof ApiError
            ? error
            : new ApiError('Something went wrong loading this data.', 0),
      })
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      setState((previous) => ({ ...previous, loading: false }))
      return
    }
    void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, ...deps])

  /** Update cached data locally after a mutation, avoiding a full refetch. */
  const setData = useCallback((updater: T | ((previous: T | null) => T | null)) => {
    setState((previous) => ({
      ...previous,
      data:
        typeof updater === 'function'
          ? (updater as (p: T | null) => T | null)(previous.data)
          : updater,
    }))
  }, [])

  return { ...state, refetch: run, setData }
}

/**
 * Wrap a mutating call (create/update/delete) with pending + error state.
 * Returns the result so callers can chain, and re-throws so a caller can
 * still react to failure.
 */
export function useMutation<TArgs extends unknown[], TResult>(
  mutator: (...args: TArgs) => Promise<TResult>,
) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const mutate = useCallback(
    async (...args: TArgs): Promise<TResult> => {
      setPending(true)
      setError(null)
      try {
        const result = await mutator(...args)
        if (mountedRef.current) setPending(false)
        return result
      } catch (caught) {
        const apiError =
          caught instanceof ApiError
            ? caught
            : new ApiError('Something went wrong. Please try again.', 0)
        if (mountedRef.current) {
          setError(apiError)
          setPending(false)
        }
        throw apiError
      }
    },
    [mutator],
  )

  return { mutate, pending, error, reset: () => setError(null) }
}
