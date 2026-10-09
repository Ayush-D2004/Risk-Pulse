import { useState, useEffect, useCallback } from 'react'
import type { PipelineRun } from '../types/api'
import { fetchPipelineRun, getPipelineStreamUrl } from '../lib/api'

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'terminal'

export interface PipelineStreamState {
  run: PipelineRun | null
  loading: boolean
  connectionState: ConnectionState
  error: Error | null
  retry: () => void
}

export function usePipelineStream(runId: string | null): PipelineStreamState {
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [loading, setLoading] = useState(false)
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting')
  const [error, setError] = useState<Error | null>(null)
  const [revision, setRevision] = useState(0)

  const retry = useCallback(() => setRevision((r) => r + 1), [])

  useEffect(() => {
    if (!runId) {
      setRun(null)
      setLoading(false)
      setError(null)
      return
    }

    let eventSource: EventSource | null = null
    const abortController = new AbortController()

    setLoading(true)
    setError(null)
    setConnectionState('connecting')

    fetchPipelineRun(runId, abortController.signal)
      .then((initialRun) => {
        if (abortController.signal.aborted) return

        setRun(initialRun)

        if (initialRun.status === 'COMPLETED' || initialRun.status === 'FAILED') {
          setLoading(false)
          setConnectionState('terminal')
          return
        }

        // Run is still active, start SSE stream
        eventSource = new EventSource(getPipelineStreamUrl(runId))

        eventSource.onopen = () => {
          setLoading(false)
          setConnectionState('connected')
        }

        eventSource.onerror = () => {
          // Browser will automatically attempt to reconnect
          setConnectionState('reconnecting')
        }

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)

            // Validate minimum required structure before accepting state
            if (
              data &&
              typeof data === 'object' &&
              data.run_id === runId &&
              data.status &&
              Array.isArray(data.stages)
            ) {
              setRun(data as PipelineRun)

              if (data.status === 'COMPLETED' || data.status === 'FAILED') {
                setConnectionState('terminal')
                eventSource?.close()
              }
            }
          } catch (e) {
            // Ignore malformed JSON and allow stream to continue
            console.warn('Pipeline SSE: Received malformed data', e)
          }
        }
      })
      .catch((err) => {
        if (abortController.signal.aborted) return
        setLoading(false)
        setConnectionState('terminal')
        setError(err instanceof Error ? err : new Error('Unknown error fetching run'))
      })

    return () => {
      abortController.abort()
      if (eventSource) {
        eventSource.close()
      }
    }
  }, [runId, revision])

  return { run, loading, connectionState, error, retry }
}
