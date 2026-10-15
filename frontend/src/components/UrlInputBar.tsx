import React, { useState } from 'react';
import { Globe, ArrowRight, Sparkles, BookOpen, Layers, Terminal } from 'lucide-react';

interface UrlInputBarProps {
  onSubmit: (url: string, mode: 'main' | 'full', forceBrowser: boolean) => void;
  isLoading: boolean;
}

const SAMPLE_URLS = [
  {
    label: 'Wikipedia (AI Article)',
    url: 'https://en.wikipedia.org/wiki/Artificial_intelligence',
    mode: 'main' as const,
    icon: BookOpen,
  },
  {
    label: 'Python HTTPX Docs',
    url: 'https://www.python-httpx.org/',
    mode: 'main' as const,
    icon: Terminal,
  },
  {
    label: 'Hacker News (Lists & Links)',
    url: 'https://news.ycombinator.com/',
    mode: 'full' as const,
    icon: Layers,
  },
];

export const UrlInputBar: React.FC<UrlInputBarProps> = ({ onSubmit, isLoading }) => {
  const [url, setUrl] = useState('');
  const [mode, setMode] = useState<'main' | 'full'>('main');
  const [forceBrowser, setForceBrowser] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim() || isLoading) return;
    onSubmit(url.trim(), mode, forceBrowser);
  };

  const handleSelectSample = (sampleUrl: string, sampleMode: 'main' | 'full') => {
    setUrl(sampleUrl);
    setMode(sampleMode);
    onSubmit(sampleUrl, sampleMode, forceBrowser);
  };

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      <form onSubmit={handleSubmit} className="relative">
        <div className="glass-panel p-2.5 rounded-2xl shadow-2xl transition-all border border-slate-800/90 focus-within:border-brand-500/50 focus-within:ring-2 focus-within:ring-brand-500/20">
          <div className="flex flex-col md:flex-row gap-2">
            {/* Input field */}
            <div className="relative flex-1 flex items-center">
              <Globe className="absolute left-3.5 w-5 h-5 text-slate-400 pointer-events-none" />
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Enter any webpage URL (e.g. https://example.com/article)"
                disabled={isLoading}
                className="w-full pl-11 pr-4 py-3 bg-slate-900/60 rounded-xl text-slate-100 placeholder-slate-500 text-sm md:text-base outline-none focus:bg-slate-900 border border-slate-800/60 transition"
              />
            </div>

            {/* Mode Selector and Submit Button */}
            <div className="flex items-center gap-2">
              <div className="bg-slate-900/80 p-1 rounded-xl border border-slate-800/80 flex items-center text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setMode('main')}
                  className={`px-3 py-2 rounded-lg transition-all ${
                    mode === 'main'
                      ? 'bg-brand-500 text-slate-950 font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Extracts primary article or documentation content (excludes headers, navbars, footers)"
                >
                  Main Content
                </button>
                <button
                  type="button"
                  onClick={() => setMode('full')}
                  className={`px-3 py-2 rounded-lg transition-all ${
                    mode === 'full'
                      ? 'bg-brand-500 text-slate-950 font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Extracts all visible text on the page including navigation and headers"
                >
                  Full Page
                </button>
              </div>

              <button
                type="submit"
                disabled={isLoading || !url.trim()}
                className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-brand-500 to-emerald-600 hover:from-brand-600 hover:to-emerald-700 text-slate-950 font-bold text-sm tracking-wide shadow-lg shadow-brand-500/25 disabled:opacity-50 disabled:pointer-events-none transition active:scale-[0.98]"
              >
                <span>{isLoading ? 'Scraping...' : 'Extract Content'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Browser Rendering Toggle */}
          <div className="mt-2.5 pt-2 border-t border-slate-800/60 px-2 flex items-center justify-between text-xs text-slate-400">
            <label className="flex items-center gap-2 cursor-pointer hover:text-slate-200 select-none">
              <input
                type="checkbox"
                checked={forceBrowser}
                onChange={(e) => setForceBrowser(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-slate-700 text-brand-500 focus:ring-brand-500 bg-slate-900 accent-emerald-500"
              />
              <span>Force Headless Browser (Render dynamic JavaScript SPAs)</span>
            </label>
            <span className="text-[11px] text-slate-500">
              Auto-detects JS fallback if disabled
            </span>
          </div>
        </div>
      </form>

      {/* Quick sample pills */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-500 flex items-center gap-1 font-medium mr-1">
          <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Quick Samples:
        </span>
        {SAMPLE_URLS.map((sample) => {
          const Icon = sample.icon;
          return (
            <button
              key={sample.label}
              type="button"
              onClick={() => handleSelectSample(sample.url, sample.mode)}
              disabled={isLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900/60 border border-slate-800 hover:border-brand-500/40 hover:bg-slate-850 text-slate-300 hover:text-brand-300 transition text-xs disabled:opacity-50"
            >
              <Icon className="w-3 h-3 text-slate-400" />
              <span>{sample.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
