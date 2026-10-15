import React, { useEffect, useState } from 'react';
import { Loader2, ShieldCheck, DownloadCloud, Trash2, ListOrdered } from 'lucide-react';

const STEPS = [
  {
    title: 'Validating Target URL & SSRF Rules',
    desc: 'Checking protocol safety and ensuring destination is not an internal or cloud metadata IP.',
    icon: ShieldCheck,
  },
  {
    title: 'Fetching Webpage HTML',
    desc: 'Connecting via asynchronous HTTP client with size limits (or Playwright browser fallback).',
    icon: DownloadCloud,
  },
  {
    title: 'Sanitizing DOM & Excluding Visual Clutter',
    desc: 'Stripping images, SVGs, canvas, CSS stylesheets, scripts, and hidden elements.',
    icon: Trash2,
  },
  {
    title: 'Structuring Content & Reading Order',
    desc: 'Extracting headings, paragraphs, lists, tables, and calculating word counts.',
    icon: ListOrdered,
  },
];

export const LoadingState: React.FC = () => {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setActiveStep((prev) => (prev < STEPS.length - 1 ? prev + 1 : prev));
    }, 1200);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="w-full max-w-2xl mx-auto glass-panel p-8 rounded-2xl border border-slate-800/80 shadow-2xl my-8">
      <div className="flex items-center justify-between pb-6 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <Loader2 className="w-6 h-6 text-brand-500 animate-spin" />
          <h3 className="text-lg font-bold text-slate-100">Scraping & Extracting Web Content</h3>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20 font-semibold">
          Processing
        </span>
      </div>

      <div className="mt-6 space-y-4">
        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isDone = idx < activeStep;
          const isCurrent = idx === activeStep;

          return (
            <div
              key={step.title}
              className={`flex items-start gap-3.5 p-3 rounded-xl transition-all ${
                isCurrent
                  ? 'bg-slate-900 border border-brand-500/30 shadow-md'
                  : isDone
                  ? 'opacity-85'
                  : 'opacity-40'
              }`}
            >
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                  isDone
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    : isCurrent
                    ? 'bg-brand-500 text-slate-950 animate-pulse'
                    : 'bg-slate-800 text-slate-500'
                }`}
              >
                <Icon className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <h4
                    className={`text-sm font-semibold ${
                      isCurrent ? 'text-brand-300' : isDone ? 'text-slate-200' : 'text-slate-400'
                    }`}
                  >
                    {step.title}
                  </h4>
                  {isCurrent && (
                    <span className="text-[11px] text-brand-400 animate-pulse">Running...</span>
                  )}
                  {isDone && (
                    <span className="text-[11px] text-emerald-400">Completed</span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{step.desc}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
