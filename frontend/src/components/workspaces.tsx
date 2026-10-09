import { AnimatePresence, motion } from 'framer-motion'
import { Activity, ArrowDownRight, ArrowRight, BarChart3, BookOpen, Check, ChevronRight, Database, Filter, Focus, GitCompareArrows, Globe, Layers3, Network, Plus, Search, Siren, Sparkles, Target, Trash2, TrendingDown, Workflow } from 'lucide-react'
import { useCallback, useState, type ReactNode } from 'react'
import type { AnalystObservation, EventStressOverviewData, EventSummary, PortfolioOverviewData, RiskAttributionData, ScenarioComparisonData, Workspace, PipelineRun, ObservationInput } from '../types/api'
import { useApiQuery } from '../hooks/useApi'
import { submitAnalystSimulation, submitGdeltSearch, fetchPipelineRuns, promotePipelineRun } from '../lib/api'
import { usePipelineStream } from '../hooks/usePipelineStream'
import { formatMoney, formatPct, formatScore, formatSignedPct, impactTone, numeric, prettyLabel, sentimentLabel } from '../lib/format'
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

export function CommandCenter({ portfolio, portfolioLoading, portfolioError, portfolioRetry, events, eventsLoading, eventsError, eventsRetry, onSelectEvent, onNavigate }: {
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
}) {
  return <div className="workspace-stack">
    <WorkspaceTitle eyebrow="COMMAND CENTER / 01" title="Portfolio at a glance." detail="A compact read on what is exposed, what is moving, and where the next research case starts." action={<div className="command-signal"><SignalLine /><span>RISK SIGNAL</span></div>} />
    <DataGate loading={portfolioLoading} error={portfolioError} empty={!portfolio?.data} retry={portfolioRetry}>
      {portfolio && <div className="hero-readout"><div><div className="hero-readout__label">Total Exposure at Default</div><div className="hero-readout__value">{formatMoney(portfolio.data.total_ead)}</div><div className="hero-readout__meta">{portfolio.data.exposure_count} exposures · {portfolio.data.obligor_count} obligors</div></div><div className="hero-readout__signal"><SignalLine /><div className="hero-readout__ticks"><span>EXPOSURE FIELD</span><span>CONCENTRATION / READ-ONLY</span></div></div></div>}
    </DataGate>
    <div className="metric-grid metric-grid--four"><MetricBlock label="EXPOSURES" value={portfolio?.data.exposure_count ?? '—'} note="portfolio count" /><MetricBlock label="OBLIGORS" value={portfolio?.data.obligor_count ?? '—'} note="named counterparties" /><MetricBlock label="EVENT FEED" value={eventsLoading ? '…' : events.length || '—'} note="returned by API" tone={events.length ? 'amber' : 'default'} /><MetricBlock label="DATA LINK" value={portfolioError || eventsError ? 'DEGRADED' : 'READY'} note={portfolioError || eventsError ? 'check endpoint status' : 'contract connected'} tone={portfolioError || eventsError ? 'danger' : 'mint'} />
    </div>
    <div className="workspace-grid workspace-grid--two-one"><SectionFrame eyebrow="EVENT INTELLIGENCE" title="Open risk cases" meta={<button className="text-button" onClick={() => onNavigate('events')}>View full feed <ArrowRight size={14} /></button>}><DataGate loading={eventsLoading} error={eventsError} empty={!events.length} retry={eventsRetry}>{<div className="mini-event-list">{events.slice(0, 4).map((event) => <button className="mini-event" key={event.event_id} onClick={() => onSelectEvent(event.event_id)}><span className={`mini-event__score mini-event__score--${impactTone(event.impact_tier)}`}>{formatScore(event.impact_score)}</span><span className="mini-event__body"><strong>{event.entity}</strong><span>{prettyLabel(event.event_type)} · {prettyLabel(event.impact_tier)}</span></span><ChevronRight size={15} /></button>)}</div>}</DataGate></SectionFrame><SectionFrame eyebrow="CONCENTRATION" title="Where the book leans" meta={<button className="text-button" onClick={() => onNavigate('portfolio')}>Inspect portfolio <ArrowRight size={14} /></button>}>{portfolio ? <><div className="signal-list">{portfolio.data.concentration_indicators.slice(0, 4).map((indicator) => <div className="signal-list__item" key={indicator}><span className="signal-list__mark" /><span>{indicator}</span></div>)}</div><div className="mini-bars"><RankedBars rows={portfolio.data.sector_distribution} limit={4} /></div></> : <EmptyState title="Awaiting portfolio data" detail="Concentration indicators will appear when the portfolio contract responds." />}</SectionFrame></div>
    <div className="footer-ribbon"><span>RISK PULSE</span><span>SELECT A CASE TO TRACE IMPACT THROUGH THE BOOK <ArrowRight size={13} /></span></div>
  </div>
}

export function EventsWorkspace({ events, loading, error, retry, selectedId, onSelect }: { events: EventSummary[]; loading: boolean; error: Error | null; retry: () => void; selectedId: string | null; onSelect: (id: string) => void }) {
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="EVENT INTELLIGENCE / 03" title="Risk, in sequence." detail="A research feed for material signals. Open a case to trace its stress path through the book." action={<button className="filter-button"><Filter size={14} /> Filter view</button>} /><SectionFrame eyebrow="LIVE EVENT REGISTER" title="Risk event feed" meta={<SourceStamp schema="EVENTS" />}><DataGate loading={loading} error={error} empty={!events.length} retry={retry}>{<div className="event-feed">{events.map((event, index) => <motion.button initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} className={`event-row ${selectedId === event.event_id ? 'event-row--selected' : ''}`} key={event.event_id} onClick={() => onSelect(event.event_id)}><div className="event-row__index">{String(index + 1).padStart(2, '0')}</div><div className={`event-row__score event-row__score--${impactTone(event.impact_tier)}`}><span>{formatScore(event.impact_score)}</span><small>IMPACT</small></div><div className="event-row__main"><div className="event-row__headline"><strong>{event.entity}</strong><span>{prettyLabel(event.event_type)}</span><StatusChip label={event.impact_tier} />{event.provenance && <span style={{ marginLeft: '8px', fontSize: '10px', padding: '2px 4px', background: '#F3F4F6', color: '#6B7280', borderRadius: '4px' }}>{event.provenance}</span>}</div><div className="event-row__detail">{event.deterministic_rationale || 'Deterministic rationale not returned by the API.'}</div></div><div className="event-row__facts"><span>{prettyLabel(sentimentLabel(event.sentiment))} SENTIMENT</span><span>{event.shock_scope ? prettyLabel(event.shock_scope) : 'SCOPE NOT RETURNED'}</span></div><ChevronRight className="event-row__arrow" size={16} /></motion.button>)}</div>}</DataGate></SectionFrame></div>
}

export function PortfolioWorkspace({ portfolio, loading, error, retry }: { portfolio: { data: PortfolioOverviewData; generated_at?: string; schema_version?: string } | null; loading: boolean; error: Error | null; retry: () => void }) {
  const data = portfolio?.data
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="PORTFOLIO / 02" title="The book, under a lens." detail="Concentration and obligor structure from the portfolio contract — ranked to keep attention on materiality." action={portfolio && <SourceStamp generatedAt={portfolio.generated_at} schema={portfolio.schema_version} />} /><DataGate loading={loading} error={error} empty={!data} retry={retry}>{data && <><div className="metric-grid metric-grid--four"><MetricBlock label="TOTAL EAD" value={formatMoney(data.total_ead)} note="exposure at default" tone="mint" /><MetricBlock label="EXPOSURES" value={data.exposure_count} note="portfolio count" /><MetricBlock label="OBLIGORS" value={data.obligor_count} note="named counterparties" /><MetricBlock label="INDICATORS" value={data.concentration_indicators.length} note="returned by API" /></div><div className="workspace-grid workspace-grid--one-two"><SectionFrame eyebrow="SECTOR × EAD" title="Concentration field" meta={<span className="meta-code">RANKED / ABSOLUTE</span>}><RankedBars rows={data.sector_distribution} limit={8} /></SectionFrame><SectionFrame eyebrow="TOP OBLIGORS" title="Material counterparties" meta={<span className="meta-code">EAD + SHARE</span>}><div className="obligor-list">{data.top_obligors.slice(0, 8).map((row, index) => <div className="obligor-row" key={`${row.obligor}-${index}`}><span className="obligor-row__rank">{String(index + 1).padStart(2, '0')}</span><span className="obligor-row__name">{row.obligor}</span><span className="obligor-row__pct">{formatPct(row.pct)}</span><span className="obligor-row__ead">{formatMoney(row.ead)}</span></div>)}</div></SectionFrame></div><div className="workspace-grid workspace-grid--three"><SectionFrame eyebrow="GEOGRAPHY" title="Geographic concentration"><RankedBars rows={data.geography_distribution} limit={7} /></SectionFrame><SectionFrame eyebrow="RATING PROFILE" title="Rating distribution"><div className="rating-strip"><InlineStack rows={data.rating_distribution} /></div><div className="legend-list">{data.rating_distribution.map((row) => <div key={row.name}><span className="legend-list__swatch" /><span>{row.name}</span><strong>{formatMoney(row.ead)}</strong></div>)}</div></SectionFrame><SectionFrame eyebrow="CONCENTRATION SIGNALS" title="Indicators"><div className="signal-list">{data.concentration_indicators.map((indicator) => <div className="signal-list__item" key={indicator}><span className="signal-list__mark" /><span>{indicator}</span></div>)}</div></SectionFrame></div></>}</DataGate></div>
}

export function InvestigationWorkspace({ event, overview, overviewLoading, overviewError, overviewRetry, attribution, attributionLoading, attributionError, attributionRetry, onNavigate }: { event: EventSummary | null; overview: EventStressOverviewData | null; overviewLoading: boolean; overviewError: Error | null; overviewRetry: () => void; attribution: RiskAttributionData | null; attributionLoading: boolean; attributionError: Error | null; attributionRetry: () => void; onNavigate: (workspace: Workspace) => void }) {
  return <div className="workspace-stack"><WorkspaceTitle eyebrow="CASE FILE / 04" title={event ? `${event.entity} — investigation` : 'Open a research case.'} detail={event ? `${prettyLabel(event.event_type)} · event ${event.event_id}` : 'Select a risk event from the feed to load its scenario overview.'} action={event && <StatusChip label={event.impact_tier} />} />{!event ? <EmptyState title="No case selected" detail="Open an event from Event Intelligence to populate the investigation workspace." icon={<Search size={18} />} /> : <><DataGate loading={overviewLoading} error={overviewError} empty={!overview} retry={overviewRetry}>{overview && <div className="investigation-hero"><div className="investigation-hero__narrative"><div className="section-eyebrow">DETERMINISTIC RATIONALE</div><p>{overview.deterministic_rationale}</p><div className="narrative-meta"><span><b>ENTITY</b>{overview.entity}</span><span><b>EVENT TYPE</b>{prettyLabel(overview.event_type)}</span><span><b>SENTIMENT</b>{prettyLabel(sentimentLabel(overview.sentiment))}</span></div></div><RiskGauge score={overview.impact_score} tier={overview.impact_tier} /></div>}</DataGate><DataGate loading={overviewLoading} error={overviewError} empty={!overview} retry={overviewRetry}>{overview && <><div className="metric-grid metric-grid--four"><MetricBlock label="AFFECTED EAD" value={formatMoney(overview.affected_ead)} note={formatPct(overview.affected_ead_pct)} tone="amber" /><MetricBlock label="INCREMENTAL EL" value={formatMoney(overview.incremental_el)} note="stress output" tone="danger" /><MetricBlock label="MTM IMPACT" value={formatMoney(overview.mtm_impact)} note="valuation output" tone="danger" /><MetricBlock label="SHOCK SCOPE" value={prettyLabel(overview.shock_scope)} note={overview.stress_applied ? 'stress applied' : 'stress not applied'} /></div><SectionFrame eyebrow="IMPACT TRACE" title="What moved, and where." meta={<button className="text-button" onClick={() => onNavigate('stress')}>Open Stress Lab <ArrowRight size={14} /></button>}><div className="impact-trace"><div><span>EVENT</span><strong>{prettyLabel(overview.event_type)}</strong><small>{formatScore(overview.impact_score)} impact</small></div><ArrowRight /><div><span>PORTFOLIO</span><strong>{formatPct(overview.affected_ead_pct)} EAD</strong><small>{formatMoney(overview.affected_ead)} affected</small></div><ArrowRight /><div><span>LOSS</span><strong>{formatMoney(overview.incremental_el)}</strong><small>incremental EL</small></div><ArrowRight /><div><span>VALUATION</span><strong>{formatMoney(overview.mtm_impact)}</strong><small>MTM impact</small></div></div></SectionFrame></>}</DataGate><div className="workspace-grid workspace-grid--two-one"><SectionFrame eyebrow="EXPOSURE ATTRIBUTION" title="Primary contributors" meta={<button className="text-button" onClick={() => onNavigate('attribution')}>Full attribution <ArrowRight size={14} /></button>}><DataGate loading={attributionLoading} error={attributionError} empty={!attribution} retry={attributionRetry}>{attribution && <ContributionBars rows={attribution.by_sector} valueKey="incremental_el" limit={5} />}</DataGate></SectionFrame><SectionFrame eyebrow="RESEARCH CONTEXT" title="Affected book"><DataGate loading={attributionLoading} error={attributionError} empty={!attribution} retry={attributionRetry}>{attribution && <div className="affected-stack"><div className="affected-stack__headline">{attribution.by_exposure.filter((row) => row.is_affected).length}<span> affected exposures</span></div><div className="affected-stack__meta">{attribution.by_exposure.length} rows returned · API-linked only</div><div className="affected-stack__line"><SignalLine variant="coral" /></div></div>}</DataGate></SectionFrame></div></>}</div>
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
  observations: AnalystObservation[]
  submitting: boolean
  submitError: Error | null
  activeRunId: string | null
}

export function SimulationWorkspace({ state, setState }: { state: SimulationWorkspaceState, setState: React.Dispatch<React.SetStateAction<SimulationWorkspaceState>> }) {
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

    setState(prev => ({ ...prev, submitting: true, submitError: null, activeRunId: null }))

    try {
      const res = await submitAnalystSimulation({ mode: 'ANALYST_SIMULATION', observations: state.observations })
      setState(prev => ({ ...prev, activeRunId: res.run_id }))
    } catch (e) {
      setState(prev => ({ ...prev, submitError: e instanceof Error ? e : new Error('Failed to submit simulation') }))
    } finally {
      setState(prev => ({ ...prev, submitting: false }))
    }
  }

  return (
    <div className="workspace-stack">
      <WorkspaceTitle 
        eyebrow="INTELLIGENCE LAB / 08" 
        title="Analyst Simulation" 
        detail="Submit simulated observations to the pipeline. Label explicitly as ANALYST_SIMULATION." 
        action={<IconBadge tone="amber"><Activity size={16} /></IconBadge>} 
      />

      <div className="workspace-grid workspace-grid--two-one">
        <SectionFrame eyebrow="INPUT" title="Simulated Observations" meta={<StatusChip label="ANALYST_SIMULATION" tone="amber" />}>
          <div className="simulation-form">
            {state.observations.map((obs, index) => (
              <div key={index} style={{ border: '1px solid #E5E7EB', padding: '16px', marginBottom: '12px', borderRadius: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div style={{ fontWeight: 'bold' }}>Observation {index + 1}</div>
                  {state.observations.length > 1 && <button className="text-button text-button--danger" onClick={() => removeObservation(index)}><Trash2 size={14} /> Remove</button>}
                </div>
                
                <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 'bold', color: '#6B7280', marginBottom: '4px' }}>CHANNEL</label>
                    <select 
                      value={obs.channel} 
                      onChange={(e) => updateObservation(index, { channel: e.target.value as 'NEWS' | 'TWITTER_X_STYLE' })}
                      style={{ width: '100%', padding: '6px 8px', border: '1px solid #D1D5DB', borderRadius: '4px', fontSize: '13px', backgroundColor: 'transparent' }}
                    >
                      <option value="NEWS">NEWS</option>
                      <option value="TWITTER_X_STYLE">TWITTER_X_STYLE</option>
                    </select>
                  </div>
                  {obs.channel === 'TWITTER_X_STYLE' && (
                    <div style={{ flex: 1 }}>
                      <AlertNote>User supplies simulated social text. No live Twitter/X ingestion occurs.</AlertNote>
                    </div>
                  )}
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 'bold', color: '#6B7280', marginBottom: '4px' }}>HEADLINE (Optional)</label>
                  <input 
                    type="text" 
                    value={obs.headline || ''} 
                    onChange={(e) => updateObservation(index, { headline: e.target.value })}
                    style={{ width: '100%', padding: '6px 8px', border: '1px solid #D1D5DB', borderRadius: '4px', fontSize: '13px', backgroundColor: 'transparent' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 'bold', color: '#6B7280', marginBottom: '4px' }}>BODY</label>
                  <textarea 
                    value={obs.body || ''} 
                    onChange={(e) => updateObservation(index, { body: e.target.value })}
                    style={{ width: '100%', padding: '6px 8px', border: '1px solid #D1D5DB', borderRadius: '4px', fontSize: '13px', minHeight: '80px', backgroundColor: 'transparent' }}
                  />
                </div>
              </div>
            ))}
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
              <button className="text-button" onClick={addObservation}><Plus size={14} /> Add observation</button>
              <button 
                onClick={handleSubmit} 
                disabled={state.submitting}
                style={{ background: '#111827', color: 'white', padding: '8px 16px', borderRadius: '4px', fontSize: '13px', fontWeight: 'bold', cursor: state.submitting ? 'not-allowed' : 'pointer', border: 'none' }}
              >
                {state.submitting ? 'Submitting...' : 'Submit to Pipeline'}
              </button>
            </div>

            {state.submitError && <div style={{ marginTop: '16px' }}><ErrorState title="Submission failed" detail={state.submitError.message} /></div>}
          </div>
        </SectionFrame>

        <PipelineRunViewer
          activeRunId={state.activeRunId}
          run={run}
          loading={loading}
          connectionState={connectionState}
          streamError={streamError}
          retry={retry}
          emptyStateTitle="No active run"
          emptyStateDetail="Submit observations to start the pipeline orchestrator."
          emptyStateIcon={<Workflow size={18} />}
        />
      </div>
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

export function GdeltWorkspace({ state, setState }: { state: GdeltWorkspaceState, setState: React.Dispatch<React.SetStateAction<GdeltWorkspaceState>> }) {
  const { run, loading, connectionState, error: streamError, retry } = usePipelineStream(state.activeRunId)

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
    <div className="workspace-stack">
      <WorkspaceTitle 
        eyebrow="LIVE INTELLIGENCE / 09" 
        title="Live News Intelligence" 
        detail="Search the Global Database of Events, Language, and Tone (GDELT) 2.0 API. Records are normalized and processed through the NLP pipeline." 
        action={<IconBadge tone="mint"><Globe size={16} /></IconBadge>} 
      />

      <div className="workspace-grid workspace-grid--two-one">
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
          headerRight={state.resultCount !== null ? (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#6B7280' }}>DOCUMENTS</div>
              <div style={{ fontSize: '13px', fontWeight: 'bold' }}>{state.resultCount}</div>
            </div>
          ) : undefined}
        />
      </div>
    </div>
  )
}

export function SidebarBrand() {
  return <div className="sidebar-brand"><AppMark /><div className="sidebar-brand__meta"></div></div>
}

function PipelineRunViewerWrapper({ activeRunId }: { activeRunId: string }) {
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
