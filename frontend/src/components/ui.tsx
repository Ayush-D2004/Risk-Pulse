import { motion } from 'framer-motion'
import { AlertTriangle, ArrowUpRight, CircleHelp, RefreshCw, ShieldAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { impactTone, prettyLabel } from '../lib/format'

export function AppMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`app-mark ${compact ? 'app-mark--compact' : ''}`} aria-label="RiskPulse">
      <span className="mark-signal" aria-hidden="true"><i /><i /><i /></span>
      {!compact && <span className="mark-word">Risk<span>Pulse</span></span>}
    </div>
  )
}

export function Kicker({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'danger' | 'mint' }) {
  return <div className={`kicker kicker--${tone}`}><span className="kicker-dot" />{children}</div>
}

export function StatusChip({ label, tone, className = '' }: { label: string; tone?: string; className?: string }) {
  const semanticTone = tone ?? impactTone(label)
  return <span className={`status-chip status-chip--${semanticTone} ${className}`}><span className="status-chip__dot" />{prettyLabel(label)}</span>
}

export function MetricBlock({ label, value, note, tone = 'default', align = 'left' }: { label: string; value: ReactNode; note?: ReactNode; tone?: 'default' | 'danger' | 'mint' | 'amber'; align?: 'left' | 'right' }) {
  return (
    <div className={`metric-block metric-block--${tone} metric-block--${align}`}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {note && <div className="metric-note">{note}</div>}
    </div>
  )
}

export function SectionFrame({ eyebrow, title, meta, children, className = '' }: { eyebrow?: string; title: string; meta?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`section-frame ${className}`}>
      <div className="section-frame__head">
        <div>
          {eyebrow && <div className="section-eyebrow">{eyebrow}</div>}
          <h2>{title}</h2>
        </div>
        {meta && <div className="section-frame__meta">{meta}</div>}
      </div>
      {children}
    </section>
  )
}

export function SignalLine({ variant = 'coral' }: { variant?: 'coral' | 'mint' | 'amber' }) {
  return <svg className={`signal-line signal-line--${variant}`} viewBox="0 0 220 38" preserveAspectRatio="none" aria-hidden="true"><path d="M0 25h32l10-16 12 23 17-20 12 9 17-12 15 10 14-4 10 8 18-13 14 8 12-5 12 4 14-6 11 3h24" /><path className="signal-line__ghost" d="M0 31h40l14-7 18 4 18-10 18 6 16-3 14 4 18-5 20 4 17-3 17 4 12-2" /></svg>
}

export function EmptyState({ title, detail, icon = <CircleHelp size={18} /> }: { title: string; detail: string; icon?: ReactNode }) {
  return <div className="state-panel state-panel--empty"><div className="state-panel__icon">{icon}</div><div><h3>{title}</h3><p>{detail}</p></div></div>
}

export function ErrorState({ title = 'Data unavailable', detail, onRetry }: { title?: string; detail: string; onRetry?: () => void }) {
  return <div className="state-panel state-panel--error"><div className="state-panel__icon"><ShieldAlert size={18} /></div><div><h3>{title}</h3><p>{detail}</p>{onRetry && <button className="text-button" onClick={onRetry}><RefreshCw size={14} />Retry request</button>}</div></div>
}

export function LoadingState({ rows = 4 }: { rows?: number }) {
  return <div className="loading-stack" aria-label="Loading"><div className="loading-line loading-line--wide" />{Array.from({ length: rows }).map((_, index) => <div className="loading-line" key={index} style={{ width: `${78 - index * 8}%` }} />)}</div>
}

export function RiskGauge({ score, tier }: { score: number; tier: string }) {
  const clamped = Math.max(0, Math.min(10, score))
  return <div className={`risk-gauge risk-gauge--${impactTone(tier)}`}><div className="risk-gauge__label">IMPACT</div><div className="risk-gauge__score">{Number.isFinite(score) ? score.toFixed(2) : '—'}</div><div className="risk-gauge__track"><motion.span initial={{ width: 0 }} animate={{ width: `${clamped * 10}%` }} transition={{ duration: 0.55, ease: 'easeOut' }} /></div><div className="risk-gauge__tier">{prettyLabel(tier)}</div></div>
}

export function IconBadge({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'danger' | 'mint' | 'amber' }) {
  return <span className={`icon-badge icon-badge--${tone}`}>{children}</span>
}

export function ArrowNote({ children }: { children: ReactNode }) {
  return <div className="arrow-note"><ArrowUpRight size={14} />{children}</div>
}

export function AlertNote({ children }: { children: ReactNode }) {
  return <div className="alert-note"><AlertTriangle size={14} />{children}</div>
}
