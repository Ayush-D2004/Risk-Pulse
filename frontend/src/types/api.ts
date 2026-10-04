export interface DashboardEnvelope {
  schema_version: string;
  generated_at: string;
  portfolio_id: string;
  event_id?: string | null;
  scenario_a_id?: string | null;
  scenario_b_id?: string | null;
}

export interface EadSlice {
  name: string;
  ead: string | number;
}

export interface ObligorConcentrationRow {
  obligor: string;
  ead: string | number;
  pct: number;
}

export interface PortfolioOverviewData {
  total_ead: string | number;
  exposure_count: number;
  obligor_count: number;
  sector_distribution: EadSlice[];
  geography_distribution: EadSlice[];
  rating_distribution: EadSlice[];
  top_obligors: ObligorConcentrationRow[];
  concentration_indicators: string[];
}

export interface PortfolioOverviewResponse extends DashboardEnvelope {
  data: PortfolioOverviewData;
}

export interface EventStressOverviewData {
  event_id: string;
  entity: string;
  event_type: string;
  sentiment: number;
  impact_score: number;
  impact_tier: string;
  shock_scope?: string | null;
  affected_ead: string | number;
  affected_ead_pct: number;
  incremental_el: string | number;
  mtm_impact: string | number;
  deterministic_rationale: string;
  stress_applied: boolean;
}

export interface EventStressOverviewResponse extends DashboardEnvelope {
  data: EventStressOverviewData;
}

export interface AttributionRow {
  dimension_value: string;
  exposure_count: number;
  ead: string | number;
  ead_pct: number;
  incremental_el: string | number;
  incremental_el_pct: number;
  mtm_impact: string | number;
  mtm_contribution_pct: number;
}

export interface ExposureAttributionRow {
  exposure_id: string;
  obligor: string;
  asset_type: string;
  sector: string;
  geography: string;
  ead: string | number;
  incremental_el: string | number;
  mtm_impact: string | number;
  is_affected: boolean;
}

export interface RiskAttributionData {
  event_id: string;
  by_sector: AttributionRow[];
  by_geography: AttributionRow[];
  by_asset_type: AttributionRow[];
  by_exposure: ExposureAttributionRow[];
}

export interface RiskAttributionResponse extends DashboardEnvelope {
  data: RiskAttributionData;
}

export interface ComparisonDeltas {
  affected_ead_difference: string | number;
  incremental_el_difference: string | number;
  absolute_mtm_difference: string | number;
}

export interface AttributionDeltaRow {
  dimension_value: string;
  ead_difference: string | number;
  incremental_el_difference: string | number;
  mtm_impact_difference: string | number;
  ead_pct_difference: number;
  incremental_el_pct_difference: number;
  mtm_contribution_pct_difference: number;
}

export interface AttributionDifferences {
  by_sector: AttributionDeltaRow[];
  by_geography: AttributionDeltaRow[];
  by_asset_type: AttributionDeltaRow[];
}

export interface ScenarioComparisonData {
  scenario_a: EventStressOverviewData;
  scenario_b: EventStressOverviewData;
  deltas: ComparisonDeltas;
  attribution_differences: AttributionDifferences;
}

export interface ScenarioComparisonResponse extends DashboardEnvelope {
  data: ScenarioComparisonData;
}
