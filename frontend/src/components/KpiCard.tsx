import { ResponsiveContainer, LineChart, Line } from 'recharts';
import { ArrowUpRight, ArrowDownRight, type LucideIcon } from 'lucide-react';
import { motion } from 'framer-motion';

interface KpiCardProps {
  title: string;
  value: string | number;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string | number;
  icon: LucideIcon;
  sparklineData?: { value: number }[];
}

export default function KpiCard({ title, value, trend, trendValue, icon: Icon, sparklineData }: KpiCardProps) {
  const isPositive = trend === 'up';
  
  return (
    <motion.div 
      whileHover={{ y: -2, boxShadow: '0 10px 30px -5px rgba(15, 23, 42, 0.08)' }}
      className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 flex flex-col justify-between transition-colors"
    >
      <div className="flex justify-between items-start">
        <div className="flex flex-col">
          <span className="text-sm font-medium text-gray-500 mb-1">{title}</span>
          <span className="text-3xl font-semibold text-gray-900 tracking-tight">{value}</span>
        </div>
        <div className="p-3 bg-teal-50/50 rounded-xl text-teal-600">
          <Icon size={22} strokeWidth={2} />
        </div>
      </div>
      
      {(trend || sparklineData) && (
        <div className="mt-6 flex items-end justify-between">
          {trend && (
            <div className={`flex items-center text-sm font-medium ${isPositive ? 'text-teal-600' : 'text-red-500'}`}>
              {isPositive ? <ArrowUpRight size={16} className="mr-1" /> : <ArrowDownRight size={16} className="mr-1" />}
              <span>{trendValue}</span>
            </div>
          )}
          {sparklineData && (
            <div className="w-24 h-8 ml-auto">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sparklineData}>
                  <Line 
                    type="monotone" 
                    dataKey="value" 
                    stroke={isPositive ? '#0d9488' : '#e11d48'} 
                    strokeWidth={2} 
                    dot={false} 
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}
