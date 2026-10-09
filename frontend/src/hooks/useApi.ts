import { useCallback, useEffect, useRef, useState } from 'react'

type QueryState<T> = {
  data: T | null
  loading: boolean
  error: Error | null
  reload: () => void
  updatedAt: Date | null
}

export function useApiQuery<T>(queryKey: string, request: (signal: AbortSignal) => Promise<T>, enabled = true): QueryState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [revision, setRevision] = useState(0)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const latestKey = useRef(queryKey)

  const reload = useCallback(() => setRevision((value) => value + 1), [])

  useEffect(() => {
    latestKey.current = queryKey
    if (!enabled) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    request(controller.signal)
      .then((result) => {
        if (latestKey.current === queryKey) {
          setData(result)
          setUpdatedAt(new Date())
        }
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        if (latestKey.current === queryKey) setError(reason instanceof Error ? reason : new Error('Unknown request error'))
      })
      .finally(() => {
        if (!controller.signal.aborted && latestKey.current === queryKey) setLoading(false)
      })
    return () => controller.abort()
  }, [enabled, queryKey, request, revision])

  return { data, loading, error, reload, updatedAt }
}
