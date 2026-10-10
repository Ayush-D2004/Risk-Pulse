import { AnimatePresence, motion } from 'framer-motion'
import { Activity, ArrowDownRight, ArrowRight, BarChart3, BookOpen, Check, ChevronRight, Database, Filter, Focus, GitCompareArrows, Globe, Layers3, Network, Plus, Search, Siren, Sparkles, Target, Trash2, TrendingDown, Workflow, X } from 'lucide-react'
import { useCallback, useState, useEffect, type ReactNode } from 'react'
import type { AnalystObservation, EventStressOverviewData, EventSummary, PortfolioOverviewData, RiskAttributionData, ScenarioComparisonData, Workspace, PipelineRun, ObservationInput } from '../types/api'
import { useApiQuery } from '../hooks/useApi'
import { submitAnalystSimulation, submitGdeltSearch, fetchPipelineRuns, promotePipelineRun, fetchHistoricalMarketData } from '../lib/api'
import { usePipelineStream } from '../hooks/usePipelineStream'
import { formatMoney, formatPct, formatDecimalPct, formatScore, formatSignedPct, impactTone, numeric, prettyLabel, sentimentLabel } from '../lib/format'
import { ContributionBars, ComparisonRows, DataTable, ExposureMatrix, InlineStack, RankedBars } from './charts'
import { AlertNote, AppMark, ArrowNote, EmptyState, ErrorState, IconBadge, Kicker, LoadingState, MetricBlock, RiskGauge, SectionFrame, SignalLine, StatusChip } from './ui'
import { PipelineRunViewer } from './pipeline'

export function WorkspaceTitle({ eyebrow, title, detail, action }: { eyebrow: string; title: string; detail: string; action?: ReactNode }) {
  return <div className="workspace-title"><div><Kicker>{eyebrow}</Kicker><h1>{title}</h1><p>{detail}</p></div>{action && <div className="workspace-title__action">{action}</div>}</div>
}

function SourceStamp({ generatedAt, schema, provenance }: { generatedAt?: string; schema?: string; provenance?: string }) {
  const isLive = provenance && provenance !== 'SYNTHETIC_FIXTURE' && provenance !== 'HISTORICAL_REPLAY'
  return <div className="source-stamp"><span>{isLive ? 'LIVE RUNTIME' : 'API-LINKED'}</span><span>{schema ? `SCHEMA ${schema}` : provenance || 'FIXTURE CATALOG'}</span>{generatedAt && <span>{generatedAt}</span>}</div>
}

function DataGate({ loading, error, empty, retry, children }: { loading: boolean; error: Error | null; empty: boolean; retry: () => void; children: ReactNode }) {
  if (loading) return <LoadingState />
  if (error) return <ErrorState detail={`${error.message}. Confirm the API is reachable at the configured base URL.`} onRetry={retry} />
  if (empty) return <EmptyState title="No observations returned" detail="This workspace is ready for live API data. No placeholder financial values are shown." />
  return <>{children}</>
}

export function CommandCenter({ portfolio, portfolioLoading, portfolioError, portfolioRetry, events, eventsLoading, eventsError, eventsRetry, onSelectEvent, onNavigate, lastRefresh }: {
  portfolio: { data: PortfolioOverviewData; generated_at?: string; schema_version?: string } | null
  portfolioLoading: boolean
  portfolioError: Error | null
  portfolioRetry: () => void
  events: EventSummary[]
  eventsLoading: boolean
  eventsError: Error | null
  eventsRetry: () => void
  onSelectEvent: (eventId: string) => void
  onNavigate: (workspace: Workspace) => void
  lastRefresh?: Date | null
}) {
  return <div className="workspace-stack">
    <WorkspaceTitle 
      eyebrow="COMMAND CENTER / 01" 
      title="Portfolio at a glance." 
      detail="A compact read on what is exposed, what is moving, and where the next research case starts." 
      action={
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {lastRefresh && (
            <div style={{ fontSize: '11px', color: 'var(--muted)', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.2 }}>
              <span style={{ fontWeight: 600 }}>LAST REFRESH</span>
              <span>{lastRefresh.toLocaleTimeString()}</span>
            </div>
          )}
          <div className="command-signal"><SignalLine /><span>RISK SIGNAL</span></div>
        </div>
      } 
    />
    <DataGate loading={portfolioLoading} error={portfolioError} empty={!portfolio?.data} retry={portfolioRetry}>
      {portfolio && <div className="hero-readout"><div><div className="hero-readout__label">Total Exposure at Default</div><div className="hero-readout__value">{formatMoney(portfolio.data.total_ead)}</div><div className="hero-readout__meta">{portfolio.data.exposure_count} exposures · {portfolio.data.obligor_count} obligors</div></div><div className="hero-readout__signal"><SignalLine /><div className="hero-readout__ticks"><span>EXPOSURE FIELD</span><span>CONCENTRATION / READ-ONLY</span></div></div></div>}
    </DataGate>
    <div className="metric-grid metric-grid--four"><MetricBlock label="EXPOSURES" value={portfolio?.data.exposure_count ?? '—'} note="portfolio count" /><MetricBlock label="OBLIGORS" value={portfolio?.data.obligor_count ?? '—'} note="named counterparties" /><MetricBlock label="EVENT FEED" value={eventsLoading ? '…' : events.length || '—'} note="returned by API" tone={events.length ? 'amber' : 'default'} /><MetricBlock label="DATA LINK" value={portfolioError || eventsError ? 'DEGRADED' : 'READY'} note={portfolioError || eventsError ? 'check endpoint status' : 'contract connected'} tone={portfolioError || eventsError ? 'danger' : 'mint'} />
    </div>
    <div className="workspace-grid workspace-grid--two-one"><SectionFrame eyebrow="EVENT INTELLIGENCE" title="Open risk cases" meta={<button className="text-button" onClick={() => onNavigate('events')}>View full feed <ArrowRight size={14} /></button>}><DataGate loading={eventsLoading} error={eventsError} empty={!events.length} retry={eventsRetry}>{<div className="mini-event-list">{events.slice(0, 4).map((event) => <button className="mini-event" key={event.event_id} onClick={() => onSelectEvent(event.event_id)}><span className={`mini-event__score mini-event__score--${impactTone(event.impact_tier)}`}>{formatScore(event.impact_score)}</span><span className="mini-event__body"><strong>{event.entity}</strong><span>{prettyLabel(event.event_type)} · {prettyLabel(event.impact_tier)}</span></span><ChevronRight size={15} /></button>)}</div>}</DataGate></SectionFrame><SectionFrame eyebrow="CONCENTRATION" title="Where the book leans" meta={<button className="text-button" onClick={() => onNavigate('portfolio')}>Inspect portfolio <ArrowRight size={14} /></button>}>{portfolio ? <><div className="signal-list">{portfolio.data.concentration_indicators.slice(0, 4).map((indicator) => <div className="signal-list__item" key={indicator}><span className="signal-list__mark" /><span>{indicator}</span></div>)}</div><div className="mini-bars"><RankedBars rows={portfolio.data.sector_distribution} limit={4} /></div></> : <EmptyState title="Awaiting portfolio data" detail="Concentration indicators will appear when the portfolio contract responds." />}</SectionFrame></div>
    <div className="footer-ribbon"><span>RISK PULSE</span><span>SELECT A CASE TO TRACE IMPACT THROUGH THE BOOK <ArrowRight size={13} /></span></div>
  </div>
}

export function EventsWorkspace({ events, loading, error, retry, selectedId, onSelect, lastRefresh }: { events: EventSummary[]; loading: boolean; error: Error | null; retry: () => void; selectedId: string | null; onSelect: (id: string) => void; lastRefresh?: Date | null }) {
  return <div className="workspace-stack">
    <WorkspaceTitle 
      eyebrow="EVENT INTELLIGENCE / 03" 
      title="Risk, in sequence." 
      detail="A research feed for material signals. Open a case to trace its stress path through the book." 
      action={
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {lastRefresh && (
            <div style={{ fontSize: '11px', color: 'var(--muted)', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.2 }}>
              <span style={{ fontWeight: 600 }}>LAST REFRESH</span>
              <span>{lastRefresh.toLocaleTimeString()}</span>
            </div>
          )}
          <button className="filter-button"><Filter size={14} /> Filter view</button>
        </div>
      } 
    />
    <SectionFrame eyebrow="LIVE EVENT REGISTER" title="Risk event feed" meta={<SourceStamp schema="EVENTS" />}>
      <DataGate loading={loading} error={error} empty={!events.length} retry={retry}>
        {<div className="event-feed">{events.map((event, index) => <motion.button initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} className={`event-row ${selectedId === event.event_id ? 'event-row--selected' : ''}`} key={event.event_id} onClick={() => onSelect(event.event_id)}><div className="event-row__index">{String(index + 1).padStart(2, '0')}</div><div className={`event-row__score event-row__score--${impactTone(event.impact_tier)}`}><span>{formatScore(event.impact_score)}</span><small>IMPACT</small></div><div className="event-row__main"><div className="event-row__headline"><strong>{event.entity}</strong><span>{prettyLabel(event.event_type)}</span><StatusChip label={event.impact_tier} />{event.provenance && <span style={{ marginLeft: '8px', fontSize: '10px', padding: '2px 4px', background: '#F3F4F6', color: '#6B7280', borderRadius: '4px' }}>{event.provenance}</span>}</div><div className="event-row__detail">{event.deterministic_rationale || 'Deterministic rationale not returned by the API.'}</div></div><div className="event-row__facts"><span>{prettyLabel(sentimentLabel(event.sentiment))} SENTIMENT</span><span>{event.shock_scope ? prettyLabel(event.shock_scope) : 'SCOPE NOT RETURNED'}</span></div><ChevronRight className="event-row__arrow" size={16} /></motion.button>)}</div>}
      </DataGate>
    </SectionFrame>
  </div>
}

export function PortfolioWorkspace({ portfolio, loading, error, retry }: { portfolio: { data: PortfolioOverviewData; generated_at?: string; schema_version?: string } | null; loading: boolean; error: Error | null; retry: () => void }) {
  const data = portfolio?.data
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="PORTFOLIO / 02" title="The book, under a lens." detail="Concentration and obligor structure from the portfolio contract — ranked to keep attention on materiality." action={portfolio && <SourceStamp generatedAt={portfolio.generated_at} schema={portfolio.schema_version} />} /><DataGate loading={loading} error={error} empty={!data} retry={retry}>{data && <><div className="metric-grid metric-grid--four"><MetricBlock label="TOTAL EAD" value={formatMoney(data.total_ead)} note="exposure at default" tone="mint" /><MetricBlock label="EXPOSURES" value={data.exposure_count} note="portfolio count" /><MetricBlock label="OBLIGORS" value={data.obligor_count} note="named counterparties" /><MetricBlock label="INDICATORS" value={data.concentration_indicators.length} note="returned by API" /></div><div className="workspace-grid workspace-grid--one-two"><SectionFrame eyebrow="SECTOR × EAD" title="Concentration field" meta={<span className="meta-code">RANKED / ABSOLUTE</span>}><RankedBars rows={data.sector_distribution} limit={8} /></SectionFrame><SectionFrame eyebrow="TOP OBLIGORS" title="Material counterparties" meta={<span className="meta-code">EAD + SHARE</span>}><div className="obligor-list">{data.top_obligors.slice(0, 8).map((row, index) => <div className="obligor-row" key={`${row.obligor}-${index}`}><span className="obligor-row__rank">{String(index + 1).padStart(2, '0')}</span><span className="obligor-row__name">{row.obligor}</span><span className="obligor-row__pct">{formatPct(row.pct)}</span><span className="obligor-row__ead">{formatMoney(row.ead)}</span></div>)}</div></SectionFrame></div><div className="workspace-grid workspace-grid--three"><SectionFrame eyebrow="GEOGRAPHY" title="Geographic concentration"><RankedBars rows={data.geography_distribution} limit={7} /></SectionFrame><SectionFrame eyebrow="RATING PROFILE" title="Rating distribution"><div className="rating-strip"><InlineStack rows={data.rating_distribution} /></div><div className="legend-list">{data.rating_distribution.map((row) => <div key={row.name}><span className="legend-list__swatch" /><span>{row.name}</span><strong>{formatMoney(row.ead)}</strong></div>)}</div></SectionFrame><SectionFrame eyebrow="CONCENTRATION SIGNALS" title="Indicators"><div className="signal-list">{data.concentration_indicators.map((indicator) => <div className="signal-list__item" key={indicator}><span className="signal-list__mark" /><span>{indicator}</span></div>)}</div></SectionFrame></div></>}</DataGate></div>
}

export function InvestigationWorkspace({ event, overview, overviewLoading, overviewError, overviewRetry, attribution, attributionLoading, attributionError, attributionRetry, onNavigate }: { event: EventSummary | null; overview: EventStressOverviewData | null; overviewLoading: boolean; overviewError: Error | null; overviewRetry: () => void; attribution: RiskAttributionData | null; attributionLoading: boolean; attributionError: Error | null; attributionRetry: () => void; onNavigate: (workspace: Workspace) => void }) {
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="CASE FILE / 04" title={event ? `${event.entity} — investigation` : 'Open a research case.'} detail={event ? `${prettyLabel(event.event_type)} · event ${event.event_id}` : 'Select a risk event from the feed to load its scenario overview.'} action={event && <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}><StatusChip label={event.impact_tier} /><SourceStamp provenance={event.provenance || overview?.provenance} /></div>} />{!event ? <EmptyState title="No case selected" detail="Open an event from Event Intelligence to populate the investigation workspace." icon={<Search size={18} />} /> : <><DataGate loading={overviewLoading} error={overviewError} empty={!overview} retry={overviewRetry}>{overview && <><div className="investigation-hero"><div className="investigation-hero__narrative"><div className="section-eyebrow">DETERMINISTIC RATIONALE</div><p>{overview.deterministic_rationale}</p><div className="narrative-meta"><span><b>ENTITY</b>{overview.entity}</span><span><b>EVENT TYPE</b>{prettyLabel(overview.event_type)}</span><span><b>SENTIMENT</b>{prettyLabel(sentimentLabel(overview.sentiment))}</span></div></div><RiskGauge score={overview.impact_score} tier={overview.impact_tier} /></div><SectionFrame eyebrow="STRESS PATHWAY" title="Trace the shock."><div className="causality-flow"><div className="flow-node flow-node--event"><span>01 / EVENT</span><strong>{prettyLabel(overview.event_type)}</strong><small>{prettyLabel(overview.entity)} · {formatScore(overview.impact_score)} impact</small></div><div className="flow-connector"><span>shock applied</span><ArrowDownRight /></div><div className="flow-node"><span>02 / SHOCK</span><strong>{prettyLabel(overview.shock_scope)}</strong><small>{overview.stress_applied ? 'scenario applied' : 'scenario not applied'}</small></div><div className="flow-connector"><span>portfolio consequence</span><ArrowDownRight /></div><div className="flow-node"><span>03 / PORTFOLIO</span><strong>{formatMoney(overview.affected_ead)}</strong><small>{formatDecimalPct(overview.affected_ead_pct)} affected EAD</small></div><div className="flow-connector"><span>loss creation</span><ArrowDownRight /></div><div className="flow-node flow-node--loss"><span>04 / LOSS</span><strong>{formatMoney(overview.incremental_el)}</strong><small>incremental expected loss</small></div><div className="flow-connector"><span>valuation</span><ArrowDownRight /></div><div className="flow-node flow-node--mtm"><span>05 / VALUATION</span><strong>{formatMoney(overview.mtm_impact)}</strong><small>mark-to-market impact</small></div></div><div className="stress-footnote"><AlertNote>Scope is API-defined as <strong>{prettyLabel(overview.shock_scope)}</strong>. The frontend does not broaden or reinterpret the stress.</AlertNote><div className="stress-readout"><span>RISK OUTPUT / READ-ONLY</span><SignalLine variant="coral" /></div></div></SectionFrame><div className="metric-grid metric-grid--four"><MetricBlock label="AFFECTED EAD" value={formatMoney(overview.affected_ead)} note={`${formatDecimalPct(overview.affected_ead_pct)} of portfolio`} tone="amber" /><MetricBlock label="INCREMENTAL EL" value={formatMoney(overview.incremental_el)} note="stress output" tone="danger" /><MetricBlock label="MTM IMPACT" value={formatMoney(overview.mtm_impact)} note="valuation output" tone="danger" /><MetricBlock label="SHOCK SCOPE" value={prettyLabel(overview.shock_scope)} note={overview.stress_applied ? 'stress applied' : 'stress not applied'} /></div></>}</DataGate><DataGate loading={attributionLoading} error={attributionError} empty={!attribution} retry={attributionRetry}>{attribution && <><SectionFrame eyebrow="EXPOSURE REGISTER" title="Affected exposures" meta={<span className="meta-code">{attribution.by_exposure.length} ROWS</span>}><DataTable headers={['OBLIGOR', 'ASSET TYPE', 'SECTOR', 'GEOGRAPHY', 'EAD', 'INCREMENTAL EL', 'MTM', 'STATE']} rows={attribution.by_exposure.slice(0, 12).map((row) => [row.obligor, prettyLabel(row.asset_type), row.sector, row.geography, formatMoney(row.ead), formatMoney(row.incremental_el), formatMoney(row.mtm_impact), row.is_affected ? 'AFFECTED' : 'NOT AFFECTED'])} /></SectionFrame><div className="workspace-grid workspace-grid--three"><SectionFrame eyebrow="BY SECTOR" title="Expected loss contribution"><ContributionBars rows={attribution.by_sector} valueKey="incremental_el" limit={6} /></SectionFrame><SectionFrame eyebrow="BY GEOGRAPHY" title="EAD intensity"><ContributionBars rows={attribution.by_geography} valueKey="ead" limit={6} /></SectionFrame><SectionFrame eyebrow="BY ASSET TYPE" title="MTM contribution"><ContributionBars rows={attribution.by_asset_type} valueKey="mtm_impact" limit={6} /></SectionFrame></div><SectionFrame eyebrow="CONCENTRATION MAP" title="Dimension × exposure intensity" meta={<span className="meta-code">EAD PCT / EXPOSURE COUNT</span>}><ExposureMatrix rows={attribution.by_sector} /></SectionFrame></>}</DataGate></>}</div>
}

export function StressLabWorkspace({ event, overview, loading, error, retry }: { event: EventSummary | null; overview: EventStressOverviewData | null; loading: boolean; error: Error | null; retry: () => void }) {
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="STRESS LAB / 05" title="Trace the shock." detail="Follow causality from the event signal to loss creation and valuation impact." action={<IconBadge tone="danger"><Siren size={16} /></IconBadge>} />{!event ? <EmptyState title="Choose an event to stress" detail="The lab follows the scenario endpoint for the selected event. Select a case from Event Intelligence first." icon={<Workflow size={18} />} /> : <DataGate loading={loading} error={error} empty={!overview} retry={retry}>{overview && <><div className="stress-banner"><div><Kicker tone="danger">ACTIVE CASE / {overview.event_id}</Kicker><h2>{overview.entity} · {prettyLabel(overview.event_type)}</h2><p>{overview.deterministic_rationale}</p></div><RiskGauge score={overview.impact_score} tier={overview.impact_tier} /></div><div className="causality-flow"><div className="flow-node flow-node--event"><span>01 / EVENT</span><strong>{prettyLabel(overview.event_type)}</strong><small>{prettyLabel(overview.entity)} · {formatScore(overview.impact_score)} impact</small></div><div className="flow-connector"><span>shock applied</span><ArrowDownRight /></div><div className="flow-node"><span>02 / SHOCK</span><strong>{prettyLabel(overview.shock_scope)}</strong><small>{overview.stress_applied ? 'scenario applied' : 'scenario not applied'}</small></div><div className="flow-connector"><span>portfolio consequence</span><ArrowDownRight /></div><div className="flow-node"><span>03 / PORTFOLIO</span><strong>{formatMoney(overview.affected_ead)}</strong><small>{formatPct(overview.affected_ead_pct)} affected EAD</small></div><div className="flow-connector"><span>loss creation</span><ArrowDownRight /></div><div className="flow-node flow-node--loss"><span>04 / LOSS</span><strong>{formatMoney(overview.incremental_el)}</strong><small>incremental expected loss</small></div><div className="flow-connector"><span>valuation</span><ArrowDownRight /></div><div className="flow-node flow-node--mtm"><span>05 / VALUATION</span><strong>{formatMoney(overview.mtm_impact)}</strong><small>mark-to-market impact</small></div></div><div className="stress-footnote"><AlertNote>Scope is API-defined as <strong>{prettyLabel(overview.shock_scope)}</strong>. The frontend does not broaden or reinterpret the stress.</AlertNote><div className="stress-readout"><span>RISK OUTPUT / READ-ONLY</span><SignalLine variant="coral" /></div></div></>}</DataGate>}</div>
}

export function AttributionWorkspace({ event, attribution, loading, error, retry }: { event: EventSummary | null; attribution: RiskAttributionData | null; loading: boolean; error: Error | null; retry: () => void }) {
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="ATTRIBUTION / 06" title="Where risk lands." detail={event ? `Exposure contribution for ${event.entity}, grouped by the dimensions returned by the attribution contract.` : 'Select an event to trace contribution across sector, geography, asset type, and exposure.'} action={<IconBadge tone="amber"><Target size={16} /></IconBadge>} />{!event ? <EmptyState title="Attribution is event-scoped" detail="Choose an event from the feed to load its exposure contribution rows." icon={<Layers3 size={18} />} /> : <DataGate loading={loading} error={error} empty={!attribution} retry={retry}>{attribution && <><div className="workspace-grid workspace-grid--three"><SectionFrame eyebrow="BY SECTOR" title="Expected loss contribution"><ContributionBars rows={attribution.by_sector} valueKey="incremental_el" limit={6} /></SectionFrame><SectionFrame eyebrow="BY GEOGRAPHY" title="EAD intensity"><ContributionBars rows={attribution.by_geography} valueKey="ead" limit={6} /></SectionFrame><SectionFrame eyebrow="BY ASSET TYPE" title="MTM contribution"><ContributionBars rows={attribution.by_asset_type} valueKey="mtm_impact" limit={6} /></SectionFrame></div><SectionFrame eyebrow="CONCENTRATION MAP" title="Dimension × exposure intensity" meta={<span className="meta-code">EAD PCT / EXPOSURE COUNT</span>}><ExposureMatrix rows={attribution.by_sector} /></SectionFrame><SectionFrame eyebrow="EXPOSURE REGISTER" title="Affected exposures" meta={<span className="meta-code">{attribution.by_exposure.length} ROWS</span>}><DataTable headers={['OBLIGOR', 'ASSET TYPE', 'SECTOR', 'GEOGRAPHY', 'EAD', 'INCREMENTAL EL', 'MTM', 'STATE']} rows={attribution.by_exposure.slice(0, 12).map((row) => [row.obligor, prettyLabel(row.asset_type), row.sector, row.geography, formatMoney(row.ead), formatMoney(row.incremental_el), formatMoney(row.mtm_impact), row.is_affected ? 'AFFECTED' : 'NOT AFFECTED'])} /></SectionFrame></>}</DataGate>}</div>
}

export function ComparisonWorkspace({ eventA, eventB, comparison, loading, error, retry, onSelectPair }: { eventA: EventSummary | null; eventB: EventSummary | null; comparison: ScenarioComparisonData | null; loading: boolean; error: Error | null; retry: () => void; onSelectPair: () => void }) {
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="COMPARISON / 07" title="Two cases. One book." detail="A compact research view for comparing API-backed scenarios and the contribution delta between them." action={<button className="filter-button" onClick={onSelectPair}><GitCompareArrows size={14} /> Change pair</button>} />{!eventA || !eventB ? <EmptyState title="Comparison pair not ready" detail="Choose two distinct events from the event feed to load the comparison endpoint." icon={<GitCompareArrows size={18} />} /> : <DataGate loading={loading} error={error} empty={!comparison} retry={retry}>{comparison && <><div className="comparison-head"><div className="comparison-head__case"><span>SCENARIO A</span><strong>{comparison.scenario_a.entity}</strong><small>{prettyLabel(comparison.scenario_a.event_type)} · {formatScore(comparison.scenario_a.impact_score)} impact</small></div><div className="comparison-head__vs">VS</div><div className="comparison-head__case comparison-head__case--b"><span>SCENARIO B</span><strong>{comparison.scenario_b.entity}</strong><small>{prettyLabel(comparison.scenario_b.event_type)} · {formatScore(comparison.scenario_b.impact_score)} impact</small></div></div><div className="comparison-metrics"><div className="comparison-metrics__header"><span>METRIC</span><span>SCENARIO A</span><span>SCENARIO B</span><span>DELTA</span></div>{[['IMPACT', formatScore(comparison.scenario_a.impact_score), formatScore(comparison.scenario_b.impact_score), formatSignedPct(comparison.scenario_b.impact_score - comparison.scenario_a.impact_score)], ['AFFECTED EAD', formatMoney(comparison.scenario_a.affected_ead), formatMoney(comparison.scenario_b.affected_ead), formatMoney(comparison.deltas.affected_ead_difference)], ['INCREMENTAL EL', formatMoney(comparison.scenario_a.incremental_el), formatMoney(comparison.scenario_b.incremental_el), formatMoney(comparison.deltas.incremental_el_difference)], ['MTM IMPACT', formatMoney(comparison.scenario_a.mtm_impact), formatMoney(comparison.scenario_b.mtm_impact), formatMoney(comparison.deltas.absolute_mtm_difference)]].map((row) => <div className="comparison-metrics__row" key={row[0]}><span>{row[0]}</span><strong>{row[1]}</strong><strong>{row[2]}</strong><strong className="comparison-metrics__delta">{row[3]}</strong></div>)}</div><SectionFrame eyebrow="ATTRIBUTION DIFFERENCES" title="Where the scenarios diverge"><div className="workspace-grid workspace-grid--three"><div><div className="mini-section-label">SECTOR</div><ComparisonRows rows={comparison.attribution_differences.by_sector} /></div><div><div className="mini-section-label">GEOGRAPHY</div><ComparisonRows rows={comparison.attribution_differences.by_geography} /></div><div><div className="mini-section-label">ASSET TYPE</div><ComparisonRows rows={comparison.attribution_differences.by_asset_type} /></div></div></SectionFrame></>}</DataGate>}</div>
}

export interface SimulationWorkspaceState {
  companyName?: string
  ticker?: string
  eventDate?: string
  eventTime?: string
  timezone?: string
  observations: AnalystObservation[]
  submitting: boolean
  submitError: Error | null
  activeRunId: string | null
}

function formatDateTime(timestamp: string, timezone: string) {
  try {
    const d = new Date(timestamp)
    return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ${timezone}`
  } catch {
    return timestamp
  }
}

function MarketChart({ companyName, ticker, timestamp, timezone }: { companyName?: string, ticker: string, timestamp: string, timezone: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetchHistoricalMarketData(ticker, timestamp, timezone, controller.signal)
      .then(res => {
        setData(res)
        setLoading(false)
      })
      .catch(err => {
        if (!controller.signal.aborted) {
          setError(err)
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [ticker, timestamp, timezone])

  if (loading) return <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)', fontSize: '13px' }}>Loading market data from Yahoo Finance...</div>
  if (error) return <div style={{ padding: '24px', color: 'var(--coral, #ef4444)', fontSize: '13px' }}>Error loading market data: {error.message}</div>
  if (!data || data.status !== 'success') return <div style={{ padding: '24px', color: 'var(--amber, #f59e0b)', fontSize: '13px' }}>Market data unavailable for this window.</div>

  const points: { timestamp: string, close: number }[] = data.points
  if (!points || points.length === 0) return null

  // Calculate pricing bounds
  const prices = points.map(p => p.close)
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const priceDelta = maxPrice - minPrice || 1
  const priceMargin = priceDelta * 0.08
  const chartMin = minPrice - priceMargin
  const chartMax = maxPrice + priceMargin
  const chartRange = chartMax - chartMin || 1

  // Chart dimensions & layout (spacious, responsive height)
  const w = 720
  const h = 270
  const pad = { top: 28, right: 35, bottom: 35, left: 70 }
  const plotW = w - pad.left - pad.right
  const plotH = h - pad.top - pad.bottom

  const minTime = new Date(points[0].timestamp).getTime()
  const maxTime = new Date(points[points.length - 1].timestamp).getTime()
  const timeRange = maxTime - minTime || 1

  // Map data points into coordinates
  const mappedPoints = points.map((p, i) => {
    const pTime = new Date(p.timestamp).getTime()
    const x = points.length === 1 
      ? pad.left + plotW / 2 
      : pad.left + ((pTime - minTime) / timeRange) * plotW
    const y = pad.top + plotH - ((p.close - chartMin) / chartRange) * plotH
    return { ...p, x, y, index: i }
  })

  // SVG Paths
  const linePath = mappedPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const areaPath = mappedPoints.length > 0 
    ? `${linePath} L ${mappedPoints[mappedPoints.length - 1].x.toFixed(1)} ${(pad.top + plotH).toFixed(1)} L ${mappedPoints[0].x.toFixed(1)} ${(pad.top + plotH).toFixed(1)} Z`
    : ''

  // Visual trend styling
  const isPositive = data.metrics.change_pct >= 0
  const pctStr = data.metrics.change_pct.toFixed(2)
  const isPostPositive = data.metrics.post_event_change_pct >= 0
  const strokeColor = isPositive ? '#10b981' : '#f43f5e'
  const gradId = `chartGrad-${ticker}-${Math.abs(minTime)}`

  // Event marker position
  const eventTimeMs = new Date(data.event_timestamp).getTime()
  const eventX = pad.left + ((eventTimeMs - minTime) / timeRange) * plotW
  const eventIsOutOfBounds = eventX < pad.left || eventX > pad.left + plotW
  const formattedEventDate = formatDateTime(data.event_timestamp, timezone)

  const preLabel = data.metrics.event_obs_time ? `Pre-event (${new Date(data.metrics.event_obs_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})` : "First"
  const prePrice = data.metrics.event_price ?? data.metrics.first_price
  const hasPostEvent = data.metrics.post_event_time != null

  // Active hover tracking
  const activePt = hoveredIdx !== null && mappedPoints[hoveredIdx] ? mappedPoints[hoveredIdx] : null

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svgRect = e.currentTarget.getBoundingClientRect()
    if (!svgRect.width) return
    const mouseX = ((e.clientX - svgRect.left) / svgRect.width) * w
    let closestIdx = 0
    let minDistance = Infinity
    mappedPoints.forEach((pt, idx) => {
      const dist = Math.abs(pt.x - mouseX)
      if (dist < minDistance) {
        minDistance = dist
        closestIdx = idx
      }
    })
    setHoveredIdx(closestIdx)
  }

  // Floating tooltip dimensions
  const tooltipW = 160
  const tooltipH = 50
  let tipX = activePt ? activePt.x + 12 : 0
  if (activePt && tipX + tooltipW > w - 10) tipX = activePt.x - tooltipW - 12
  let tipY = activePt ? Math.max(pad.top, Math.min(activePt.y - 25, pad.top + plotH - tooltipH)) : 0
  const diffFromStart = activePt ? ((activePt.close - points[0].close) / points[0].close) * 100 : 0

  const displayTitle = companyName ? `${companyName} (${ticker})` : ticker

  return (
    <SectionFrame 
      eyebrow="OBSERVED MARKET RESPONSE" 
      title={displayTitle}
      meta={
        <div style={{ color: 'var(--muted)', fontSize: '13px' }}>
          Historical Close ({points.length} points) • {timezone}
        </div>
      }
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', marginBottom: '16px' }}>
        <MetricBlock label={preLabel} value={`$${prePrice.toFixed(2)}`} />
        {hasPostEvent ? (
          <MetricBlock label={`Post-event (${new Date(data.metrics.post_event_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})`} value={`$${data.metrics.post_event_price.toFixed(2)}`} />
        ) : (
          <MetricBlock label="Last observed" value={`$${data.metrics.last_price.toFixed(2)}`} />
        )}
        
        {hasPostEvent ? (
          <MetricBlock 
            label="Post-event Return (1h)" 
            value={`${isPostPositive ? '+' : ''}${data.metrics.post_event_change_pct.toFixed(2)}%`} 
            tone={isPostPositive ? 'mint' : 'danger'} 
          />
        ) : (
          <MetricBlock 
            label="Window Return" 
            value={`${isPositive ? '+' : ''}${pctStr}%`} 
            tone={isPositive ? 'mint' : 'danger'} 
          />
        )}
        
        <MetricBlock label="Min/Max" value={`$${data.metrics.low_price.toFixed(2)} / $${data.metrics.high_price.toFixed(2)}`} />
      </div>
      
      <div style={{ padding: '16px', border: '1px solid #dce2e8', borderRadius: '8px', background: '#ffffff', boxShadow: '0 2px 8px rgba(0, 0, 0, 0.04)' }}>
        <div style={{ position: 'relative', width: '100%', height: `${h}px` }}>
          {eventIsOutOfBounds && (
             <div style={{ position: 'absolute', top: 0, left: 0, right: 0, textAlign: 'center', fontSize: '11px', color: '#b45309', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid #fde68a', borderRadius: '4px', padding: '4px', zIndex: 2 }}>
               The event time ({formattedEventDate}) is outside the available trading session points.
             </div>
          )}
          <svg 
            viewBox={`0 0 ${w} ${h}`} 
            style={{ width: '100%', height: '100%', overflow: 'visible', cursor: 'crosshair' }} 
            preserveAspectRatio="none"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoveredIdx(null)}
          >
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={strokeColor} stopOpacity="0.14" />
                <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Background Grid Lines & Y-Axis Labels */}
            <line x1={pad.left} y1={pad.top} x2={pad.left + plotW} y2={pad.top} stroke="#e2e8f0" strokeWidth="1" strokeDasharray="3 3" />
            <text x={pad.left - 8} y={pad.top + 3} textAnchor="end" fill="#0f172a" fontSize="11" fontWeight="600" fontFamily="monospace">${maxPrice.toFixed(2)}</text>

            <line x1={pad.left} y1={pad.top + plotH / 2} x2={pad.left + plotW} y2={pad.top + plotH / 2} stroke="#e2e8f0" strokeWidth="1" strokeDasharray="3 3" />
            <text x={pad.left - 8} y={pad.top + plotH / 2 + 3} textAnchor="end" fill="#0f172a" fontSize="11" fontWeight="600" fontFamily="monospace">${((maxPrice + minPrice) / 2).toFixed(2)}</text>

            <line x1={pad.left} y1={pad.top + plotH} x2={pad.left + plotW} y2={pad.top + plotH} stroke="#e2e8f0" strokeWidth="1" strokeDasharray="3 3" />
            <text x={pad.left - 8} y={pad.top + plotH + 3} textAnchor="end" fill="#0f172a" fontSize="11" fontWeight="600" fontFamily="monospace">${minPrice.toFixed(2)}</text>

            {/* Gradient Area Fill */}
            {areaPath && (
              <path d={areaPath} fill={`url(#${gradId})`} />
            )}

            {/* Vertical event marker line */}
            {!eventIsOutOfBounds && (
              <>
                <line x1={eventX} y1={pad.top} x2={eventX} y2={pad.top + plotH} stroke="#dc2626" strokeWidth="1.5" strokeDasharray="4 3" />
                <rect x={eventX - 28} y={pad.top - 18} width="56" height="15" rx="3" fill="#dc2626" />
                <text x={eventX} y={pad.top - 7} fontSize="9" fill="#ffffff" fontWeight="bold" fontFamily="monospace" textAnchor="middle">EVENT</text>
              </>
            )}

            {/* Price Movement Line */}
            <path d={linePath} fill="none" stroke={strokeColor} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />

            {/* Data Point Dots */}
            {mappedPoints.length <= 40 && mappedPoints.map((pt) => (
              <circle key={pt.index} cx={pt.x} cy={pt.y} r="3.5" fill={strokeColor} stroke="#ffffff" strokeWidth="1.5" />
            ))}

            {/* Active Hover Crosshair & Details */}
            {activePt && (
              <>
                <line x1={activePt.x} y1={pad.top} x2={activePt.x} y2={pad.top + plotH} stroke="#64748b" strokeWidth="1" strokeDasharray="3 3" opacity="0.6" />
                <circle cx={activePt.x} cy={activePt.y} r="6" fill={strokeColor} stroke="#ffffff" strokeWidth="2.5" />
                
                {/* Floating Tooltip Card */}
                <g transform={`translate(${tipX}, ${tipY})`}>
                  <rect width={tooltipW} height={tooltipH} rx="6" fill="#ffffff" stroke="#cbd5e1" filter="drop-shadow(0 4px 10px rgba(0,0,0,0.10))" />
                  <text x="10" y="18" fill="#475569" fontSize="10" fontFamily="monospace">{formatDateTime(activePt.timestamp, timezone)}</text>
                  <text x="10" y="38" fill="#0f172a" fontSize="13" fontWeight="bold" fontFamily="monospace">${activePt.close.toFixed(2)}</text>
                  <text x={tooltipW - 10} y="38" textAnchor="end" fill={diffFromStart >= 0 ? '#16a34a' : '#dc2626'} fontSize="11" fontWeight="bold" fontFamily="monospace">
                    {diffFromStart >= 0 ? '+' : ''}{diffFromStart.toFixed(2)}%
                  </text>
                </g>
              </>
            )}
          </svg>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', paddingLeft: `${pad.left}px`, fontSize: '11px', color: '#1e293b', fontWeight: '500', fontFamily: 'monospace' }}>
          <span>{formatDateTime(points[0].timestamp, timezone)}</span>
          <span>{formatDateTime(points[points.length-1].timestamp, timezone)}</span>
        </div>
      </div>
    </SectionFrame>
  )
}

function SimulationResultView({ result, run }: { result: any, run: any }) {
  const signal = result.signals?.[0]
  const stress = result.stress_results?.[0]

  if (!signal) return <EmptyState title="No Risk Signal Produced" detail="The pipeline did not generate a canonical risk signal." />

  const meta = run?.request?.observations?.[0]?.metadata || {}
  const hasMarketData = meta.ticker && meta.event_datetime && meta.timezone

  return (
    <>
      <SectionFrame eyebrow="AI EVENT ANALYSIS" title={`${signal.entity} · ${prettyLabel(signal.event_type)}`}>
        <div style={{ display: 'flex', gap: '32px', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 200px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
               <MetricBlock label="MATERIALITY" value={prettyLabel(signal.materiality)} />
               <MetricBlock label="SENTIMENT SCORE" value={signal.sentiment_score?.toFixed(2) || '0.00'} />
            </div>
          </div>
          <div style={{ flex: '0 0 auto', alignSelf: 'center' }}>
            <RiskGauge score={signal.impact_score} tier={signal.impact_tier || 'UNKNOWN'} />
          </div>
        </div>
      </SectionFrame>

      {hasMarketData && (
        <MarketChart 
          companyName={meta.company_name || signal.entity}
          ticker={meta.ticker} 
          timestamp={meta.event_datetime} 
          timezone={meta.timezone} 
        />
      )}

      {!stress ? (
        <SectionFrame eyebrow="PORTFOLIO STRESS ASSESSMENT" title="Stress Output Unavailable" meta={<StatusChip label="UNAVAILABLE" tone="amber" />}>
          <AlertNote>No portfolio stress data was returned by the pipeline.</AlertNote>
        </SectionFrame>
      ) : stress.error ? (
        <SectionFrame eyebrow="PORTFOLIO STRESS ASSESSMENT" title="Stress Calculation Failed" meta={<StatusChip label="FAILED" tone="danger" />}>
          <AlertNote>The stress engine encountered an error: {stress.error}</AlertNote>
        </SectionFrame>
      ) : !stress.stress_applied ? (
        stress.affected_exposure_count === 0 && (stress.shock_scenario?.shock_scope === 'ENTITY' || !stress.shock_scenario) ? (
          <SectionFrame 
            eyebrow="PORTFOLIO STRESS ASSESSMENT" 
            title="Unheld Counterparty · Zero Direct Exposure" 
            meta={<StatusChip label="UNHELD_ENTITY" tone="amber" />}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="metric-grid metric-grid--four">
                <MetricBlock label="COUNTERPARTY" value={signal.entity} />
                <MetricBlock label="SHOCK TRANSMISSION" value={prettyLabel(stress.shock_scenario?.shock_scope || 'ENTITY')} />
                <MetricBlock label="BOOK EXPOSURE (EAD)" value="$0.00" tone="amber" note="0.00% of portfolio" />
                <MetricBlock label="DIRECT CREDIT LOSS" value="$0.00" tone="mint" note="No active debt or equity held" />
              </div>

              <div style={{ padding: '16px', background: 'var(--surface)', border: '1px solid var(--line-strong)', borderRadius: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                  <span style={{ fontSize: '18px' }}>ℹ️</span>
                  <div style={{ fontSize: '13px', lineHeight: '1.6', color: 'var(--text)' }}>
                    <strong>Institutional Credit Portfolio Context:</strong>
                    <p style={{ margin: '6px 0 0', color: 'var(--muted)' }}>
                      The wholesale credit book holds <strong>$860M total EAD across 15 active corporate obligors</strong> (Technology, Energy, Industrials, Financials, Consumer, Healthcare, Sovereign). 
                      While the AI evaluated a severe shock ({prettyLabel(signal.impact_tier)}, Impact {signal.impact_score?.toFixed(1) || '0.0'}) on <em>{signal.entity}</em>, 
                      this company is not currently an obligor in the bank's wholesale loan or bond book. Direct single-name credit loss is mathematically <strong>$0.00</strong>.
                    </p>
                  </div>
                </div>
              </div>

              <div style={{ padding: '14px 16px', background: 'var(--bg-panel-2, #191e25)', borderRadius: '8px', border: '1px dashed var(--line-strong)' }}>
                <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: '8px' }}>
                  ACTIVE WHOLESALE BOOK COUNTERPARTIES (AVAILABLE FOR SINGLE-NAME CREDIT STRESS)
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '12px' }}>
                  <span style={{ padding: '4px 8px', borderRadius: '4px', background: 'var(--surface)', border: '1px solid var(--line)' }}>
                    <strong>Technology:</strong> Apple (AAPL, $80M) · Microsoft (MSFT, $40M) · Tesla (TSLA, $35M) · Samsung ($20M)
                  </span>
                  <span style={{ padding: '4px 8px', borderRadius: '4px', background: 'var(--surface)', border: '1px solid var(--line)' }}>
                    <strong>Industrials:</strong> Boeing (BA, $65M)
                  </span>
                  <span style={{ padding: '4px 8px', borderRadius: '4px', background: 'var(--surface)', border: '1px solid var(--line)' }}>
                    <strong>Energy:</strong> PetroGlobal ($260M) · Shell ($80M) · SaudiChem ($45M) · Rosneft ($35M)
                  </span>
                  <span style={{ padding: '4px 8px', borderRadius: '4px', background: 'var(--surface)', border: '1px solid var(--line)' }}>
                    <strong>Consumer:</strong> Amazon (AMZN, $90M) · RetailCo ($25M)
                  </span>
                </div>
              </div>
            </div>
          </SectionFrame>
        ) : (
          <SectionFrame eyebrow="PORTFOLIO STRESS ASSESSMENT" title="No Portfolio Stress Triggered" meta={<StatusChip label="NO_STRESS" tone="amber" />}>
            <AlertNote>{stress.rationale || "No applicable shock mapping for this event."}</AlertNote>
          </SectionFrame>
        )
      ) : (
        <SectionFrame eyebrow="PORTFOLIO STRESS ASSESSMENT" title="Stress Applied">
          <div className="metric-grid metric-grid--four">
            <MetricBlock label="AFFECTED EAD" value={formatMoney(stress.affected_ead)} tone="amber" />
            <MetricBlock label="INCREMENTAL EL" value={formatMoney(stress.incremental_expected_loss)} tone="danger" />
            <MetricBlock label="MTM IMPACT" value={formatMoney(stress.total_mtm_impact)} tone="danger" />
            <MetricBlock label="SHOCK SCOPE" value={prettyLabel(stress.shock_scenario?.shock_scope || 'NONE')} note={stress.rationale} />
          </div>
        </SectionFrame>
      )}
    </>
  )
}

function SimulationRunView({ runId, run, loading, connectionState, streamError, retry, onPromoteSuccess }: { runId: string, run: any, loading: boolean, connectionState: string, streamError: Error | null, retry: () => void, onPromoteSuccess?: () => void }) {
  const [promoting, setPromoting] = useState(false)
  const [promotedData, setPromotedData] = useState<{ count: number, eventIds: string[] } | null>(null)
  const [promoteError, setPromoteError] = useState<Error | null>(null)

  const handlePromote = async () => {
    if (!runId) return
    setPromoting(true)
    setPromoteError(null)
    try {
      const res = await promotePipelineRun(runId)
      if (res.status === 'SUCCESS' || res.status === 'ALREADY_PROMOTED') {
        setPromotedData({ count: res.count, eventIds: res.promoted_event_ids })
        if (onPromoteSuccess) onPromoteSuccess()
      }
    } catch (e) {
      setPromoteError(e instanceof Error ? e : new Error('Promotion failed'))
    } finally {
      setPromoting(false)
    }
  }

  const isEligible = run?.status === 'COMPLETED' && run.final_result && Array.isArray(run.final_result.signals) && run.final_result.signals.length > 0 && Array.isArray(run.final_result.stress_results) && run.final_result.stress_results.length > 0

  if (streamError) return <ErrorState title="Stream error" detail={streamError.message} onRetry={retry} />
  if (loading && !run) return <LoadingState />
  if (!run) return <EmptyState title="Run not found" detail="The execution may have expired." />

  const isTerminal = run.status === 'COMPLETED' || run.status === 'FAILED'
  const hasResults = isTerminal && run.final_result

  const companyName = 
    run?.request?.observations?.[0]?.metadata?.company_name ||
    run?.final_result?.signals?.[0]?.entity ||
    run?.request?.observations?.[0]?.metadata?.ticker ||
    `Simulation (${runId.slice(0, 8)})`

  return (
    <div className="workspace-stack">
      <SectionFrame 
        eyebrow={`PIPELINE EXECUTION · RUN ${runId.slice(0, 8)}`} 
        title={companyName} 
        meta={
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            {isEligible && (
              promotedData ? (
                <span style={{ fontSize: '12px', color: 'var(--mint)', fontWeight: 'bold' }}><Check size={14} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> PROMOTED ({promotedData.count})</span>
              ) : (
                <button 
                  type="button"
                  onClick={handlePromote} 
                  disabled={promoting}
                  style={{ 
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    background: '#0f172a', 
                    color: '#ffffff', 
                    fontWeight: 700, 
                    fontSize: '11px', 
                    letterSpacing: '0.04em',
                    padding: '6px 14px', 
                    borderRadius: '6px', 
                    border: '1px solid #334155',
                    cursor: promoting ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)',
                    transition: 'all 0.15s ease'
                  }}
                  onMouseOver={(e) => { e.currentTarget.style.background = '#1e293b' }}
                  onMouseOut={(e) => { e.currentTarget.style.background = '#0f172a' }}
                >
                  <Sparkles size={13} style={{ color: '#38bdf8' }} />
                  {promoting ? 'PROMOTING...' : 'PROMOTE TO COMMAND CENTER'}
                </button>
              )
            )}
            <StatusChip label={run.status} tone={run.status === 'FAILED' ? 'danger' : run.status === 'COMPLETED' ? 'mint' : 'default'} />
          </div>
        }
      >
        {promoteError && <div style={{ marginBottom: '16px' }}><ErrorState title="Promotion Failed" detail={promoteError.message} /></div>}
        <div style={{ display: 'flex', gap: '32px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 320px' }}>
            <div className="section-eyebrow" style={{ marginBottom: '16px' }}>EXECUTION TIMELINE</div>
            <div className="stage-timeline">
              {run.stages.map((stage: any) => {
                const statusLower = (stage.status || 'pending').toLowerCase()
                const tone = 
                  stage.status === 'FAILED' ? 'danger' : 
                  stage.status === 'COMPLETED' ? 'mint' : 
                  stage.status === 'RUNNING' ? 'amber' : 
                  stage.status === 'SKIPPED' ? 'neutral' : 
                  'default'

                return (
                  <div key={stage.name} className={`stage-row stage-row--${statusLower}`}>
                    <div className="stage-row__line" />
                    <div className="stage-row__indicator" />
                    <div>
                      <div className="stage-row__name">{stage.name.replace(/_/g, ' ').toUpperCase()}</div>
                      {stage.output && (
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', fontFamily: 'monospace' }}>
                          {Object.entries(stage.output).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                        </div>
                      )}
                      {stage.error && <div style={{ fontSize: '11px', color: '#EF4444', marginTop: '4px' }}>{stage.error}</div>}
                    </div>
                    <div style={{ alignSelf: 'center' }}>
                      <StatusChip label={stage.status} tone={tone} />
                    </div>
                  </div>
                )
              })}
            </div>
            {run.error && (
              <div style={{ marginTop: '16px', padding: '12px', borderLeft: '3px solid #EF4444', background: '#FEF2F2', fontSize: '13px', color: '#B91C1C' }}>
                <strong>Pipeline Error:</strong> {run.error}
              </div>
            )}
          </div>
          
          <div style={{ flex: '1 1 300px' }}>
            <div className="section-eyebrow" style={{ marginBottom: '16px' }}>CONTEXT</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', marginBottom: '24px' }}>
              <MetricBlock label="MODE" value={run.request?.mode || 'UNKNOWN'} />
              <MetricBlock label="OBSERVATIONS" value={run.request?.observations?.length || 0} />
              <MetricBlock label="PROVENANCE" value={run.request?.mode || 'UNKNOWN'} tone={run.request?.mode === 'LIVE_GDELT' ? 'mint' : 'amber'} />
            </div>
          </div>
        </div>
      </SectionFrame>

      {hasResults && <SimulationResultView result={run.final_result} run={run} />}
    </div>
  )
}

export function SimulationWorkspace({ state, setState, hideTitle, onPromoteSuccess }: { state: SimulationWorkspaceState, setState: React.Dispatch<React.SetStateAction<SimulationWorkspaceState>>, hideTitle?: boolean, onPromoteSuccess?: () => void }) {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { run, loading, connectionState, error: streamError, retry } = usePipelineStream(state.activeRunId)

  const addObservation = () => setState(prev => ({ ...prev, observations: [...prev.observations, { channel: 'NEWS', body: '', headline: '' }] }))
  
  const removeObservation = (index: number) => setState(prev => ({ ...prev, observations: prev.observations.filter((_, i) => i !== index) }))

  const updateObservation = (index: number, updates: Partial<AnalystObservation>) => {
    setState(prev => {
      const next = [...prev.observations]
      next[index] = { ...next[index], ...updates }
      return { ...prev, observations: next }
    })
  }

  const handleSubmit = async () => {
    const valid = state.observations.every(o => o.headline?.trim() || o.body?.trim())
    if (!valid) {
      setState(prev => ({ ...prev, submitError: new Error('Each observation must have text in the headline or body.') }))
      return
    }

    if (!state.companyName || !state.ticker || !state.eventDate || !state.eventTime || !state.timezone) {
      setState(prev => ({ ...prev, submitError: new Error('Company Name, Ticker, Event Date, Event Time, and Timezone are required.') }))
      return
    }

    setState(prev => ({ ...prev, submitting: true, submitError: null, activeRunId: null }))

    try {
      const event_datetime = `${state.eventDate}T${state.eventTime}:00`
      const res = await submitAnalystSimulation({ 
        mode: 'ANALYST_SIMULATION', 
        company_name: state.companyName,
        ticker: state.ticker,
        event_datetime,
        timezone: state.timezone,
        observations: state.observations 
      })
      setState(prev => ({ ...prev, activeRunId: res.run_id }))
      setIsModalOpen(false)
    } catch (e) {
      setState(prev => ({ ...prev, submitError: e instanceof Error ? e : new Error('Failed to submit simulation') }))
    } finally {
      setState(prev => ({ ...prev, submitting: false }))
    }
  }

  return (
    <div className={hideTitle ? "" : "workspace-stack"}>
      {!hideTitle && (
        <WorkspaceTitle 
          eyebrow="INTELLIGENCE LAB / 08" 
          title="Analyst Simulation" 
          detail="Simulate a real-time risk event to observe the execution pipeline." 
          action={
            <button 
              onClick={() => setIsModalOpen(true)}
              style={{ background: '#111827', color: 'white', padding: '10px 20px', borderRadius: '4px', fontSize: '13px', fontWeight: 'bold', border: '1px solid #374151', cursor: 'pointer' }}
            >
              Simulate Test
            </button>
          } 
        />
      )}
      
      {hideTitle && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '20px' }}>
          <button 
            onClick={() => setIsModalOpen(true)}
            style={{ background: '#111827', color: 'white', padding: '10px 20px', borderRadius: '4px', fontSize: '13px', fontWeight: 'bold', border: '1px solid #374151', cursor: 'pointer' }}
          >
            Simulate Test
          </button>
        </div>
      )}

      <AnimatePresence>
        {isModalOpen && (
          <div className="modal-backdrop" onClick={() => !state.submitting && setIsModalOpen(false)}>
            <motion.div 
              className="modal-content"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ duration: 0.15 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="modal-header">
                <h2>Configure Simulation</h2>
                <button className="topbar-icon" onClick={() => !state.submitting && setIsModalOpen(false)} disabled={state.submitting}><X size={18} /></button>
              </div>
              
              <div className="modal-body">
                <div style={{ marginBottom: '24px' }}>
                  <AlertNote>The pipeline expects unstructured text (News, Social Media). Provide a diverse set of inputs to simulate corroboration across channels.</AlertNote>
                </div>
                
                <div style={{ marginBottom: '24px' }}>
                  <div className="section-eyebrow" style={{ marginBottom: '10px' }}>PRESET BENCHMARK SCENARIOS</div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={() => {
                        setState(prev => ({
                          ...prev,
                          companyName: 'Apple Inc.',
                          ticker: 'AAPL',
                          eventDate: '2026-10-06',
                          eventTime: '11:30',
                          timezone: 'America/New_York',
                          observations: [
                            {
                              channel: 'NEWS',
                              headline: 'EU & US Antitrust Authorities Impose $14B Penalty on Apple Inc.',
                              body: 'European and US regulators levied unprecedented structural penalties and multi-billion dollar antitrust fines on Apple, mandating immediate App Store unbundling.'
                            },
                            {
                              channel: 'TWITTER_X_STYLE',
                              headline: '',
                              body: 'BREAKING: Historic $14B antitrust penalty handed down against Apple. Operating margins in severe jeopardy. $AAPL'
                            }
                          ]
                        }))
                      }}
                      style={{ padding: '6px 12px', background: 'var(--surface)', border: '1px solid var(--line-strong)', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', color: 'var(--text)' }}
                    >
                      ⚡ Apple: $14B Regulatory Fine ($80M EAD)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setState(prev => ({
                          ...prev,
                          companyName: 'Tesla Inc',
                          ticker: 'TSLA',
                          eventDate: '2026-10-06',
                          eventTime: '11:30',
                          timezone: 'America/New_York',
                          observations: [
                            {
                              channel: 'NEWS',
                              headline: 'Credit Agency Downgrades Tesla Debt to CCC Junk After Offshore Default',
                              body: 'Rating agencies slashed Tesla long-term debt to speculative grade following an unexpected missed payment on international notes, triggering cross-default covenants.'
                            },
                            {
                              channel: 'TWITTER_X_STYLE',
                              headline: '',
                              body: 'Tesla debt officially downgraded to CCC junk status after missed bond coupons. Debt covenants breaking! $TSLA'
                            }
                          ]
                        }))
                      }}
                      style={{ padding: '6px 12px', background: 'var(--surface)', border: '1px solid var(--line-strong)', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', color: 'var(--text)' }}
                    >
                      ⚡ Tesla: Debt Default & Downgrade ($35M EAD)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setState(prev => ({
                          ...prev,
                          companyName: 'PetroGlobal',
                          ticker: 'SHEL',
                          eventDate: '2026-10-06',
                          eventTime: '11:30',
                          timezone: 'America/New_York',
                          observations: [
                            {
                              channel: 'NEWS',
                              headline: 'Persian Gulf Shipping Blockade Disrupts Global Energy and Oil Deliveries',
                              body: 'Strait of Hormuz transit closure halts crude tanker traffic, causing severe refinery feed-stock shortages and operating losses across global energy providers.'
                            },
                            {
                              channel: 'TWITTER_X_STYLE',
                              headline: '',
                              body: 'Oil tankers halted in Persian Gulf! Massive supply chain disruption spreading across wholesale energy obligors. #EnergyShock'
                            }
                          ]
                        }))
                      }}
                      style={{ padding: '6px 12px', background: 'var(--surface)', border: '1px solid var(--line-strong)', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', color: 'var(--text)' }}
                    >
                      ⚡ PetroGlobal: Energy Supply Shock ($420M EAD)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setState(prev => ({
                          ...prev,
                          companyName: 'Boeing Co',
                          ticker: 'BA',
                          eventDate: '2024-01-08',
                          eventTime: '09:30',
                          timezone: 'America/New_York',
                          observations: [
                            {
                              channel: 'NEWS',
                              headline: 'FAA Orders Emergency Grounding of Boeing 737 MAX 9 Fleet; Credit Agencies Warn of Liabilities and Debt Downgrade',
                              body: 'Federal Aviation Administration officials issued an emergency grounding order for Boeing 737 MAX 9 jetliners after a mid-air blowout. Aviation credit analysts warn of billions in delivery delays, cash flow penalties, and negative rating downgrade reviews for Boeing debt facilities.'
                            },
                            {
                              channel: 'TWITTER_X_STYLE',
                              headline: '',
                              body: 'BREAKING: FAA grounds Boeing 737 MAX fleet. Massive production freeze and credit rating downgrade warnings across Wall Street. $BA'
                            }
                          ]
                        }))
                      }}
                      style={{ padding: '6px 12px', background: 'var(--surface)', border: '1px solid var(--line-strong)', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', color: 'var(--text)' }}
                    >
                      ⚡ Boeing: 737 MAX Grounding ($65M EAD)
                    </button>
                  </div>
                </div>
                
                <div style={{ marginBottom: '32px', padding: '24px', borderRadius: '12px', border: '1px solid var(--line-strong)', background: 'var(--bg)' }}>
                  <div className="section-eyebrow" style={{ marginBottom: '16px' }}>EVENT CONTEXT (GLOBAL)</div>
                  
                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', marginBottom: '16px' }}>
                    <div style={{ flex: '1 1 200px' }}>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>COMPANY NAME</label>
                      <input 
                        type="text" 
                        placeholder="e.g. Apple Inc."
                        value={state.companyName || ''} 
                        onChange={(e) => setState(prev => ({ ...prev, companyName: e.target.value }))}
                        style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                      />
                    </div>
                    <div style={{ flex: '1 1 120px' }}>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>TICKER</label>
                      <input 
                        type="text" 
                        placeholder="e.g. AAPL"
                        value={state.ticker || ''} 
                        onChange={(e) => setState(prev => ({ ...prev, ticker: e.target.value }))}
                        style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                    <div style={{ flex: '1 1 150px' }}>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>EVENT DATE</label>
                      <input 
                        type="date" 
                        value={state.eventDate || ''} 
                        onChange={(e) => setState(prev => ({ ...prev, eventDate: e.target.value }))}
                        style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                      />
                    </div>
                    <div style={{ flex: '1 1 150px' }}>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>EVENT TIME</label>
                      <input 
                        type="time" 
                        value={state.eventTime || ''} 
                        onChange={(e) => setState(prev => ({ ...prev, eventTime: e.target.value }))}
                        style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                      />
                    </div>
                    <div style={{ flex: '1 1 150px' }}>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>TIMEZONE</label>
                      <select 
                        value={state.timezone || 'UTC'} 
                        onChange={(e) => setState(prev => ({ ...prev, timezone: e.target.value }))}
                        style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                      >
                        <option value="UTC">UTC</option>
                        <option value="America/New_York">US Eastern (ET)</option>
                        <option value="America/Los_Angeles">US Pacific (PT)</option>
                        <option value="Europe/London">London</option>
                        <option value="Asia/Tokyo">Tokyo</option>
                      </select>
                    </div>
                  </div>
                </div>

                <div className="simulation-form" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                  {state.observations.map((obs, index) => (
                    <motion.div 
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.1 }}
                      key={index} 
                      style={{ 
                        border: '1px solid var(--line-strong)', 
                        padding: '24px', 
                        borderRadius: '12px', 
                        background: 'var(--bg)', 
                        boxShadow: '0 4px 12px rgba(0,0,0,0.03)' 
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px', alignItems: 'center' }}>
                        <div style={{ fontWeight: 600, fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text)' }}>
                          <div style={{ width: '24px', height: '24px', borderRadius: '50%', background: 'var(--line)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', color: 'var(--text)' }}>
                            {index + 1}
                          </div>
                          Observation Node
                        </div>
                        {state.observations.length > 1 && (
                          <button className="text-button text-button--danger" onClick={() => removeObservation(index)} style={{ padding: '4px 8px', borderRadius: '4px' }}>
                            <Trash2 size={14} /> Remove
                          </button>
                        )}
                      </div>
                      
                      <div style={{ display: 'flex', gap: '16px', marginBottom: '20px', flexWrap: 'wrap' }}>
                        <div style={{ flex: '1 1 200px' }}>
                          <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>SOURCE CHANNEL</label>
                          <select 
                            value={obs.channel} 
                            onChange={(e) => updateObservation(index, { channel: e.target.value as 'NEWS' | 'TWITTER_X_STYLE' })}
                            style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                          >
                            <option value="NEWS">Global News Wire</option>
                            <option value="TWITTER_X_STYLE">Social Media (Twitter/X)</option>
                          </select>
                        </div>
                        <div style={{ flex: '1 1 200px' }}>
                          <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>AUTHOR / ENTITY (Optional)</label>
                          <input 
                            type="text" 
                            placeholder={obs.channel === 'TWITTER_X_STYLE' ? '@username' : 'e.g. Bloomberg, Reuters'}
                            value={obs.author || ''} 
                            onChange={(e) => updateObservation(index, { author: e.target.value })}
                            style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                          />
                        </div>
                      </div>

                      <div style={{ marginBottom: '20px' }}>
                        <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>HEADLINE (Optional)</label>
                        <input 
                          type="text" 
                          placeholder="e.g. Major Sovereign Default Event Declared"
                          value={obs.headline || ''} 
                          onChange={(e) => updateObservation(index, { headline: e.target.value })}
                          style={{ width: '100%', padding: '10px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none' }}
                        />
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', letterSpacing: '0.05em' }}>OBSERVATION BODY (Required)</label>
                        <textarea 
                          placeholder="Paste full text, tweet body, or raw unstructured event data..."
                          value={obs.body || ''} 
                          onChange={(e) => updateObservation(index, { body: e.target.value })}
                          style={{ width: '100%', padding: '12px 14px', border: '1px solid var(--line-strong)', borderRadius: '8px', fontSize: '13px', minHeight: '120px', backgroundColor: 'var(--bg-raised)', color: 'var(--text)', outline: 'none', resize: 'vertical' }}
                        />
                      </div>
                    </motion.div>
                  ))}
                  
                  <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                    <button 
                      className="text-button" 
                      onClick={addObservation}
                      style={{ padding: '10px 20px', background: 'var(--bg-raised)', borderRadius: '8px', border: '1px dashed var(--line-strong)', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text)' }}
                    >
                      <Plus size={14} /> Append Observation Node
                    </button>
                  </div>

                  {state.submitError && <div style={{ marginTop: '8px' }}><ErrorState title="Submission failed" detail={state.submitError.message} /></div>}
                </div>
              </div>

              <div className="modal-footer" style={{ borderTop: '1px solid var(--line)', background: 'var(--bg-panel)' }}>
                <button 
                  onClick={() => setIsModalOpen(false)} 
                  disabled={state.submitting}
                  style={{ padding: '10px 18px', borderRadius: '6px', fontSize: '13px', fontWeight: 600, border: '1px solid var(--line-strong)', background: 'transparent', cursor: 'pointer', color: 'var(--text)' }}
                >
                  Cancel
                </button>
                <button 
                  onClick={handleSubmit} 
                  disabled={state.submitting}
                  style={{ background: 'var(--coral)', color: '#fff', padding: '10px 18px', borderRadius: '6px', fontSize: '13px', fontWeight: 600, cursor: state.submitting ? 'not-allowed' : 'pointer', border: 'none', display: 'flex', alignItems: 'center', gap: '8px', boxShadow: '0 4px 12px rgba(255, 92, 92, 0.2)' }}
                >
                  {state.submitting ? 'Submitting...' : 'Run Pipeline Analysis'}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {state.activeRunId ? (
        <SimulationRunView runId={state.activeRunId} run={run} loading={loading} connectionState={connectionState} streamError={streamError} retry={retry} onPromoteSuccess={onPromoteSuccess} />
      ) : (
        <EmptyState 
          title="No active simulation" 
          detail="Click 'Simulate Test' to supply synthetic observations and trace their impact through the pipeline." 
          icon={<Workflow size={18} />} 
        />
      )}
    </div>
  )
}

export interface GdeltWorkspaceState {
  query: string
  maxRecords: number
  submitting: boolean
  submitError: Error | null
  activeRunId: string | null
  resultCount: number | null
}

export function GdeltWorkspace({ state, setState, hideTitle, onPromoteSuccess }: { state: GdeltWorkspaceState, setState: React.Dispatch<React.SetStateAction<GdeltWorkspaceState>>, hideTitle?: boolean, onPromoteSuccess?: () => void }) {
  const { run, loading, connectionState, error: streamError, retry } = usePipelineStream(state.activeRunId)

  const [promoting, setPromoting] = useState(false)
  const [promotedData, setPromotedData] = useState<{ count: number, eventIds: string[] } | null>(null)
  const [promoteError, setPromoteError] = useState<Error | null>(null)

  const handlePromote = async () => {
    if (!state.activeRunId) return
    setPromoting(true)
    setPromoteError(null)
    try {
      const res = await promotePipelineRun(state.activeRunId)
      if (res.status === 'SUCCESS' || res.status === 'ALREADY_PROMOTED') {
        setPromotedData({ count: res.count, eventIds: res.promoted_event_ids })
        if (onPromoteSuccess) onPromoteSuccess()
      }
    } catch (e) {
      setPromoteError(e instanceof Error ? e : new Error('Promotion failed'))
    } finally {
      setPromoting(false)
    }
  }

  const isEligible = run?.status === 'COMPLETED' && run.final_result && Array.isArray((run.final_result as any).signals) && (run.final_result as any).signals.length > 0 && Array.isArray((run.final_result as any).stress_results) && (run.final_result as any).stress_results.length > 0


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!state.query.trim()) {
      setState(prev => ({ ...prev, submitError: new Error('Search query is required.') }))
      return
    }

    setState(prev => ({ ...prev, submitting: true, submitError: null, activeRunId: null, resultCount: null }))

    try {
      const res = await submitGdeltSearch({ query: state.query, max_records: state.maxRecords })
      setState(prev => ({ ...prev, activeRunId: res.run_id, resultCount: res.count }))
    } catch (err) {
      setState(prev => ({ ...prev, submitError: err instanceof Error ? err : new Error('Failed to submit GDELT search') }))
    } finally {
      setState(prev => ({ ...prev, submitting: false }))
    }
  }

  return (
    <div className={hideTitle ? "" : "workspace-stack"}>
      {!hideTitle && (
        <WorkspaceTitle 
          eyebrow="LIVE INTELLIGENCE / 09" 
          title="Live News Intelligence" 
          detail="Search the Global Database of Events, Language, and Tone (GDELT) 2.0 API. Records are normalized and processed through the NLP pipeline." 
          action={<IconBadge tone="mint"><Globe size={16} /></IconBadge>} 
        />
      )}

      <div className="workspace-grid workspace-grid--two-one" style={{ marginTop: hideTitle ? 0 : undefined }}>
        <SectionFrame eyebrow="SEARCH" title="News Query" meta={<StatusChip label="LIVE_GDELT" tone="mint" />}>
          <form className="simulation-form" onSubmit={handleSubmit}>
            <div style={{ border: '1px solid #E5E7EB', padding: '16px', marginBottom: '16px', borderRadius: '4px' }}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 'bold', color: '#6B7280', marginBottom: '4px' }}>QUERY</label>
                <input 
                  type="text" 
                  value={state.query} 
                  onChange={(e) => setState(prev => ({ ...prev, query: e.target.value }))}
                  placeholder='e.g., "supply chain" OR "chip shortage"'
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #D1D5DB', borderRadius: '4px', fontSize: '14px', backgroundColor: 'transparent' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 'bold', color: '#6B7280', marginBottom: '4px' }}>MAX RECORDS (1-250)</label>
                <input 
                  type="number" 
                  min={1}
                  max={250}
                  value={state.maxRecords} 
                  onChange={(e) => setState(prev => ({ ...prev, maxRecords: Number(e.target.value) }))}
                  style={{ width: '100%', padding: '8px 12px', border: '1px solid #D1D5DB', borderRadius: '4px', fontSize: '14px', backgroundColor: 'transparent' }}
                />
                <p style={{ fontSize: '11px', color: '#6B7280', marginTop: '6px' }}>GDELT 2.0 DOC API limit is 250 records per request.</p>
              </div>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button 
                type="submit"
                disabled={state.submitting}
                style={{ background: '#111827', color: 'white', padding: '8px 16px', borderRadius: '4px', fontSize: '13px', fontWeight: 'bold', cursor: state.submitting ? 'not-allowed' : 'pointer', border: 'none' }}
              >
                {state.submitting ? 'Searching GDELT...' : 'Search and Analyze'}
              </button>
            </div>

            {state.submitError && <div style={{ marginTop: '16px' }}><ErrorState title="Search failed" detail={state.submitError.message} /></div>}
          </form>
        </SectionFrame>

        <PipelineRunViewer
          activeRunId={state.activeRunId}
          run={run}
          loading={loading}
          connectionState={connectionState}
          streamError={streamError}
          retry={retry}
          emptyStateTitle="No active run"
          emptyStateDetail="Submit a query to fetch and process live news records."
          emptyStateIcon={<Search size={18} />}
          headerRight={
            <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
              {state.resultCount !== null && (
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7280' }}>DOCUMENTS</div>
                  <div style={{ fontSize: '13px', fontWeight: 'bold' }}>{state.resultCount}</div>
                </div>
              )}
              {isEligible && (
                promotedData ? (
                  <span style={{ fontSize: '12px', color: '#10B981', fontWeight: 'bold' }}><Check size={14} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> PROMOTED ({promotedData.count})</span>
                ) : (
                  <button 
                    className="text-button" 
                    onClick={handlePromote} 
                    disabled={promoting}
                    style={{ padding: '6px 12px', background: '#E5E7EB', borderRadius: '4px', color: '#374151', fontWeight: 'bold', fontSize: '11px', border: 'none', cursor: promoting ? 'not-allowed' : 'pointer' }}
                  >
                    {promoting ? 'PROMOTING...' : 'PROMOTE TO COMMAND CENTER'}
                  </button>
                )
              )}
            </div>
          }
        />
      </div>
    </div>
  )
}

export function SidebarBrand() {
  return <div className="sidebar-brand"><AppMark /><div className="sidebar-brand__meta"></div></div>
}

function PipelineRunViewerWrapper({ activeRunId, onPromoteSuccess }: { activeRunId: string, onPromoteSuccess?: () => void }) {
  const { run, loading, connectionState, error, retry } = usePipelineStream(activeRunId)
  
  const [promoting, setPromoting] = useState(false)
  const [promotedData, setPromotedData] = useState<{ count: number, eventIds: string[] } | null>(null)
  const [promoteError, setPromoteError] = useState<Error | null>(null)

  const handlePromote = async () => {
    if (!activeRunId) return
    setPromoting(true)
    setPromoteError(null)
    try {
      const res = await promotePipelineRun(activeRunId)
      if (res.status === 'SUCCESS' || res.status === 'ALREADY_PROMOTED') {
        setPromotedData({ count: res.count, eventIds: res.promoted_event_ids })
        if (onPromoteSuccess) onPromoteSuccess()
      }
    } catch (e) {
      setPromoteError(e instanceof Error ? e : new Error('Promotion failed'))
    } finally {
      setPromoting(false)
    }
  }

  const isEligible = run?.status === 'COMPLETED' && run.final_result && Array.isArray((run.final_result as any).signals) && (run.final_result as any).signals.length > 0 && Array.isArray((run.final_result as any).stress_results) && (run.final_result as any).stress_results.length > 0

  return (
    <div>
      <PipelineRunViewer
        activeRunId={activeRunId}
        run={run}
        loading={loading}
        connectionState={connectionState}
        streamError={error}
        retry={retry}
        emptyStateTitle="Run not found"
        emptyStateDetail="This run could not be found or has expired."
        emptyStateIcon={<Search size={18} />}
        headerRight={isEligible && (
          <div style={{ textAlign: 'right' }}>
            {promotedData ? (
              <span style={{ fontSize: '12px', color: '#10B981', fontWeight: 'bold' }}><Check size={14} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> PROMOTED ({promotedData.count})</span>
            ) : (
              <button 
                className="text-button" 
                onClick={handlePromote} 
                disabled={promoting}
                style={{ padding: '6px 12px', background: '#E5E7EB', borderRadius: '4px', color: '#374151', fontWeight: 'bold', fontSize: '11px', border: 'none', cursor: promoting ? 'not-allowed' : 'pointer' }}
              >
                {promoting ? 'PROMOTING...' : 'PROMOTE TO COMMAND CENTER'}
              </button>
            )}
          </div>
        )}
      />
      {promoteError && <div style={{ marginTop: '12px' }}><ErrorState title="Promotion Failed" detail={promoteError.message} /></div>}
    </div>
  )
}

export function PipelineRunsWorkspace() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const runsRequest = useCallback((signal: AbortSignal) => fetchPipelineRuns(signal), [])
  const { data, loading, error, reload } = useApiQuery('pipeline-runs', runsRequest)

  if (selectedRunId) {
    return (
      <div className="workspace-stack">
        <WorkspaceTitle 
          eyebrow="PIPELINE RUNS / 10" 
          title="Run Inspector" 
          detail={`Inspecting run ${selectedRunId.slice(0, 8)}... Returning to list retains run execution history.`} 
          action={<button className="text-button" onClick={() => setSelectedRunId(null)}><ArrowRight size={14} style={{transform: 'rotate(180deg)'}} /> Back to runs</button>} 
        />
        <PipelineRunViewerWrapper activeRunId={selectedRunId} />
      </div>
    )
  }

  return (
    <div className="workspace-stack">
      <WorkspaceTitle 
        eyebrow="PIPELINE RUNS / 10" 
        title="Runtime History" 
        detail="A list of pipeline runs retained by the current backend runtime." 
        action={<button className="text-button" onClick={reload}><Workflow size={14} /> Refresh list</button>} 
      />
      <DataGate loading={loading} error={error} empty={!data?.runs?.length} retry={reload}>
        {data && (
          <SectionFrame eyebrow="ALL RUNS" title="Execution Register" meta={<span className="meta-code">{data.runs.length} ROWS</span>}>
            <div className="event-feed">
              {data.runs.map((run: PipelineRun, index: number) => {
                const observations = run.request.observations?.length || 0;
                const source = run.request.observations?.[0]?.source || 'OTHER';
                const channel = run.request.observations?.[0]?.channel || '';
                const date = new Date(run.created_at).toLocaleString();

                return (
                  <button className="event-row" key={run.run_id} onClick={() => setSelectedRunId(run.run_id)}>
                    <div className="event-row__index">{String(index + 1).padStart(2, '0')}</div>
                    <div className="event-row__main">
                      <div className="event-row__headline">
                        <strong style={{fontFamily: 'monospace'}} title={run.run_id}>{run.run_id.slice(0, 8)}...</strong>
                        <span style={{ fontSize: '11px', padding: '2px 6px', background: '#E5E7EB', borderRadius: '4px' }}>{run.request.mode}</span>
                        <StatusChip label={run.status} tone={run.status === 'FAILED' ? 'danger' : run.status === 'COMPLETED' ? 'mint' : 'default'} />
                      </div>
                      <div className="event-row__detail">
                        {date} • {observations} observation{observations === 1 ? '' : 's'} ({source}{channel ? ` / ${channel}` : ''})
                      </div>
                    </div>
                    <ChevronRight className="event-row__arrow" size={16} />
                  </button>
                )
              })}
            </div>
          </SectionFrame>
        )}
      </DataGate>
    </div>
  )
}

export function ProvenanceWorkspace() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const runsRequest = useCallback((signal: AbortSignal) => fetchPipelineRuns(signal), [])
  const { data, loading, error, reload } = useApiQuery('pipeline-provenance', runsRequest)

  if (selectedRunId) {
    return (
      <div className="workspace-stack">
        <WorkspaceTitle 
          eyebrow="DATA PROVENANCE / 11" 
          title="Run Inspector" 
          detail={`Inspecting execution context for run ${selectedRunId.slice(0, 8)}...`} 
          action={<button className="text-button" onClick={() => setSelectedRunId(null)}><ArrowRight size={14} style={{transform: 'rotate(180deg)'}} /> Back to provenance</button>} 
        />
        <PipelineRunViewerWrapper activeRunId={selectedRunId} />
      </div>
    )
  }

  return (
    <div className="workspace-stack">
      <WorkspaceTitle 
        eyebrow="DATA PROVENANCE / 11" 
        title="Execution Provenance" 
        detail="Traceability and metadata for actual pipeline executions. Records are retained in active memory and will be cleared on process restart." 
        action={<button className="text-button" onClick={reload}><Workflow size={14} /> Refresh list</button>} 
      />

      <SectionFrame eyebrow="PROVENANCE TAXONOMY" title="Source & Integration Mapping">
        <div className="workspace-grid workspace-grid--two">
          <div>
            <h4 style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7280', marginBottom: '8px' }}>EXECUTION MODE</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>LIVE_GDELT</strong> Run initiated through the live GDELT API integration. Does not guarantee exhaustive news coverage.</div>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>ANALYST_SIMULATION</strong> User-supplied observations manually processed through the NLP pipeline.</div>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>HISTORICAL_REPLAY</strong> Historical-replay provenance. Launching replays is not currently supported in this UI.</div>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>SYNTHETIC_FIXTURE</strong> Synthetic fixture mode for testing portfolio impact behaviors.</div>
            </div>
          </div>
          <div>
            <h4 style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7280', marginBottom: '8px' }}>OBSERVATION SOURCE & CHANNEL</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>GDELT</strong> Data sourced from the GDELT Project.</div>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>HISTORICAL_SOCIAL</strong> Historical social media records.</div>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>ANALYST_SIMULATION</strong> Authored manually by an analyst.</div>
              <div><strong style={{ display: 'inline-block', width: '150px' }}>OTHER</strong> Other uncategorized observation sources.</div>
              <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #E5E7EB' }}>
                <div><strong style={{ display: 'inline-block', width: '150px' }}>TWITTER_X_STYLE</strong> Describes a channel/style constraint. <em>Not evidence of live Twitter/X ingestion.</em></div>
                <div><strong style={{ display: 'inline-block', width: '150px' }}>NEWS</strong> Traditional news channel style constraint.</div>
              </div>
            </div>
          </div>
        </div>
      </SectionFrame>

      <DataGate loading={loading} error={error} empty={!data?.runs?.length} retry={reload}>
        {data && (
          <SectionFrame eyebrow="TRACEABILITY LOG" title="Retained Executions" meta={<span className="meta-code">{data.runs.length} RECORDS</span>}>
            <div className="event-feed">
              {data.runs.map((run: PipelineRun) => {
                const observations = run.request.observations?.length || 0;
                
                const sources = Array.from(new Set(run.request.observations?.map((o: ObservationInput) => o.source).filter(Boolean)));
                const channels = Array.from(new Set(run.request.observations?.map((o: ObservationInput) => o.channel).filter(Boolean)));
                
                const date = new Date(run.created_at).toLocaleString();
                
                let durationStr = '';
                if (run.completed_at && run.created_at) {
                  const durationMs = new Date(run.completed_at).getTime() - new Date(run.created_at).getTime();
                  durationStr = ` • ${(durationMs / 1000).toFixed(1)}s execution`;
                }

                return (
                  <button className="event-row" key={run.run_id} onClick={() => setSelectedRunId(run.run_id)} style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-start', height: 'auto' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
                      <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                        <strong style={{fontFamily: 'monospace', fontSize: '13px'}} title={run.run_id}>{run.run_id.slice(0, 12)}...</strong>
                        <span style={{ fontSize: '11px', padding: '2px 6px', background: '#F3F4F6', color: '#374151', borderRadius: '4px', fontWeight: 'bold' }}>{run.request.mode}</span>
                        <StatusChip label={run.status} tone={run.status === 'FAILED' ? 'danger' : run.status === 'COMPLETED' ? 'mint' : 'default'} />
                      </div>
                      <ChevronRight size={16} color="#9CA3AF" />
                    </div>
                    
                    <div style={{ fontSize: '12px', color: '#6B7280', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                      <span><strong>CREATED:</strong> {date}{durationStr}</span>
                      <span><strong>OBSERVATIONS:</strong> {observations}</span>
                      {sources.length > 0 && <span><strong>SOURCE:</strong> {sources.join(', ')}</span>}
                      {channels.length > 0 && <span><strong>CHANNEL:</strong> {channels.join(', ')}</span>}
                    </div>
                  </button>
                )
              })}
            </div>
          </SectionFrame>
        )}
      </DataGate>
    </div>
  )
}

export function IntelligenceWorkspace({ 
  simulationState, setSimulationState, 
  gdeltState, setGdeltState,
  onPromoteSuccess
}: { 
  simulationState: SimulationWorkspaceState, setSimulationState: React.Dispatch<React.SetStateAction<SimulationWorkspaceState>>,
  gdeltState: GdeltWorkspaceState, setGdeltState: React.Dispatch<React.SetStateAction<GdeltWorkspaceState>>,
  onPromoteSuccess?: () => void
}) {
  const [activeTab, setActiveTab] = useState<'sandbox' | 'gdelt'>('sandbox')

  return (
    <div className="workspace-stack">
      <WorkspaceTitle 
        eyebrow="INTELLIGENCE LAB / 03" 
        title="Intelligence Lab" 
        detail="Unified workspace for Analyst Simulation Sandbox and Live News Search (GDELT)." 
        action={
          <div style={{ display: 'flex', gap: '8px', background: 'var(--bg-raised)', padding: '4px', borderRadius: '8px', border: '1px solid var(--line-strong)' }}>
            <button 
              onClick={() => setActiveTab('sandbox')} 
              style={{ padding: '6px 16px', borderRadius: '4px', fontSize: '13px', fontWeight: 600, border: 'none', background: activeTab === 'sandbox' ? 'var(--bg-panel)' : 'transparent', color: activeTab === 'sandbox' ? 'var(--text)' : 'var(--muted)', cursor: 'pointer', boxShadow: activeTab === 'sandbox' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none' }}
            >
              Analyst Sandbox
            </button>
            <button 
              onClick={() => setActiveTab('gdelt')} 
              style={{ padding: '6px 16px', borderRadius: '4px', fontSize: '13px', fontWeight: 600, border: 'none', background: activeTab === 'gdelt' ? 'var(--bg-panel)' : 'transparent', color: activeTab === 'gdelt' ? 'var(--text)' : 'var(--muted)', cursor: 'pointer', boxShadow: activeTab === 'gdelt' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none' }}
            >
              News Search (GDELT)
            </button>
          </div>
        } 
      />
      <div style={{ marginTop: '8px' }}>
        {activeTab === 'sandbox' ? (
          <SimulationWorkspace state={simulationState} setState={setSimulationState} hideTitle onPromoteSuccess={onPromoteSuccess} />
        ) : (
          <GdeltWorkspace state={gdeltState} setState={setGdeltState} hideTitle onPromoteSuccess={onPromoteSuccess} />
        )}
      </div>
    </div>
  )
}
