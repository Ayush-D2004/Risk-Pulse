import { useEffect, useState } from 'react';
import { fetchScenarioOverview, fetchScenarioAttribution } from '../api/client';
import type { EventStressOverviewData, RiskAttributionData, AttributionRow } from '../types/api';
import { formatCurrency, formatPercentage } from '../lib/format';
import { AlertTriangle, TrendingDown, Target, Building2, MapPin, Briefcase } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface Props {
  events: { event_id: string; type: string; impact: number }[];
}

export default function EventStressPage({ events }: Props) {
  const [selectedEventId, setSelectedEventId] = useState<string>('');
  const [overview, setOverview] = useState<EventStressOverviewData | null>(null);
  const [attribution, setAttribution] = useState<RiskAttributionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [attrDimension, setAttrDimension] = useState<'sector' | 'geography' | 'asset_type'>('sector');

  useEffect(() => {
    if (events.length > 0 && !selectedEventId) {
      setSelectedEventId(events[0].event_id);
    }
  }, [events, selectedEventId]);

  useEffect(() => {
    if (!selectedEventId) return;
    setLoading(true);
    
    Promise.all([
      fetchScenarioOverview(selectedEventId),
      fetchScenarioAttribution(selectedEventId)
    ])
      .then(([overviewRes, attrRes]) => {
        setOverview(overviewRes.data);
        setAttribution(attrRes.data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedEventId]);

  const getImpactColor = (tier: string) => {
    if (tier === 'SEVERE') return 'var(--color-negative)';
    if (tier === 'HIGH') return 'var(--color-warning)';
    if (tier === 'MODERATE') return 'var(--color-info)';
    return 'var(--color-positive)';
  };

  const getGaugeClass = (tier: string) => {
    if (tier === 'SEVERE') return 'severe';
    if (tier === 'HIGH') return 'high';
    if (tier === 'MODERATE') return 'moderate';
    return '';
  };

  if (!events.length) return <div className="p-6">No events available in the system.</div>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-4 border-b border-strong pb-4">
        <span className="text-secondary font-medium">Select Event Scenario:</span>
        <div className="flex gap-2">
          {events.map(ev => (
            <button
              key={ev.event_id}
              className={`select-btn ${selectedEventId === ev.event_id ? 'active' : ''}`}
              onClick={() => setSelectedEventId(ev.event_id)}
            >
              {ev.event_id.replace('DEMO-', '')}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="loader-container h-64"><div className="spinner"></div></div>
      ) : overview && attribution ? (
        <div className="animate-slide-up">
          <div className="grid grid-cols-12 gap-6">
            <div className="col-span-4 flex flex-col gap-6">
              <div className="surface metric-card p-8">
                <div className="flex justify-between items-start mb-6">
                  <div>
                    <div className="badge badge-brand mb-3">{overview.event_type}</div>
                    <h2 className="text-xl font-bold">{overview.entity}</h2>
                  </div>
                  <div className="text-right">
                    <div className="text-4xl font-bold font-mono tracking-tighter" style={{ color: getImpactColor(overview.impact_tier) }}>
                      {overview.impact_score.toFixed(1)}
                    </div>
                    <div className="text-xs font-bold text-secondary uppercase tracking-widest mt-1">{overview.impact_tier} IMPACT</div>
                  </div>
                </div>
                
                <div className="impact-gauge mb-8">
                  <div 
                    className={`impact-gauge-fill ${getGaugeClass(overview.impact_tier)}`} 
                    style={{ width: `${(overview.impact_score / 10) * 100}%` }}
                  ></div>
                </div>

                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="bg-surface-hover p-4 rounded border border-subtle">
                    <div className="text-xs font-semibold uppercase tracking-wider text-secondary mb-1">Sentiment</div>
                    <div className="font-mono text-lg font-bold">{overview.sentiment.toFixed(2)}</div>
                  </div>
                  <div className="bg-surface-hover p-4 rounded border border-subtle">
                    <div className="text-xs font-semibold uppercase tracking-wider text-secondary mb-1">Scope</div>
                    <div className="font-mono text-lg font-bold">{overview.shock_scope || 'PORTFOLIO'}</div>
                  </div>
                </div>
                
                <div className="bg-surface-hover p-4 rounded border-l-4 border-l-brand text-sm text-secondary italic">
                  {overview.deterministic_rationale}
                </div>
              </div>
            </div>

            <div className="col-span-8 flex flex-col gap-6">
              <div className="surface p-8 flex flex-col justify-center h-full relative overflow-hidden">
                <div className="absolute -right-10 -top-10 opacity-5">
                  <AlertTriangle size={240} />
                </div>
                <h3 className="text-sm font-bold mb-8 text-secondary uppercase tracking-widest flex items-center gap-2">
                  <AlertTriangle size={18} className="text-accent" /> Portfolio Stress Impact
                </h3>
                
                <div className="grid grid-cols-3 gap-8 relative z-10">
                  <div>
                    <div className="text-secondary text-xs font-semibold uppercase tracking-wider mb-2">Affected EAD</div>
                    <div className="text-3xl font-bold font-mono text-primary mb-1">
                      {formatCurrency(overview.affected_ead)}
                    </div>
                    <div className="text-xs font-mono text-brand font-medium">
                      {formatPercentage(overview.affected_ead_pct)} of portfolio
                    </div>
                  </div>
                  
                  <div>
                    <div className="text-secondary text-xs font-semibold uppercase tracking-wider mb-2">Incremental EL</div>
                    <div className="text-3xl font-bold font-mono text-accent mb-1">
                      +{formatCurrency(overview.incremental_el)}
                    </div>
                  </div>
                  
                  <div>
                    <div className="text-secondary text-xs font-semibold uppercase tracking-wider mb-2">MTM Impact</div>
                    <div className="text-3xl font-bold font-mono text-accent mb-1">
                      {formatCurrency(overview.mtm_impact)}
                    </div>
                  </div>
                </div>
                
                {!overview.stress_applied && (
                  <div className="mt-6 p-3 bg-positive-bg text-positive border border-positive/30 rounded flex items-center gap-2">
                    <Target size={16} /> No stress applied. Portfolio is insulated from this event.
                  </div>
                )}
              </div>
            </div>
          </div>

          {overview.stress_applied && (
            <div className="surface mt-4">
              <div className="border-b border-strong p-4 flex items-center justify-between">
                <h3 className="text-base m-0 flex items-center gap-2">
                  <TrendingDown size={18} className="text-secondary" /> Risk Attribution
                </h3>
                
                <div className="flex bg-surface-hover rounded-md p-1 border border-subtle">
                  <button 
                    className={`px-3 py-1 text-sm rounded ${attrDimension === 'sector' ? 'bg-surface-active text-primary shadow-sm' : 'text-secondary hover:text-primary bg-transparent border-0'}`}
                    onClick={() => setAttrDimension('sector')}
                  ><Building2 size={14} className="inline mr-1" /> Sector</button>
                  <button 
                    className={`px-3 py-1 text-sm rounded ${attrDimension === 'geography' ? 'bg-surface-active text-primary shadow-sm' : 'text-secondary hover:text-primary bg-transparent border-0'}`}
                    onClick={() => setAttrDimension('geography')}
                  ><MapPin size={14} className="inline mr-1" /> Geography</button>
                  <button 
                    className={`px-3 py-1 text-sm rounded ${attrDimension === 'asset_type' ? 'bg-surface-active text-primary shadow-sm' : 'text-secondary hover:text-primary bg-transparent border-0'}`}
                    onClick={() => setAttrDimension('asset_type')}
                  ><Briefcase size={14} className="inline mr-1" /> Asset Type</button>
                </div>
              </div>
              
              <div className="p-6 grid grid-cols-2 gap-8">
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={attribution[`by_${attrDimension}` as keyof RiskAttributionData] as AttributionRow[]} layout="vertical" margin={{ left: 40 }}>
                      <XAxis type="number" tickFormatter={(v) => formatCurrency(v)} stroke="var(--border-strong)" tick={{fill: 'var(--text-secondary)'}} />
                      <YAxis dataKey="dimension_value" type="category" width={120} stroke="var(--border-strong)" tick={{fill: 'var(--text-secondary)'}} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-strong)', borderRadius: 'var(--radius-sm)' }}
                        formatter={(value: any) => formatCurrency(value)}
                        cursor={{ fill: 'var(--bg-surface-hover)' }}
                      />
                      <Bar dataKey="incremental_el" fill="var(--color-accent)" radius={[0, 4, 4, 0]} name="Incremental EL" animationDuration={1000} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                
                <div className="overflow-y-auto max-h-64">
                  <table className="data-table">
                    <thead className="sticky top-0 bg-surface">
                      <tr>
                        <th>{attrDimension.replace('_', ' ').toUpperCase()}</th>
                        <th className="text-right">Affected EAD</th>
                        <th className="text-right">+EL</th>
                        <th className="text-right">MTM Impact</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(attribution[`by_${attrDimension}` as keyof RiskAttributionData] as AttributionRow[]).map((row, i) => (
                        <tr key={i}>
                          <td className="font-medium">{row.dimension_value}</td>
                          <td className="text-right font-mono">{formatCurrency(row.ead)}</td>
                          <td className="text-right font-mono text-accent">{formatCurrency(row.incremental_el)}</td>
                          <td className="text-right font-mono text-accent">{formatCurrency(row.mtm_impact)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {overview.stress_applied && attribution.by_exposure.length > 0 && (
            <div className="surface mt-6 p-6">
              <h3 className="text-base mb-4 flex items-center gap-2">
                Affected Exposures Drill-down
              </h3>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Obligor</th>
                      <th>Sector</th>
                      <th>Geography</th>
                      <th className="text-right">EAD</th>
                      <th className="text-right">Inc. EL</th>
                      <th className="text-right">MTM Impact</th>
                    </tr>
                  </thead>
                  <tbody>
                    {attribution.by_exposure.map((exp, i) => (
                      <tr key={i}>
                        <td className="font-medium">{exp.obligor}</td>
                        <td className="text-secondary">{exp.sector}</td>
                        <td className="text-secondary">{exp.geography}</td>
                        <td className="text-right font-mono">{formatCurrency(exp.ead)}</td>
                        <td className="text-right font-mono text-accent">{formatCurrency(exp.incremental_el)}</td>
                        <td className="text-right font-mono text-accent">{formatCurrency(exp.mtm_impact)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
