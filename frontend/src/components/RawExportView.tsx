import React, { useState } from 'react';
import { ExtractedItem } from '../types';
import { Copy, Check, FileSpreadsheet, FileText } from 'lucide-react';

interface RawExportViewProps {
  items: ExtractedItem[];
  sourceUrl: string;
  pageTitle: string;
  fullTextPreview: string;
  onNotify: (msg: string, type: 'success' | 'error') => void;
}

export const RawExportView: React.FC<RawExportViewProps> = ({
  items,
  sourceUrl,
  pageTitle,
  fullTextPreview,
  onNotify,
}) => {
  const [format, setFormat] = useState<'csv' | 'txt'>('csv');
  const [copied, setCopied] = useState(false);

  // Generate CSV text snippet for preview
  const csvSnippet = React.useMemo(() => {
    const header = 'source_url,page_title,content_type,heading,text_content,sequence_number,extracted_at\n';
    const rows = items.slice(0, 100).map((item) => {
      const escape = (val: string | null) => {
        if (!val) return '""';
        const str = String(val).replace(/"/g, '""');
        return `"${str}"`;
      };
      return [
        escape(item.source_url),
        escape(item.page_title),
        escape(item.content_type),
        escape(item.heading),
        escape(item.text_content),
        item.sequence_number,
        escape(item.extracted_at),
      ].join(',');
    }).join('\n');

    return header + rows;
  }, [items]);

  const activeContent = format === 'csv' ? csvSnippet : fullTextPreview;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(activeContent);
      setCopied(true);
      onNotify(`Copied ${format.toUpperCase()} preview to clipboard!`, 'success');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      onNotify('Clipboard copy failed.', 'error');
    }
  };

  return (
    <div className="glass-panel rounded-2xl border border-slate-800 shadow-2xl overflow-hidden max-w-5xl mx-auto">
      {/* Format Toggle Bar */}
      <div className="px-5 py-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setFormat('csv')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              format === 'csv'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>CSV Preview (RFC-4180 / Excel BOM)</span>
          </button>
          <button
            type="button"
            onClick={() => setFormat('txt')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              format === 'txt'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>TXT Preview (Reading Order)</span>
          </button>
        </div>

        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium transition"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5 text-slate-400" />
              <span>Copy Raw {format.toUpperCase()}</span>
            </>
          )}
        </button>
      </div>

      {/* Code Viewer */}
      <div className="p-4 bg-slate-950 font-mono text-xs text-slate-300 max-h-[500px] overflow-auto select-all leading-relaxed whitespace-pre-wrap">
        {activeContent}
      </div>

      <div className="px-4 py-2.5 bg-slate-900/60 border-t border-slate-800 text-[11px] text-slate-500 flex items-center justify-between">
        <span>Showing first 100 rows for preview. Full file download contains all {items.length} records.</span>
        <span>Encoding: UTF-8</span>
      </div>
    </div>
  );
};
