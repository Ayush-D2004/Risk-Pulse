import type {
  EventsResponse,
  PortfolioOverviewResponse,
  RiskAttributionResponse,
  ScenarioComparisonResponse,
  EventStressOverviewResponse,
  EventSummary,
  AnalystSimulationRequest,
  RunSubmissionResponse,
  GDELTSearchRequest,
  GDELTSearchResponse,
  PipelineRun,
  PipelineRunsResponse,
  PromotedRunResponse,
} from '../types/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api'

export class ApiError extends Error {
  constructor(message: string, public status?: number, public data?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { Accept: 'application/json', ...options?.headers }
  })
  
  if (!response.ok) {
    let errorData
    try {
      errorData = await response.json()
    } catch {
      // Body is not valid JSON
    }
    const message = errorData?.detail || errorData?.error || `Request failed with ${response.status}`
    throw new ApiError(message, response.status, errorData)
  }
  
  return response.json() as Promise<T>
}

export const fetchPortfolio = (signal?: AbortSignal) => fetchJson<PortfolioOverviewResponse>('/portfolio', { signal })
export const fetchEvents = (signal?: AbortSignal) => fetchJson<EventsResponse | EventSummary[]>('/events', { signal })
export const fetchScenarioOverview = (eventId: string, signal?: AbortSignal) => fetchJson<EventStressOverviewResponse>(`/scenarios/${encodeURIComponent(eventId)}`, { signal })
export const fetchScenarioAttribution = (eventId: string, signal?: AbortSignal) => fetchJson<RiskAttributionResponse>(`/scenarios/${encodeURIComponent(eventId)}/attribution`, { signal })
export const fetchScenarioComparison = (eventA: string, eventB: string, signal?: AbortSignal) => fetchJson<ScenarioComparisonResponse>(`/compare/${encodeURIComponent(eventA)}/${encodeURIComponent(eventB)}`, { signal })

export const submitAnalystSimulation = (request: AnalystSimulationRequest, signal?: AbortSignal) =>
  fetchJson<RunSubmissionResponse>('/intelligence/simulate', {
    method: 'POST',
    body: JSON.stringify(request),
    signal,
    headers: { 'Content-Type': 'application/json' }
  })

export const submitGdeltSearch = (request: GDELTSearchRequest, signal?: AbortSignal) =>
  fetchJson<GDELTSearchResponse>('/intelligence/gdelt/search', {
    method: 'POST',
    body: JSON.stringify(request),
    signal,
    headers: { 'Content-Type': 'application/json' }
  })

export const fetchPipelineRun = (runId: string, signal?: AbortSignal) =>
  fetchJson<PipelineRun>(`/intelligence/runs/${encodeURIComponent(runId)}`, { signal })

export const fetchPipelineRuns = (signal?: AbortSignal) =>
  fetchJson<PipelineRunsResponse>('/intelligence/runs', { signal })

export const getPipelineStreamUrl = (runId: string) => `${API_BASE_URL}/intelligence/runs/${encodeURIComponent(runId)}/stream`

export function unwrapEvents(payload: EventsResponse | EventSummary[]): EventSummary[] {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload.data)) return payload.data
  return payload.data.events
}

export function unwrapData<T>(payload: { data: T }): T {
  return payload.data
}

export const promotePipelineRun = (runId: string, signal?: AbortSignal) =>
  fetchJson<PromotedRunResponse>(`/intelligence/runs/${encodeURIComponent(runId)}/promote`, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' }
  })

export const fetchHistoricalMarketData = (ticker: string, timestamp: string, timezone: string, signal?: AbortSignal) =>
  fetchJson<any>(`/market/historical?ticker=${encodeURIComponent(ticker)}&timestamp=${encodeURIComponent(timestamp)}&timezone=${encodeURIComponent(timezone)}`, { signal })
