import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, BarChart3, BellRing, Command, GitCompareArrows, Layers3, Menu, Network, Search, Settings2, Siren } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { fetchEvents, fetchPortfolio, fetchScenarioAttribution, fetchScenarioComparison, fetchScenarioOverview, unwrapEvents, unwrapData } from './lib/api'
import { useApiQuery } from './hooks/useApi'
import type { EventSummary, Workspace } from './types/api'
import { prettyLabel } from './lib/format'
import { AppMark, Kicker } from './components/ui'
import { AttributionWorkspace, CommandCenter, ComparisonWorkspace, EventsWorkspace, InvestigationWorkspace, PortfolioWorkspace, SidebarBrand, StressLabWorkspace } from './components/workspaces'

const navItems: Array<{ id: Workspace; label: string; code: string; icon: typeof Activity }> = [
  { id: 'command', label: 'Command center', code: '01', icon: Command },
  { id: 'portfolio', label: 'Portfolio overview', code: '02', icon: BarChart3 },
  { id: 'events', label: 'Event intelligence', code: '03', icon: BellRing },
  { id: 'investigation', label: 'Investigation', code: '04', icon: Search },
  { id: 'stress', label: 'Stress lab', code: '05', icon: Siren },
  { id: 'attribution', label: 'Exposure attribution', code: '06', icon: Layers3 },
  { id: 'comparison', label: 'Scenario comparison', code: '07', icon: GitCompareArrows },
]

function initialWorkspace(): Workspace {
  const path = window.location.pathname
  return navItems.find((item) => `/${item.id === 'command' ? '' : item.id}` === path)?.id ?? 'command'
}

export default function App() {
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace>(initialWorkspace)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  const portfolioRequest = useCallback((signal: AbortSignal) => fetchPortfolio(signal), [])
  const eventsRequest = useCallback((signal: AbortSignal) => fetchEvents(signal).then(unwrapEvents), [])
  const portfolioQuery = useApiQuery('portfolio', portfolioRequest)
  const eventsQuery = useApiQuery('events', eventsRequest)

  useEffect(() => {
    if (!selectedEventId && eventsQuery.data?.length) setSelectedEventId(eventsQuery.data[0].event_id)
  }, [eventsQuery.data, selectedEventId])

  const selectedEvent = useMemo(() => eventsQuery.data?.find((event) => event.event_id === selectedEventId) ?? null, [eventsQuery.data, selectedEventId])
  const secondEvent = useMemo(() => eventsQuery.data?.find((event) => event.event_id !== selectedEventId) ?? null, [eventsQuery.data, selectedEventId])
  const overviewRequest = useCallback((signal: AbortSignal) => selectedEventId ? fetchScenarioOverview(selectedEventId, signal).then(unwrapData) : Promise.reject(new Error('No event selected')), [selectedEventId])
  const attributionRequest = useCallback((signal: AbortSignal) => selectedEventId ? fetchScenarioAttribution(selectedEventId, signal).then(unwrapData) : Promise.reject(new Error('No event selected')), [selectedEventId])
  const comparisonRequest = useCallback((signal: AbortSignal) => selectedEventId && secondEvent ? fetchScenarioComparison(selectedEventId, secondEvent.event_id, signal).then(unwrapData) : Promise.reject(new Error('Two events are required')), [secondEvent, selectedEventId])

  const overviewQuery = useApiQuery(`scenario-${selectedEventId ?? 'none'}`, overviewRequest, Boolean(selectedEventId) && ['investigation', 'stress'].includes(activeWorkspace))
  const attributionQuery = useApiQuery(`attribution-${selectedEventId ?? 'none'}`, attributionRequest, Boolean(selectedEventId) && ['investigation', 'attribution'].includes(activeWorkspace))
  const comparisonQuery = useApiQuery(`comparison-${selectedEventId ?? 'none'}-${secondEvent?.event_id ?? 'none'}`, comparisonRequest, activeWorkspace === 'comparison' && Boolean(selectedEventId && secondEvent))

  const navigate = useCallback((workspace: Workspace) => {
    setActiveWorkspace(workspace)
    setMobileNavOpen(false)
    const path = workspace === 'command' ? '/' : `/${workspace}`
    if (window.location.pathname !== path) window.history.pushState({ workspace }, '', path)
  }, [])

  const selectEvent = useCallback((eventId: string) => {
    setSelectedEventId(eventId)
    navigate('investigation')
  }, [navigate])

  useEffect(() => {
    const onPopState = () => setActiveWorkspace(initialWorkspace())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        navigate('events')
      }
      if (event.key >= '1' && event.key <= '7' && !event.metaKey && !event.ctrlKey && !(event.target instanceof HTMLInputElement)) {
        const target = navItems[Number(event.key) - 1]
        if (target) navigate(target.id)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [navigate])

  const workspace = (() => {
    switch (activeWorkspace) {
      case 'portfolio': return <PortfolioWorkspace portfolio={portfolioQuery.data} loading={portfolioQuery.loading} error={portfolioQuery.error} retry={portfolioQuery.reload} />
      case 'events': return <EventsWorkspace events={eventsQuery.data ?? []} loading={eventsQuery.loading} error={eventsQuery.error} retry={eventsQuery.reload} selectedId={selectedEventId} onSelect={selectEvent} />
      case 'investigation': return <InvestigationWorkspace event={selectedEvent} overview={overviewQuery.data} overviewLoading={overviewQuery.loading} overviewError={overviewQuery.error} overviewRetry={overviewQuery.reload} attribution={attributionQuery.data} attributionLoading={attributionQuery.loading} attributionError={attributionQuery.error} attributionRetry={attributionQuery.reload} onNavigate={navigate} />
      case 'stress': return <StressLabWorkspace event={selectedEvent} overview={overviewQuery.data} loading={overviewQuery.loading} error={overviewQuery.error} retry={overviewQuery.reload} />
      case 'attribution': return <AttributionWorkspace event={selectedEvent} attribution={attributionQuery.data} loading={attributionQuery.loading} error={attributionQuery.error} retry={attributionQuery.reload} />
      case 'comparison': return <ComparisonWorkspace eventA={selectedEvent} eventB={secondEvent} comparison={comparisonQuery.data} loading={comparisonQuery.loading} error={comparisonQuery.error} retry={comparisonQuery.reload} onSelectPair={() => navigate('events')} />
      default: return <CommandCenter portfolio={portfolioQuery.data} portfolioLoading={portfolioQuery.loading} portfolioError={portfolioQuery.error} portfolioRetry={portfolioQuery.reload} events={eventsQuery.data ?? []} eventsLoading={eventsQuery.loading} eventsError={eventsQuery.error} eventsRetry={eventsQuery.reload} onSelectEvent={selectEvent} onNavigate={navigate} />
    }
  })()

  return <div className="app-shell">
    <AnimatePresence>{mobileNavOpen && <motion.button className="mobile-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileNavOpen(false)} aria-label="Close navigation" />}</AnimatePresence>
    <aside className={`sidebar ${mobileNavOpen ? 'sidebar--open' : ''}`}>
      <SidebarBrand />
      <div className="sidebar-section-label">WORKSPACES</div>
      <nav className="sidebar-nav" aria-label="Primary navigation">{navItems.map((item) => { const Icon = item.icon; return <button key={item.id} className={`nav-item ${activeWorkspace === item.id ? 'nav-item--active' : ''}`} onClick={() => navigate(item.id)}><Icon size={16} /><span>{item.label}</span><kbd>{item.code}</kbd></button> })}</nav>
      <div className="sidebar-bottom"><div className="sidebar-status"><span className="live-dot" />API LINK <span>·</span> {portfolioQuery.error || eventsQuery.error ? 'DEGRADED' : 'STANDBY'}</div><div className="sidebar-utilities"><button title="Open command palette" onClick={() => navigate('events')}><Search size={15} /><span>Command search</span><kbd>⌘K</kbd></button><button title="Settings"><Settings2 size={15} /><span>System settings</span></button></div></div>
    </aside>
    <main className="main-canvas">
      <div className="hackathon-strip"><div className="hackathon-strip__brand"><span className="partner-mark" style={{marginRight: '12px', paddingTop: '5px'}}>Code to Connect</span><span className="partner-mark partner-mark--sp">S&amp;P Global</span><span className="partner-divider" /><span className="partner-mark partner-mark--crisil">Crisil</span></div><div className="hackathon-strip__status"><span className="live-dot" /> CASE STUDY / RESEARCH SYSTEM</div></div>
      <header className="topbar"><div className="topbar__left"><button className="mobile-menu-button" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation"><Menu size={18} /></button><div className="topbar-breadcrumb"><span>RISK PULSE</span><span>/</span><strong>{prettyLabel(activeWorkspace)}</strong></div></div><div className="topbar__right"><span className="topbar-status"><span className="live-dot" /> LIVE CONTRACT</span><span className="topbar-divider" /><span className="topbar-meta">PORTFOLIO / DEFAULT</span><button className="topbar-icon" title="System notifications"><Network size={16} /></button></div></header>
      <div className="page-canvas"><AnimatePresence mode="wait"><motion.div key={activeWorkspace} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18 }}>{workspace}</motion.div></AnimatePresence></div>
      
    </main>
  </div>
}
