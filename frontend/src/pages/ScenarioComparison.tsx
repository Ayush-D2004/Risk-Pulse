import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchEvents, fetchScenarioComparison } from '../api/client';
import { formatCurrency, formatCurrencyDelta, formatPercentageDelta } from '../lib/format';
import { GitCompare, ArrowRight, Loader2 } from 'lucide-react';

export default function ScenarioComparison() {
  const { data: events, isLoading: isLoadingEvents } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
  });

  const [scenarioA, setScenarioA] = useState<string>('');
  const [scenarioB, setScenarioB] = useState<string>('');

  useEffect(() => {
    if (events && events.length >= 2 && !scenarioA && !scenarioB) {
      setScenarioA(events[0].event_id);
      setScenarioB(events[1].event_id);
    }
  }, [events, scenarioA, scenarioB]);

  const { data: comparisonData, isLoading: isLoadingComparison } = useQuery({
    queryKey: ['comparison', scenarioA, scenarioB],
    queryFn: () => fetchScenarioComparison(scenarioA, scenarioB),
    enabled: !!scenarioA && !!scenarioB,
  });

  if (isLoadingEvents) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
      </div>
    );
  }

  if (!events || events.length === 0) {
    return <div className="p-8 text-gray-500">No risk scenarios found.</div>;
  }

  const data = comparisonData?.data;

  return (
    <div className="flex flex-col gap-6 max-w-7xl mx-auto pb-12">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Market Scenarios Comparison</h1>
        <p className="text-sm text-gray-500 mt-1">
          Objective differential comparison of stress shocks (B − A).
        </p>
      </div>

      {/* SELECTION BAR */}
      <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col md:flex-row items-center gap-4">
        <div className="flex-1 w-full">
          <label className="text-xs text-gray-500 font-semibold uppercase tracking-wider block mb-2">
            Scenario A (Base)
          </label>
          <select 
            className="w-full bg-gray-50 border border-gray-200 text-gray-900 p-2.5 rounded-xl outline-none focus:ring-2 focus:ring-teal-500 text-sm font-medium"
            value={scenarioA}
            onChange={e => setScenarioA(e.target.value)}
          >
            {events.map(ev => (
              <option key={ev.event_id} value={ev.event_id}>
                {ev.event_id.replace('DEMO-', '')} (Impact {ev.impact}/10)
              </option>
            ))}
          </select>
        </div>
        
        <div className="flex items-center justify-center pt-2 md:pt-6 text-gray-400">
          <GitCompare size={24} />
        </div>
        
        <div className="flex-1 w-full">
          <label className="text-xs text-gray-500 font-semibold uppercase tracking-wider block mb-2">
            Scenario B (Compare)
          </label>
          <select 
            className="w-full bg-gray-50 border border-gray-200 text-gray-900 p-2.5 rounded-xl outline-none focus:ring-2 focus:ring-teal-500 text-sm font-medium"
            value={scenarioB}
            onChange={e => setScenarioB(e.target.value)}
          >
            {events.map(ev => (
              <option key={ev.event_id} value={ev.event_id}>
                {ev.event_id.replace('DEMO-', '')} (Impact {ev.impact}/10)
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoadingComparison ? (
        <div className="flex justify-center p-12">
          <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
        </div>
      ) : data ? (
        <div className="space-y-6">
          {/* THREE-COLUMN COMPARISON CARDS */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* SCENARIO A */}
            <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm flex flex-col justify-between">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 bg-gray-100 px-2.5 py-1 rounded-md">
                  Scenario A
                </span>
                <div className="mt-4">
                  <div className="text-xl font-bold text-gray-900">{data.scenario_a.entity}</div>
                  <div className="text-xs text-gray-500 mt-1">{data.scenario_a.event_type}</div>
                  <div className="mt-2 text-sm font-semibold text-teal-700 bg-teal-50 inline-block px-2.5 py-1 rounded-md">
                    Impact {data.scenario_a.impact_score.toFixed(1)}/10
                  </div>
                </div>
              </div>

              <div className="mt-6 space-y-4">
                <div className="bg-gray-50 p-4 rounded-xl">
                  <div className="text-xs text-gray-500 font-medium">Incremental EL</div>
                  <div className="text-xl font-bold font-mono text-gray-900 mt-1">
                    {formatCurrency(data.scenario_a.incremental_el)}
                  </div>
                </div>
                <div className="bg-gray-50 p-4 rounded-xl">
                  <div className="text-xs text-gray-500 font-medium">MTM Impact</div>
                  <div className="text-xl font-bold font-mono text-red-600 mt-1">
                    {formatCurrency(data.scenario_a.mtm_impact)}
                  </div>
                </div>
              </div>
            </div>

            {/* DELTA (B - A) */}
            <div className="bg-teal-50/50 rounded-2xl p-6 border border-teal-200/80 shadow-sm flex flex-col justify-between relative">
              <div className="text-center">
                <span className="text-xs font-semibold uppercase tracking-wider text-teal-800 bg-teal-100 px-3 py-1 rounded-md">
                  Difference (B − A)
                </span>
                <div className="flex justify-center mt-3 text-teal-600">
                  <ArrowRight size={20} />
                </div>
              </div>

              <div className="mt-6 space-y-4">
                <div className="bg-white p-4 rounded-xl border border-teal-100 shadow-xs text-center">
                  <div className="text-xs text-gray-500 font-medium uppercase tracking-wider">Δ Incremental EL</div>
                  <div className="text-2xl font-bold font-mono text-teal-900 mt-1">
                    {formatCurrencyDelta(data.deltas.incremental_el_difference)}
                  </div>
                </div>
                <div className="bg-white p-4 rounded-xl border border-teal-100 shadow-xs text-center">
                  <div className="text-xs text-gray-500 font-medium uppercase tracking-wider">Δ MTM Impact</div>
                  <div className="text-2xl font-bold font-mono text-red-600 mt-1">
                    {formatCurrencyDelta(data.deltas.absolute_mtm_difference)}
                  </div>
                </div>
              </div>
            </div>

            {/* SCENARIO B */}
            <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm flex flex-col justify-between">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 bg-gray-100 px-2.5 py-1 rounded-md">
                  Scenario B
                </span>
                <div className="mt-4">
                  <div className="text-xl font-bold text-gray-900">{data.scenario_b.entity}</div>
                  <div className="text-xs text-gray-500 mt-1">{data.scenario_b.event_type}</div>
                  <div className="mt-2 text-sm font-semibold text-teal-700 bg-teal-50 inline-block px-2.5 py-1 rounded-md">
                    Impact {data.scenario_b.impact_score.toFixed(1)}/10
                  </div>
                </div>
              </div>

              <div className="mt-6 space-y-4">
                <div className="bg-gray-50 p-4 rounded-xl">
                  <div className="text-xs text-gray-500 font-medium">Incremental EL</div>
                  <div className="text-xl font-bold font-mono text-gray-900 mt-1">
                    {formatCurrency(data.scenario_b.incremental_el)}
                  </div>
                </div>
                <div className="bg-gray-50 p-4 rounded-xl">
                  <div className="text-xs text-gray-500 font-medium">MTM Impact</div>
                  <div className="text-xl font-bold font-mono text-red-600 mt-1">
                    {formatCurrency(data.scenario_b.mtm_impact)}
                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* ATTRIBUTION DIFFERENCES TABLE */}
          <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Sector Attribution Differences</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-gray-500 uppercase bg-gray-50/50 border-b border-gray-100">
                  <tr>
                    <th className="px-6 py-3 font-semibold rounded-tl-xl">Sector</th>
                    <th className="px-6 py-3 font-semibold text-right">Δ Affected EAD</th>
                    <th className="px-6 py-3 font-semibold text-right">Δ Inc. EL</th>
                    <th className="px-6 py-3 font-semibold text-right">Δ MTM Impact</th>
                    <th className="px-6 py-3 font-semibold text-right rounded-tr-xl">Δ MTM Contrib. %</th>
                  </tr>
                </thead>
                <tbody>
                  {data.attribution_differences.by_sector.map((row, i) => (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                      <td className="px-6 py-3 font-medium text-gray-900">{row.dimension_value}</td>
                      <td className="px-6 py-3 text-right font-mono text-gray-700">{formatCurrencyDelta(row.ead_difference)}</td>
                      <td className="px-6 py-3 text-right font-mono text-gray-700">{formatCurrencyDelta(row.incremental_el_difference)}</td>
                      <td className="px-6 py-3 text-right font-mono text-red-600">{formatCurrencyDelta(row.mtm_impact_difference)}</td>
                      <td className="px-6 py-3 text-right font-mono text-gray-700">{formatPercentageDelta(row.mtm_contribution_pct_difference)}</td>
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
