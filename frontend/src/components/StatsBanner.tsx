import React from 'react';
import { ExternalLink, Clock, Type, AlignLeft, Layers, AlertCircle, Cpu, FileCheck } from 'lucide-react';
import { ExtractResponse } from '../types';

interface StatsBannerProps {
  data: ExtractResponse;
}

export const StatsBanner: React.FC<StatsBannerProps> = ({ data }) => {
  const { stats, page_title, source_url, engine_used, mode, warnings, extracted_at } = data;

  const formattedDate = new Date(extracted_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <div className="w-full max-w-7xl mx-auto space-y-4">
      {/* Title & Source Card */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Extracted Successfully
              </span>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                Mode: {mode === 'main' ? 'Main Content' : 'Full Page'}
              </span>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20 flex items-center gap-1">
                <Cpu className="w-3 h-3" /> {engine_used}
              </span>
              <span className="text-[11px] text-slate-500">
                at {formattedDate} ({stats.duration_ms} ms)
              </span>
            </div>

            <h2 className="text-xl md:text-2xl font-bold text-slate-100 truncate mt-1">
              {page_title || 'Untitled Page'}
            </h2>

            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <span className="text-slate-500">Source:</span>
              <a
                href={source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-400 hover:text-brand-300 hover:underline flex items-center gap-1 truncate max-w-xl"
              >
                <span>{source_url}</span>
                <ExternalLink className="w-3 h-3 shrink-0" />
              </a>
            </div>
          </div>
        </div>

        {/* Warnings Banner if any */}
        {warnings && warnings.length > 0 && (
          <div className="mt-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-2.5 text-xs text-amber-300">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
            <div className="space-y-0.5">
              <span className="font-semibold">Notice:</span>
              <ul className="list-disc list-inside space-y-0.5 text-amber-200/90">
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <div className="glass-panel p-3.5 rounded-xl border border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">{stats.block_count.toLocaleString()}</div>
            <div className="text-[11px] text-slate-400">Total Blocks</div>
          </div>
        </div>

        <div className="glass-panel p-3.5 rounded-xl border border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 flex items-center justify-center shrink-0">
            <AlignLeft className="w-4 h-4" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">{stats.word_count.toLocaleString()}</div>
            <div className="text-[11px] text-slate-400">Word Count</div>
          </div>
        </div>

        <div className="glass-panel p-3.5 rounded-xl border border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0">
            <Type className="w-4 h-4" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">{stats.character_count.toLocaleString()}</div>
            <div className="text-[11px] text-slate-400">Characters</div>
          </div>
        </div>

        <div className="glass-panel p-3.5 rounded-xl border border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">{stats.reading_time_minutes} min</div>
            <div className="text-[11px] text-slate-400">Reading Time</div>
          </div>
        </div>

        <div className="glass-panel p-3.5 rounded-xl border border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center shrink-0">
            <FileCheck className="w-4 h-4" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">{stats.headings_count}</div>
            <div className="text-[11px] text-slate-400">Headings</div>
          </div>
        </div>

        <div className="glass-panel p-3.5 rounded-xl border border-slate-800 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center shrink-0">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">
              {stats.lists_count} li / {stats.tables_count} tbl
            </div>
            <div className="text-[11px] text-slate-400">Lists & Tables</div>
          </div>
        </div>
      </div>
    </div>
  );
};
