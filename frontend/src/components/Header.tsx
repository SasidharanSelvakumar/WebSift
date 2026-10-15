import React from 'react';
import { ShieldCheck, Cpu, Filter } from 'lucide-react';
import { HealthStatus } from '../types';

interface HeaderProps {
  health: HealthStatus | null;
}

export const Header: React.FC<HeaderProps> = ({ health }) => {
  return (
    <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-emerald-400 p-0.5 shadow-lg shadow-brand-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Filter className="w-5 h-5 text-brand-500" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                WebSift
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20 uppercase tracking-wider">
                v1.0
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">
              Web Scraping & Content Export Agent
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden md:inline">SSRF Protected</span>
          </div>

          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
            <span>
              {health?.playwright_available ? 'Playwright Ready' : 'HTTP Engine'}
            </span>
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse ml-0.5"></span>
          </div>
        </div>
      </div>
    </header>
  );
};
