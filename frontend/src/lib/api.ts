import type {
  EventsResponse,
  PortfolioOverviewResponse,
  RiskAttributionResponse,
  ScenarioComparisonResponse,
  EventStressOverviewResponse,
  EventSummary,
} from '../types/api'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api'

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`Request failed with ${response.status}`)
  return response.json() as Promise<T>
}

export const fetchPortfolio = (signal?: AbortSignal) => fetchJson<PortfolioOverviewResponse>('/portfolio', signal)
export const fetchEvents = (signal?: AbortSignal) => fetchJson<EventsResponse | EventSummary[]>('/events', signal)
export const fetchScenarioOverview = (eventId: string, signal?: AbortSignal) => fetchJson<EventStressOverviewResponse>(`/scenarios/${encodeURIComponent(eventId)}`, signal)
export const fetchScenarioAttribution = (eventId: string, signal?: AbortSignal) => fetchJson<RiskAttributionResponse>(`/scenarios/${encodeURIComponent(eventId)}/attribution`, signal)
export const fetchScenarioComparison = (eventA: string, eventB: string, signal?: AbortSignal) => fetchJson<ScenarioComparisonResponse>(`/compare/${encodeURIComponent(eventA)}/${encodeURIComponent(eventB)}`, signal)

export function unwrapEvents(payload: EventsResponse | EventSummary[]): EventSummary[] {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload.data)) return payload.data
  return payload.data.events
}

export function unwrapData<T>(payload: { data: T }): T {
  return payload.data
}
