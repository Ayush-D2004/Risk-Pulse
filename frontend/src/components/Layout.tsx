import { Link, useLocation } from 'react-router-dom';
import { Search, Bell, Settings, LayoutDashboard, AlertTriangle, PieChart as PieChartIcon, TrendingUp, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const navItems = [
    { name: 'Portfolio Overview', path: '/', icon: LayoutDashboard },
    { name: 'Event Stress', path: '/events', icon: AlertTriangle },
    { name: 'Risk Attribution', path: '/attribution', icon: PieChartIcon },
    { name: 'Market Scenarios', path: '/compare', icon: TrendingUp },
  ];

  return (
    <div className="flex h-screen bg-[#f4f7f6] overflow-hidden font-sans">
      {/* LEFT SIDEBAR */}
      <aside className="w-64 bg-white border-r border-gray-100 flex flex-col justify-between flex-shrink-0 z-20 shadow-sm">
        <div>
          <div className="h-20 flex items-center px-8 border-b border-gray-50">
            <Link to="/" className="flex items-center gap-2 text-teal-700 font-bold text-xl tracking-tight">
              <Activity size={26} strokeWidth={2.5} />
              RiskPulse
            </Link>
          </div>
          <nav className="p-4 space-y-1">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  to={item.path}
                  className={`flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-xl transition-all duration-200 ${
                    isActive 
                      ? 'bg-teal-50 text-teal-700 shadow-sm' 
                      : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
                  }`}
                >
                  <Icon size={18} className={isActive ? 'text-teal-600' : 'text-gray-400'} />
                  {item.name}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="p-4 border-t border-gray-50">
          <button className="w-full flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-xl text-gray-500 hover:text-gray-900 hover:bg-gray-50 transition-colors">
            <Settings size={18} className="text-gray-400" />
            Settings
          </button>
        </div>
      </aside>

      {/* MAIN CONTENT AREA */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        {/* TOP APP BAR */}
        <header className="h-20 bg-white/80 backdrop-blur-md border-b border-gray-100 flex items-center justify-between px-8 flex-shrink-0 z-10 sticky top-0">
          <div className="flex-1 flex items-center max-w-md">
            <div className="relative w-full">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Search className="h-5 w-5 text-gray-400" />
              </div>
              <input 
                type="text" 
                className="block w-full pl-10 pr-3 py-2.5 border border-transparent bg-gray-50 rounded-full text-sm placeholder-gray-400 focus:outline-none focus:ring-0 focus:border-teal-500 focus:bg-white transition-all hover:bg-gray-100" 
                placeholder="Search portfolios, securities, or scenarios..." 
              />
            </div>
          </div>
          <div className="flex items-center gap-6">
            <button className="text-gray-400 hover:text-gray-900 transition-colors relative">
              <Bell size={20} />
              <span className="absolute top-0 right-0 block h-2 w-2 rounded-full bg-red-500 ring-2 ring-white transform translate-x-1/2 -translate-y-1/2"></span>
            </button>
            <div className="flex items-center gap-3 border-l border-gray-200 pl-6 cursor-pointer group">
              <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-teal-600 to-teal-400 text-white flex items-center justify-center font-semibold text-sm shadow-sm group-hover:shadow transition-all">
                AS
              </div>
              <div className="hidden md:block">
                <p className="text-sm font-medium text-gray-900">Ayush S.</p>
                <p className="text-xs text-gray-500">Lead Analyst</p>
              </div>
            </div>
          </div>
        </header>

        {/* SCROLLABLE WORKSPACE WITH PAGE TRANSITIONS */}
        <main className="flex-1 overflow-y-auto p-8 relative">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="h-full"
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
