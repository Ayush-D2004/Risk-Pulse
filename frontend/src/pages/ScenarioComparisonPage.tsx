import { useEffect, useState } from 'react';
import { fetchScenarioComparison } from '../api/client';
import type { ScenarioComparisonData } from '../types/api';
import { formatCurrency, formatCurrencyDelta, formatPercentageDelta } from '../lib/format';
import { GitCompare, ArrowRight } from 'lucide-react';

interface Props {
  events: { event_id: string; type: string; impact: number }[];
}

export default function ScenarioComparisonPage({ events }: Props) {
  const [scenarioA, setScenarioA] = useState<string>('');
  const [scenarioB, setScenarioB] = useState<string>('');
  const [data, setData] = useState<ScenarioComparisonData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (events.length >= 2 && !scenarioA && !scenarioB) {
      setScenarioA(events[0].event_id);
      setScenarioB(events[1].event_id);
    }
  }, [events, scenarioA, scenarioB]);

  useEffect(() => {
    if (!scenarioA || !scenarioB) return;
    setLoading(true);
    setError(null);
    fetchScenarioComparison(scenarioA, scenarioB)
      .then(res => setData(res.data))
      .catch(err => {
        console.error(err);
        setError('Failed to fetch comparison data');
      })
      .finally(() => setLoading(false));
  }, [scenarioA, scenarioB]);

  if (!events.length) return <div className="p-6">No events available in the system.</div>;

  return (
    <div className="flex flex-col gap-6">
      <div className="surface p-4 flex items-center justify-between">
        <div className="flex items-center gap-4 w-full max-w-4xl">
          <div className="flex-1">
            <label className="text-xs text-secondary uppercase tracking-wider block mb-1">Scenario A (Base)</label>
            <select 
              className="w-full bg-surface-hover border border-subtle text-primary p-2 rounded outline-none"
              value={scenarioA}
              onChange={e => setScenarioA(e.target.value)}
            >
              {events.map(ev => (
                <option key={ev.event_id} value={ev.event_id}>{ev.event_id.replace('DEMO-', '')}</option>
              ))}
            </select>
          </div>
          
          <div className="flex items-center justify-center pt-5">
            <GitCompare size={24} className="text-secondary" />
          </div>
          
          <div className="flex-1">
            <label className="text-xs text-secondary uppercase tracking-wider block mb-1">Scenario B (Compare)</label>
            <select 
              className="w-full bg-surface-hover border border-subtle text-primary p-2 rounded outline-none"
              value={scenarioB}
              onChange={e => setScenarioB(e.target.value)}
            >
              {events.map(ev => (
                <option key={ev.event_id} value={ev.event_id}>{ev.event_id.replace('DEMO-', '')}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="loader-container h-64"><div className="spinner"></div></div>
      ) : error ? (
        <div className="surface p-6 text-negative">{error}</div>
      ) : data ? (
        <div className="animate-slide-up">
          <div className="grid grid-cols-3 gap-8">
            <div className="surface p-8">
              <div className="badge badge-neutral mb-4 mx-auto table">Base Scenario</div>
              <div className="text-center mb-8">
                <div className="text-2xl font-bold mb-2">{data.scenario_a.entity}</div>
                <div className="inline-flex items-center gap-2 bg-surface-hover px-3 py-1 rounded-full text-brand font-mono font-bold text-sm">
                  Impact {data.scenario_a.impact_score.toFixed(1)}
                </div>
              </div>
              
              <div className="flex flex-col gap-4">
                <div className="bg-surface-hover p-5 rounded-md border border-subtle">
                  <div className="text-xs text-secondary mb-1 font-semibold uppercase tracking-wider">Incremental EL</div>
                  <div className="text-2xl font-mono text-primary font-bold">{formatCurrency(data.scenario_a.incremental_el)}</div>
                </div>
                <div className="bg-surface-hover p-5 rounded-md border border-subtle">
                  <div className="text-xs text-secondary mb-1 font-semibold uppercase tracking-wider">MTM Impact</div>
                  <div className="text-2xl font-mono text-primary font-bold">{formatCurrency(data.scenario_a.mtm_impact)}</div>
                </div>
              </div>
            </div>

            <div className="surface p-8 border-brand/30 relative bg-brand/5">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-surface border border-subtle rounded-full p-2 text-brand shadow-sm">
                <ArrowRight size={24} />
              </div>
              <div className="badge badge-brand mb-4 mx-auto table">Difference (B − A)</div>
              
              <div className="flex flex-col gap-4 mt-[90px]">
                <div className="bg-surface p-5 rounded-md border border-subtle text-center shadow-sm">
                  <div className="text-xs text-secondary mb-2 font-semibold uppercase tracking-wider">Δ Incremental EL</div>
                  <div className={`text-3xl font-bold font-mono tracking-tight ${parseFloat(data.deltas.incremental_el_difference.toString()) > 0 ? 'text-accent' : parseFloat(data.deltas.incremental_el_difference.toString()) < 0 ? 'text-positive' : 'text-primary'}`}>
                    {formatCurrencyDelta(data.deltas.incremental_el_difference)}
                  </div>
                </div>
                <div className="bg-surface p-5 rounded-md border border-subtle text-center shadow-sm">
                  <div className="text-xs text-secondary mb-2 font-semibold uppercase tracking-wider">Δ MTM Impact</div>
                  <div className={`text-3xl font-bold font-mono tracking-tight ${parseFloat(data.deltas.absolute_mtm_difference.toString()) < 0 ? 'text-accent' : parseFloat(data.deltas.absolute_mtm_difference.toString()) > 0 ? 'text-positive' : 'text-primary'}`}>
                    {formatCurrencyDelta(data.deltas.absolute_mtm_difference)}
                  </div>
                </div>
              </div>
            </div>
            
            <div className="surface p-8">
              <div className="badge badge-neutral mb-4 mx-auto table">Compare Scenario</div>
              <div className="text-center mb-8">
                <div className="text-2xl font-bold mb-2">{data.scenario_b.entity}</div>
                <div className="inline-flex items-center gap-2 bg-surface-hover px-3 py-1 rounded-full text-brand font-mono font-bold text-sm">
                  Impact {data.scenario_b.impact_score.toFixed(1)}
                </div>
              </div>
              
              <div className="flex flex-col gap-4">
                <div className="bg-surface-hover p-5 rounded-md border border-subtle">
                  <div className="text-xs text-secondary mb-1 font-semibold uppercase tracking-wider">Incremental EL</div>
                  <div className="text-2xl font-mono text-primary font-bold">{formatCurrency(data.scenario_b.incremental_el)}</div>
                </div>
                <div className="bg-surface-hover p-5 rounded-md border border-subtle">
                  <div className="text-xs text-secondary mb-1 font-semibold uppercase tracking-wider">MTM Impact</div>
                  <div className="text-2xl font-mono text-primary font-bold">{formatCurrency(data.scenario_b.mtm_impact)}</div>
                </div>
              </div>
            </div>
          </div>
          
          <div className="surface mt-6 p-6">
            <h3 className="text-base mb-4">Sector Attribution Differences</h3>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Sector</th>
                    <th className="text-right">Δ Affected EAD</th>
                    <th className="text-right">Δ Inc. EL</th>
                    <th className="text-right">Δ MTM Impact</th>
                    <th className="text-right">Δ MTM Contribution %</th>
                  </tr>
                </thead>
                <tbody>
                  {data.attribution_differences.by_sector.map((row, i) => (
                    <tr key={i}>
                      <td className="font-medium">{row.dimension_value}</td>
                      <td className="text-right font-mono">{formatCurrencyDelta(row.ead_difference)}</td>
                      <td className="text-right font-mono">{formatCurrencyDelta(row.incremental_el_difference)}</td>
                      <td className="text-right font-mono">{formatCurrencyDelta(row.mtm_impact_difference)}</td>
                      <td className="text-right font-mono">{formatPercentageDelta(row.mtm_contribution_pct_difference)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
