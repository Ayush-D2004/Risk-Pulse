import { useQuery } from '@tanstack/react-query';
import { fetchPortfolio } from '../api/client';
import KpiCard from '../components/KpiCard';
import { DollarSign, Users, Briefcase, Loader2, AlertCircle } from 'lucide-react';
import { formatCurrency } from '../utils/formatters';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';

const COLORS = ['#0f766e', '#0369a1', '#6d28d9', '#be123c', '#b45309', '#047857', '#1d4ed8'];

export default function PortfolioOverview() {
  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['portfolio'],
    queryFn: fetchPortfolio,
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-teal-600" />
      </div>
    );
  }

  if (isError || !response) {
    return (
      <div className="flex h-full items-center justify-center flex-col text-red-500">
        <AlertCircle className="w-12 h-12 mb-4" />
        <h2 className="text-xl font-semibold">Failed to load portfolio data</h2>
        <p className="text-gray-500 mt-2">Please ensure the backend is running on port 8000.</p>
      </div>
    );
  }

  const { data } = response;

  return (
    <div className="max-w-7xl mx-auto space-y-8 pb-12">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Portfolio Overview</h1>
          <p className="text-sm text-gray-500 mt-1">Aggregated wholesale banking exposure metrics.</p>
        </div>
        <button className="px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium rounded-xl shadow-sm transition-colors">
          Download Report
        </button>
      </div>

      {/* KPI GRID */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <KpiCard 
          title="Total Exposure (EAD)" 
          value={formatCurrency(data.total_ead as any)} 
          icon={DollarSign}
        />
        <KpiCard 
          title="Total Exposures (Facilities)" 
          value={data.exposure_count.toLocaleString()} 
          icon={Briefcase}
        />
        <KpiCard 
          title="Unique Obligors" 
          value={data.obligor_count.toLocaleString()} 
          icon={Users}
        />
      </div>

      {/* CHARTS GRID */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* SECTOR DISTRIBUTION DONUT */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 flex flex-col hover:shadow-md transition-shadow">
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900">Sector Distribution</h2>
            <p className="text-sm text-gray-500">Exposure at Default by Industry</p>
          </div>
          <div className="flex-1 min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data.sector_distribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="ead"
                  nameKey="name"
                  stroke="none"
                >
                  {data.sector_distribution.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <RechartsTooltip 
                  formatter={(value: any) => formatCurrency(value)}
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)', padding: '12px' }}
                  itemStyle={{ fontSize: '13px', fontWeight: 600 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* GEOGRAPHY DISTRIBUTION BAR */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 flex flex-col hover:shadow-md transition-shadow">
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900">Geography Distribution</h2>
            <p className="text-sm text-gray-500">Exposure at Default by Region</p>
          </div>
          <div className="flex-1 min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.geography_distribution} layout="vertical" margin={{ top: 0, right: 30, left: 40, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                <XAxis type="number" tickFormatter={(val) => formatCurrency(val)} axisLine={false} tickLine={false} tick={{fill: '#64748b', fontSize: 12}} />
                <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{fill: '#475569', fontSize: 13, fontWeight: 500}} />
                <RechartsTooltip 
                  cursor={{fill: '#f8fafc'}}
                  formatter={(value: any) => formatCurrency(value)}
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 30px -5px rgba(0,0,0,0.1)', padding: '12px' }}
                />
                <Bar dataKey="ead" fill="#0f766e" radius={[0, 4, 4, 0]} barSize={24} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* TOP OBLIGORS TABLE */}
      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900">Top Obligor Concentrations</h2>
          <p className="text-sm text-gray-500">Largest single-name exposures in the portfolio</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-500 uppercase bg-gray-50/50 border-b border-gray-100">
              <tr>
                <th className="px-6 py-4 font-semibold tracking-wider rounded-tl-xl">Obligor Name</th>
                <th className="px-6 py-4 font-semibold tracking-wider text-right">Exposure (EAD)</th>
                <th className="px-6 py-4 font-semibold tracking-wider text-right rounded-tr-xl">% of Total</th>
              </tr>
            </thead>
            <tbody>
              {data.top_obligors.map((row, idx) => (
                <tr key={idx} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                  <td className="px-6 py-4 font-medium text-gray-900">{row.obligor}</td>
                  <td className="px-6 py-4 text-right text-gray-600 font-mono">{formatCurrency(row.ead as any)}</td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <span className="text-gray-600 font-medium">{(row.pct * 100).toFixed(2)}%</span>
                      <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-teal-500 rounded-full" 
                          style={{ width: `${Math.min(row.pct * 100 * 2, 100)}%` }}
                        />
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
