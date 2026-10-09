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

export function GithubIcon({ size = 16, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  )
}

export function LinkedinIcon({ size = 16, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.46 10.9h2.79v8.37H6.46v-8.37M7.86 6.3a1.63 1.63 0 1 0 0 3.26 1.63 1.63 0 0 0 0-3.26z" />
    </svg>
  )
}

