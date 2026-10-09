export function numeric(value: string | number | null | undefined): number {
  if (typeof value === 'number') return value
  if (value == null) return Number.NaN
  const parsed = Number(String(value).replace(/[$,%\s,]/g, ''))
  return Number.isFinite(parsed) ? parsed : Number.NaN
}

export function formatMoney(value: string | number | null | undefined, compact = true): string {
  if (value == null || Number.isNaN(numeric(value))) return '—'
  const amount = numeric(value)
  const absolute = Math.abs(amount)
  const sign = amount < 0 ? '−' : amount > 0 ? '+' : ''
  if (compact && absolute >= 1_000_000_000) return `${sign}$${(absolute / 1_000_000_000).toFixed(2)}B`
  if (compact && absolute >= 1_000_000) return `${sign}$${(absolute / 1_000_000).toFixed(2)}M`
  if (compact && absolute >= 1_000) return `${sign}$${(absolute / 1_000).toFixed(1)}K`
  return `${sign}$${absolute.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}

export function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

export function formatDecimalPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

export function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(2)
}

export function formatSignedPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

export function formatDecimalSignedPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

export function prettyLabel(value: string | null | undefined): string {
  if (!value) return 'UNSPECIFIED'
  return value.replace(/[_-]+/g, ' ').toUpperCase()
}

export function sentimentLabel(value: number): string {
  if (value < 0) return 'NEGATIVE'
  if (value > 0) return 'POSITIVE'
  return 'NEUTRAL'
}

export function impactTone(tier: string | undefined): 'critical' | 'high' | 'watch' | 'neutral' {
  const value = (tier ?? '').toLowerCase()
  if (value.includes('critical')) return 'critical'
  if (value.includes('high')) return 'high'
  if (value.includes('medium') || value.includes('watch')) return 'watch'
  return 'neutral'
}
