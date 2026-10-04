import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchEvents, fetchScenarioAttribution } from '../api/client';
import { formatCurrency, formatPercent } from '../utils/formatters';
import { Loader2, ShieldAlert, BarChart3, Globe2, Layers, ListFilter } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

type Dimension = 'Sector' | 'Geography' | 'Asset Type' | 'Exposure';

export default function RiskAttribution() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Dimension>('Sector');

  const { data: events } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
  });

  const { data: attribution, isLoading } = useQuery({
    queryKey: ['attribution', selectedEventId],
    queryFn: () => fetchScenarioAttribution(selectedEventId!),
    enabled: !!selectedEventId,
  });

  if (events && events.length > 0 && !selectedEventId) {
    setSelectedEventId(events[0].event_id);
  }

  const getDimensionData = () => {
    if (!attribution?.data) return [];
    switch (activeTab) {
      case 'Sector':
        return attribution.data.by_sector;
      case 'Geography':
        return attribution.data.by_geography;
      case 'Asset Type':
        return attribution.data.by_asset_type;
      default:
        return [];
    }
  };

  const dimData = getDimensionData();

  return (
    <div className="flex flex-col h-full space-y-6 pb-12 max-w-7xl mx-auto">
      {/* HEADER & SCENARIO SELECTOR */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Risk Attribution Engine</h1>
          <p className="text-sm text-gray-500 mt-1">
            Multidimensional stress decomposition across portfolios and exposures.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm font-semibold text-gray-700">Scenario:</label>
          <select 
            value={selectedEventId || ''} 
            onChange={(e) => setSelectedEventId(e.target.value)}
            className="block w-72 px-4 py-2 text-sm border-gray-200 rounded-xl bg-white focus:ring-2 focus:ring-teal-500 focus:border-teal-500 shadow-sm font-medium"
          >
            {events?.map(ev => (
              <option key={ev.event_id} value={ev.event_id}>
                {ev.event_id.replace('DEMO-', '')} ({ev.type})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* DIMENSION TABS */}
      <div className="flex items-center gap-2 border-b border-gray-200 pb-2">
        <button
          onClick={() => setActiveTab('Sector')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'Sector' 
              ? 'bg-teal-600 text-white shadow-sm' 
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <BarChart3 size={16} />
          Sector
        </button>
        <button
          onClick={() => setActiveTab('Geography')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'Geography' 
              ? 'bg-teal-600 text-white shadow-sm' 
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <Globe2 size={16} />
          Geography
        </button>
        <button
          onClick={() => setActiveTab('Asset Type')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'Asset Type' 
              ? 'bg-teal-600 text-white shadow-sm' 
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <Layers size={16} />
          Asset Type
        </button>
        <button
          onClick={() => setActiveTab('Exposure')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'Exposure' 
              ? 'bg-teal-600 text-white shadow-sm' 
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <ListFilter size={16} />
          Exposure Drill-Down
        </button>
      </div>

      {!selectedEventId ? (
        <div className="flex-1 flex flex-col items-center justify-center text-gray-400 bg-white/50 rounded-3xl border border-dashed border-gray-200">
           <ShieldAlert className="w-12 h-12 mb-4 text-gray-300" />
           <p>Select a scenario to view attribution</p>
        </div>
      ) : isLoading || !attribution ? (
        <div className="flex-1 flex items-center justify-center p-12">
          <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
        </div>
      ) : activeTab === 'Exposure' ? (
        /* EXPOSURE DRILL-DOWN TABLE */
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-gray-900">Individual Stressed Exposures</h3>
              <p className="text-xs text-gray-500">Asset-level loss attribution and shock absorption</p>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 bg-gray-100 text-gray-700 rounded-lg">
              {attribution.data.by_exposure.length} Affected Positions
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-500 uppercase bg-gray-50/50 border-b border-gray-100">
                <tr>
                  <th className="px-5 py-3 font-semibold rounded-tl-xl">Exposure ID</th>
                  <th className="px-5 py-3 font-semibold">Obligor</th>
                  <th className="px-5 py-3 font-semibold">Asset Type</th>
                  <th className="px-5 py-3 font-semibold">Sector</th>
                  <th className="px-5 py-3 font-semibold">Region</th>
                  <th className="px-5 py-3 font-semibold text-right">EAD</th>
                  <th className="px-5 py-3 font-semibold text-right">Inc. EL</th>
                  <th className="px-5 py-3 font-semibold text-right rounded-tr-xl">MTM Impact</th>
                </tr>
              </thead>
              <tbody>
                {attribution.data.by_exposure.map((row) => (
                  <tr key={row.exposure_id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-3 font-mono text-xs text-gray-500">{row.exposure_id}</td>
                    <td className="px-5 py-3 font-medium text-gray-900">{row.obligor}</td>
                    <td className="px-5 py-3 text-xs text-gray-600">{row.asset_type}</td>
                    <td className="px-5 py-3 text-xs text-gray-600">{row.sector}</td>
                    <td className="px-5 py-3 text-xs text-gray-600">{row.geography}</td>
                    <td className="px-5 py-3 text-right font-mono text-gray-900">{formatCurrency(row.ead as any)}</td>
                    <td className="px-5 py-3 text-right font-mono text-amber-700 font-medium">+{formatCurrency(row.incremental_el as any)}</td>
                    <td className="px-5 py-3 text-right font-mono text-red-600 font-medium">-{formatCurrency(Math.abs(Number(row.mtm_impact)))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* DIMENSION ATTRIBUTION (Sector / Geography / Asset Type) */
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* HORIZONTAL CONTRIBUTION CHART */}
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 flex flex-col justify-between">
            <div>
              <h3 className="text-lg font-bold text-gray-900 mb-1">{activeTab} Loss Breakdown (MTM)</h3>
              <p className="text-xs text-gray-500 mb-4">Total mark-to-market stress shock by {activeTab.toLowerCase()}</p>
            </div>
            
            <div className="h-[320px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dimData} layout="vertical" margin={{ top: 10, right: 30, left: 40, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                  <XAxis 
                    type="number" 
                    tickFormatter={(val) => formatCurrency(Math.abs(val))} 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{fill: '#64748b', fontSize: 12}} 
                  />
                  <YAxis 
                    dataKey="dimension_value" 
                    type="category" 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{fill: '#475569', fontSize: 12, fontWeight: 500}} 
                  />
                  <RechartsTooltip 
                    formatter={(val: any) => formatCurrency(Math.abs(Number(val)))}
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)', padding: '12px' }}
                  />
                  <Bar dataKey="mtm_impact" fill="#e11d48" radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ATTRIBUTION DATA TABLE */}
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 flex flex-col">
            <h3 className="text-lg font-bold text-gray-900 mb-1">{activeTab} Stress Metrics</h3>
            <p className="text-xs text-gray-500 mb-4">Concentration and incremental expected loss decomposition</p>
            
            <div className="overflow-x-auto flex-1">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-gray-500 uppercase bg-gray-50/50 border-b border-gray-100">
                  <tr>
                    <th className="px-4 py-3 font-semibold rounded-tl-xl">{activeTab}</th>
                    <th className="px-4 py-3 font-semibold text-right">EAD</th>
                    <th className="px-4 py-3 font-semibold text-right">Inc. EL</th>
                    <th className="px-4 py-3 font-semibold text-right">MTM Impact</th>
                    <th className="px-4 py-3 font-semibold text-right rounded-tr-xl">MTM %</th>
                  </tr>
                </thead>
                <tbody>
                  {dimData.map((row, idx) => (
                    <tr key={idx} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-gray-900">{row.dimension_value}</td>
                      <td className="px-4 py-3 text-right text-gray-600 font-mono">{formatCurrency(row.ead as any)}</td>
                      <td className="px-4 py-3 text-right text-amber-700 font-mono font-medium">+{formatCurrency(row.incremental_el as any)}</td>
                      <td className="px-4 py-3 text-right text-red-600 font-mono font-medium">-{formatCurrency(Math.abs(Number(row.mtm_impact)))}</td>
                      <td className="px-4 py-3 text-right text-gray-700 font-mono">{formatPercent(row.mtm_contribution_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
