import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchEvents, fetchScenarioOverview } from '../api/client';
import { formatCurrency } from '../utils/formatters';
import { Loader2, AlertCircle, Calendar, ShieldAlert } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts';

export default function EventStress() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const { data: events, isLoading: isLoadingEvents } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
  });

  const { data: scenario, isLoading: isLoadingScenario } = useQuery({
    queryKey: ['scenario', selectedEventId],
    queryFn: () => fetchScenarioOverview(selectedEventId!),
    enabled: !!selectedEventId,
  });

  // Auto-select first event when events load
  if (events && events.length > 0 && !selectedEventId) {
    setSelectedEventId(events[0].event_id);
  }

  return (
    <div className="flex flex-col lg:flex-row gap-8 h-full pb-8">
      {/* LEFT PANEL: Event List */}
      <div className="w-full lg:w-80 flex-shrink-0 flex flex-col gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 tracking-tight">Identified Risks</h2>
          <p className="text-sm text-gray-500 mt-1">Select an NLP signal to evaluate shock</p>
        </div>
        
        <div className="flex-1 overflow-y-auto pr-2 space-y-3">
          {isLoadingEvents ? (
            <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-teal-600" /></div>
          ) : (
            events?.map((ev) => (
              <button
                key={ev.event_id}
                onClick={() => setSelectedEventId(ev.event_id)}
                className={`w-full text-left p-4 rounded-xl border transition-all ${
                  selectedEventId === ev.event_id 
                    ? 'bg-teal-50 border-teal-200 shadow-sm' 
                    : 'bg-white border-gray-100 hover:border-gray-200 hover:shadow-sm'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-teal-700 bg-teal-100/50 px-2 py-1 rounded-md">
                    {ev.type}
                  </span>
                  <span className={`text-sm font-bold ${ev.impact >= 7 ? 'text-red-600' : 'text-amber-600'}`}>
                    Impact {ev.impact}/10
                  </span>
                </div>
                <div className="text-sm font-medium text-gray-900 truncate">{ev.event_id}</div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* RIGHT PANEL: Event Stress Details */}
      <div className="flex-1 flex flex-col min-w-0">
        {!selectedEventId ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-400 bg-white/50 rounded-3xl border border-dashed border-gray-200">
            <ShieldAlert className="w-12 h-12 mb-4 text-gray-300" />
            <p>Select a risk event from the list to view stress scenario</p>
          </div>
        ) : isLoadingScenario ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
          </div>
        ) : !scenario ? (
          <div className="flex-1 flex items-center justify-center text-red-500">
            <AlertCircle className="w-8 h-8 mr-2" /> Error loading scenario data
          </div>
        ) : (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Header Card */}
            <div className="bg-white rounded-2xl p-8 shadow-sm border border-gray-100 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-red-500" />
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                  <h1 className="text-2xl font-bold text-gray-900">{scenario.data.entity}</h1>
                  <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-gray-500">
                    <span className="flex items-center gap-1"><Calendar className="w-4 h-4" /> {new Date(scenario.generated_at).toLocaleDateString()}</span>
                    <span>•</span>
                    <span className="font-medium text-gray-700">Type: {scenario.data.event_type}</span>
                    <span>•</span>
                    <span>Severity Tier: <span className="font-bold text-red-600">{scenario.data.impact_tier}</span></span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-gray-500 font-medium">Est. MtM Impact</div>
                  <div className="text-3xl font-bold text-red-600 tracking-tight">
                    -{formatCurrency(Math.abs(Number(scenario.data.mtm_impact)))}
                  </div>
                </div>
              </div>
              <div className="mt-6 p-4 bg-gray-50 rounded-xl border border-gray-100">
                <p className="text-sm text-gray-700 italic">"{scenario.data.deterministic_rationale}"</p>
              </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                <div className="text-sm font-medium text-gray-500">Affected EAD</div>
                <div className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(scenario.data.affected_ead as any)}</div>
                <div className="text-sm text-gray-400 mt-2">{(scenario.data.affected_ead_pct * 100).toFixed(1)}% of total portfolio</div>
              </div>
              <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                <div className="text-sm font-medium text-gray-500">Incremental Expected Loss</div>
                <div className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(scenario.data.incremental_el as any)}</div>
                <div className="text-sm text-gray-400 mt-2">Driven by PD/LGD shocks</div>
              </div>
              <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                <div className="text-sm font-medium text-gray-500">Sentiment Score</div>
                <div className="text-2xl font-bold text-gray-900 mt-1">{scenario.data.sentiment.toFixed(2)}</div>
                <div className="text-sm text-gray-400 mt-2">NLP extracted context</div>
              </div>
            </div>

            {/* Visualization */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-gray-900">Value at Risk Shock Comparison</h3>
                <p className="text-sm text-gray-500">Illustrative portfolio trajectory vs severe macro stress</p>
              </div>
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={[
                    { time: 'T-3', baseline: 100, shock: 100 },
                    { time: 'T-2', baseline: 102, shock: 102 },
                    { time: 'T-1', baseline: 101, shock: 101 },
                    { time: 'T-0 (Event)', baseline: 103, shock: 103 },
                    { time: 'T+1', baseline: 104, shock: 104 - (Number(scenario.data.mtm_impact) / Number(scenario.data.affected_ead) * 100 * 0.3) },
                    { time: 'T+2', baseline: 105, shock: 105 - (Number(scenario.data.mtm_impact) / Number(scenario.data.affected_ead) * 100 * 0.7) },
                    { time: 'T+3', baseline: 106, shock: 106 - (Number(scenario.data.mtm_impact) / Number(scenario.data.affected_ead) * 100) },
                  ]} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorBase" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#0f766e" stopOpacity={0.2}/>
                        <stop offset="95%" stopColor="#0f766e" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorShock" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15}/>
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{fill: '#9ca3af', fontSize: 12}} dy={10} />
                    <YAxis axisLine={false} tickLine={false} tick={{fill: '#9ca3af', fontSize: 12}} dx={-10} domain={['dataMin - 2', 'dataMax + 2']} />
                    <RechartsTooltip 
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px -2px rgba(0,0,0,0.1)', padding: '12px' }}
                    />
                    <Area type="monotone" dataKey="baseline" name="Baseline Projection" stroke="#0f766e" strokeWidth={3} fill="url(#colorBase)" />
                    <Area type="monotone" dataKey="shock" name="Post-Shock Trajectory" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 5" fill="url(#colorShock)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
