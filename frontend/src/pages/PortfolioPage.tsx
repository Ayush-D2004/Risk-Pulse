import { useEffect, useState } from 'react';
import { fetchPortfolio } from '../api/client';
import type { PortfolioOverviewData } from '../types/api';
import { formatCurrency } from '../lib/format';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, LineChart, Line } from 'recharts';
import { AlertCircle, Users, Briefcase, Building2, MapPin } from 'lucide-react';

const COLORS = ['#0f766e', '#0369a1', '#047857', '#b45309', '#be123c', '#4338ca'];

export default function PortfolioPage() {
  const [data, setData] = useState<PortfolioOverviewData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPortfolio()
      .then(res => setData(res.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loader-container">
        <div className="spinner"></div>
        <div>Loading portfolio...</div>
      </div>
    );
  }

  if (!data) return <div>No data</div>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl mb-1">Portfolio Overview</h2>
          <div className="text-secondary text-sm">Base state without applied stress events</div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <div className="surface bento-highlight-top metric-card p-8 flex flex-col h-40 relative">
          <div className="text-secondary text-sm font-semibold tracking-wider uppercase mb-1 flex items-center gap-2">
            <Briefcase size={16} className="text-brand" /> Total Exposure (EAD)
          </div>
          <div className="text-3xl font-bold font-mono text-primary mt-2">{formatCurrency(data.total_ead)}</div>
          <div className="absolute bottom-4 right-4 sparkline-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={Array.from({ length: 12 }, (_, i) => ({ value: 800 + Math.random() * 60 + i * 5 }))}>
                <Line type="monotone" dataKey="value" stroke="var(--color-brand)" strokeWidth={2} dot={false} isAnimationActive={true} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="surface bento-highlight-top metric-card p-8 flex flex-col h-40 relative">
          <div className="text-secondary text-sm font-semibold tracking-wider uppercase mb-1 flex items-center gap-2">
            <Building2 size={16} className="text-brand" /> Exposure Count
          </div>
          <div className="text-3xl font-bold font-mono text-primary mt-2">{data.exposure_count}</div>
          <div className="absolute bottom-4 right-4 sparkline-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={Array.from({ length: 12 }, (_, i) => ({ value: 1200 + Math.random() * 50 + i * 2 }))}>
                <Line type="monotone" dataKey="value" stroke="var(--color-info)" strokeWidth={2} dot={false} isAnimationActive={true} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="surface bento-highlight-top metric-card p-8 flex flex-col h-40 relative">
          <div className="text-secondary text-sm font-semibold tracking-wider uppercase mb-1 flex items-center gap-2">
            <Users size={16} className="text-brand" /> Unique Obligors
          </div>
          <div className="text-3xl font-bold font-mono text-primary mt-2">{data.obligor_count}</div>
          <div className="absolute bottom-4 right-4 sparkline-container">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={Array.from({ length: 12 }, (_, i) => ({ value: 450 + Math.random() * 10 + i * 1 }))}>
                <Line type="monotone" dataKey="value" stroke="var(--color-positive)" strokeWidth={2} dot={false} isAnimationActive={true} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="surface bento-highlight-top alert bg-warning-bg border-warning/30 p-8 flex flex-col h-40">
          <div className="text-warning text-sm font-semibold tracking-wider uppercase mb-1 flex items-center gap-2">
            <AlertCircle size={16} /> Concentration Risk
          </div>
          <div className="text-sm font-medium mt-auto">
            {data.concentration_indicators.length > 0 ? (
              <ul className="pl-4 m-0 text-warning">
                {data.concentration_indicators.slice(0, 2).map((c, i) => <li key={i} className="mb-1">{c}</li>)}
              </ul>
            ) : (
              <span className="text-positive">Well diversified</span>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 mt-4">
        <div className="surface p-6">
          <h3 className="text-base mb-6 flex items-center gap-2">
            <Building2 size={18} className="text-secondary" /> Sector Exposure
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data.sector_distribution}
                  dataKey="ead"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  innerRadius={60}
                  paddingAngle={2}
                >
                  {data.sector_distribution.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--bg-surface-active)', borderColor: 'var(--border-strong)' }}
                  itemStyle={{ color: 'var(--text-primary)' }}
                  formatter={(value: any) => formatCurrency(value)}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="surface p-6">
          <h3 className="text-base mb-6 flex items-center gap-2">
            <MapPin size={18} className="text-secondary" /> Geography Distribution
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.geography_distribution} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" tickFormatter={(v) => formatCurrency(v)} stroke="var(--border-strong)" tick={{fill: 'var(--text-secondary)'}} />
                <YAxis dataKey="name" type="category" width={100} stroke="var(--border-strong)" tick={{fill: 'var(--text-secondary)'}} />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--bg-surface-active)', borderColor: 'var(--border-strong)' }}
                  formatter={(value: any) => formatCurrency(value)}
                  cursor={{ fill: 'var(--bg-surface-hover)' }}
                />
                <Bar dataKey="ead" fill="var(--color-brand)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      
      <div className="surface p-6 mt-4">
        <h3 className="text-base mb-4">Top Obligors</h3>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Obligor</th>
                <th className="text-right">Exposure (EAD)</th>
                <th className="text-right">% of Total</th>
              </tr>
            </thead>
            <tbody>
              {data.top_obligors.map((row, i) => (
                <tr key={i}>
                  <td className="font-medium">{row.obligor}</td>
                  <td className="text-right font-mono">{formatCurrency(row.ead)}</td>
                  <td className="text-right font-mono">{(row.pct * 100).toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
