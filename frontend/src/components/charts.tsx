import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import type { AttributionDeltaRow, AttributionRow, EadSlice, ObligorConcentrationRow } from '../types/api'
import { formatMoney, formatPct, formatSignedPct, numeric, prettyLabel } from '../lib/format'

function maxOf(values: number[]) {
  const max = Math.max(...values, 0)
  return max > 0 ? max : 1
}

export function RankedBars({ rows, mode = 'ead', limit = 6 }: { rows: EadSlice[] | ObligorConcentrationRow[]; mode?: 'ead' | 'pct'; limit?: number }) {
  const normalized = rows.slice(0, limit).map((row) => ({ name: 'obligor' in row ? row.obligor : row.name, value: mode === 'pct' && 'pct' in row ? row.pct : numeric(row.ead), display: mode === 'pct' && 'pct' in row ? formatPct(row.pct) : formatMoney(row.ead) }))
  const max = maxOf(normalized.map((row) => row.value))
  if (!normalized.length) return <div className="chart-empty">No rows returned by the API.</div>
  return <div className="ranked-bars">{normalized.map((row, index) => <div className="ranked-row" key={`${row.name}-${index}`}><div className="ranked-row__meta"><span className="ranked-row__name">{row.name}</span><span className="ranked-row__value">{row.display}</span></div><div className="ranked-row__track"><motion.span initial={{ width: 0 }} animate={{ width: `${(row.value / max) * 100}%` }} transition={{ duration: 0.5, delay: index * 0.045, ease: 'easeOut' }} /></div></div>)}</div>
}

export function ContributionBars({ rows, valueKey = 'incremental_el', limit = 8 }: { rows: AttributionRow[]; valueKey?: 'ead' | 'incremental_el' | 'mtm_impact'; limit?: number }) {
  const selected = rows.slice(0, limit)
  const values = selected.map((row) => Math.abs(numeric(row[valueKey])))
  const max = maxOf(values)
  return <div className="contribution-bars">{selected.length ? selected.map((row, index) => { const value = numeric(row[valueKey]); const pct = valueKey === 'ead' ? row.ead_pct : valueKey === 'mtm_impact' ? row.mtm_contribution_pct : row.incremental_el_pct; return <div className="contribution-row" key={`${row.dimension_value}-${index}`}><div className="contribution-row__top"><span>{row.dimension_value}</span><strong>{valueKey === 'ead' ? formatMoney(row.ead) : formatMoney(row[valueKey])}</strong></div><div className="contribution-row__bar"><motion.span initial={{ width: 0 }} animate={{ width: `${(Math.abs(value) / max) * 100}%` }} transition={{ duration: 0.5, delay: index * 0.04 }} /></div><div className="contribution-row__foot"><span>{formatPct(pct)} contribution</span><span>{formatPct(row.ead_pct)} of EAD</span></div></div> }) : <div className="chart-empty">No attribution rows returned by the API.</div>}</div>
}

export function ExposureMatrix({ rows }: { rows: AttributionRow[] }) {
  if (!rows.length) return <div className="chart-empty">No concentration rows returned by the API.</div>
  return <div className="exposure-matrix">{rows.slice(0, 12).map((row, index) => <div className="matrix-cell" key={`${row.dimension_value}-${index}`} style={{ ['--cell-intensity' as string]: `${Math.max(10, Math.min(100, row.ead_pct))}%` }}><div className="matrix-cell__value">{row.dimension_value}</div><div className="matrix-cell__bar" /><div className="matrix-cell__meta">{formatPct(row.ead_pct)} · {row.exposure_count} exp.</div></div>)}</div>
}

export function ComparisonRows({ rows }: { rows: AttributionDeltaRow[] }) {
  if (!rows.length) return <div className="chart-empty">No attribution differences returned by the API.</div>
  return <div className="comparison-rows">{rows.slice(0, 8).map((row, index) => <div className="comparison-row" key={`${row.dimension_value}-${index}`}><div><span className="comparison-row__name">{row.dimension_value}</span><span className="comparison-row__meta">EAD {formatSignedPct(row.ead_pct_difference)} · EL {formatSignedPct(row.incremental_el_pct_difference)}</span></div><div className="comparison-row__numbers"><strong>{formatMoney(row.incremental_el_difference)}</strong><span>{formatMoney(row.mtm_impact_difference)} MTM</span></div></div>)}</div>
}

export function InlineStack({ rows }: { rows: EadSlice[] }) {
  const total = rows.reduce((sum, row) => sum + numeric(row.ead), 0)
  return <div className="inline-stack">{rows.map((row, index) => { const pct = total > 0 ? (numeric(row.ead) / total) * 100 : 0; return <div key={`${row.name}-${index}`} className="inline-stack__segment" style={{ width: `${pct}%` }} title={`${row.name}: ${formatPct(pct)}`} /> })}</div>
}

export function DataTable({ headers, rows }: { headers: string[]; rows: Array<Array<string | number>> }) {
  return <div className="data-table-wrap"><table className="data-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex} className={cellIndex > 0 ? 'numeric-cell' : ''}>{cell}</td>)}</tr>)}</tbody></table></div>
}

export function Annotation({ children }: { children: ReactNode }) {
  return <span className="annotation">{prettyLabel(String(children))}</span>
}
