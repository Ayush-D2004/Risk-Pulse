import type {
  PortfolioOverviewResponse,
  EventStressOverviewResponse,
  RiskAttributionResponse,
  ScenarioComparisonResponse,
} from '../types/api';

const API_BASE_URL = 'http://localhost:8000/api';

export const fetchPortfolio = async (): Promise<PortfolioOverviewResponse> => {
  const res = await fetch(`${API_BASE_URL}/portfolio`);
  if (!res.ok) throw new Error('Failed to fetch portfolio');
  return res.json();
};

export const fetchEvents = async (): Promise<{ event_id: string; type: string; impact: number }[]> => {
  const res = await fetch(`${API_BASE_URL}/events`);
  if (!res.ok) throw new Error('Failed to fetch events');
  return res.json();
};

export const fetchScenarioOverview = async (eventId: string): Promise<EventStressOverviewResponse> => {
  const res = await fetch(`${API_BASE_URL}/scenarios/${eventId}`);
  if (!res.ok) throw new Error('Failed to fetch scenario overview');
  return res.json();
};

export const fetchScenarioAttribution = async (eventId: string): Promise<RiskAttributionResponse> => {
  const res = await fetch(`${API_BASE_URL}/scenarios/${eventId}/attribution`);
  if (!res.ok) throw new Error('Failed to fetch scenario attribution');
  return res.json();
};

export const fetchScenarioComparison = async (eventA: string, eventB: string): Promise<ScenarioComparisonResponse> => {
  const res = await fetch(`${API_BASE_URL}/compare/${eventA}/${eventB}`);
  if (!res.ok) throw new Error('Failed to fetch scenario comparison');
  return res.json();
};
