import React, { useState } from 'react';
import {
  FileSpreadsheet,
  FileText,
  Copy,
  Check,
  RotateCcw,
  Loader2,
  TableProperties,
  UploadCloud,
} from 'lucide-react';
import { ExtractedItem, MedicineBatch } from '../types';
import {
  downloadCsv,
  downloadTxt,
  downloadExcel,
  downloadMedicineCsv,
  downloadMedicineTxt,
} from '../api';

interface DownloadBarProps {
  items: ExtractedItem[];
  medicineBatch?: MedicineBatch | null;
  sourceUrl: string;
  pageTitle: string;
  mode: string;
  fullTextPreview: string;
  onReset: () => void;
  onNotify: (msg: string, type: 'success' | 'error') => void;
  onOpenPushModal: () => void;
}

export const DownloadBar: React.FC<DownloadBarProps> = ({
  items,
  medicineBatch,
  sourceUrl,
  pageTitle,
  mode,
  fullTextPreview,
  onReset,
  onNotify,
  onOpenPushModal,
}) => {
  const [downloadingExcel, setDownloadingExcel] = useState(false);
  const [downloadingCsv, setDownloadingCsv] = useState(false);
  const [downloadingTxt, setDownloadingTxt] = useState(false);
  const [copied, setCopied] = useState(false);

  const hasItems = items && items.length > 0;
  const hasMedicine = medicineBatch && medicineBatch.records && medicineBatch.records.length > 0;

  const handleDownloadExcel = async () => {
    if (!hasMedicine || downloadingExcel) return;
    try {
      setDownloadingExcel(true);
      const filename = await downloadExcel(medicineBatch, sourceUrl);
      onNotify(`Downloaded Excel Workbook: ${filename}`, 'success');
    } catch (err: any) {
      onNotify(err.message || 'Failed to download Excel.', 'error');
    } finally {
      setDownloadingExcel(false);
    }
  };

  const handleDownloadCsv = async () => {
    if (downloadingCsv) return;
    try {
      setDownloadingCsv(true);
      if (hasMedicine) {
        const filename = await downloadMedicineCsv(medicineBatch, sourceUrl);
        onNotify(`Downloaded Dynamic CSV (${medicineBatch.all_discovered_fields.length} columns): ${filename}`, 'success');
      } else if (hasItems) {
        const filename = await downloadCsv(items, sourceUrl, pageTitle);
        onNotify(`Downloaded CSV: ${filename}`, 'success');
      }
    } catch (err: any) {
      onNotify(err.message || 'Failed to download CSV.', 'error');
    } finally {
      setDownloadingCsv(false);
    }
  };

  const handleDownloadTxt = async () => {
    if (downloadingTxt) return;
    try {
      setDownloadingTxt(true);
      if (hasMedicine) {
        const filename = await downloadMedicineTxt(medicineBatch, sourceUrl);
        onNotify(`Downloaded Medicine Record TXT: ${filename}`, 'success');
      } else if (hasItems) {
        const filename = await downloadTxt(items, sourceUrl, pageTitle, mode);
        onNotify(`Downloaded TXT: ${filename}`, 'success');
      }
    } catch (err: any) {
      onNotify(err.message || 'Failed to download TXT.', 'error');
    } finally {
      setDownloadingTxt(false);
    }
  };

  const handleCopyText = async () => {
    if (!fullTextPreview) return;
    try {
      await navigator.clipboard.writeText(fullTextPreview);
      setCopied(true);
      onNotify('Complete extracted text copied to clipboard!', 'success');
      setTimeout(() => setCopied(false), 2500);
    } catch {
      onNotify('Clipboard access failed.', 'error');
    }
  };

  return (
    <div className="w-full max-w-7xl mx-auto glass-panel p-4 rounded-2xl border border-slate-800 shadow-xl flex flex-col lg:flex-row items-center justify-between gap-4">
      {/* Left side actions: Reset & Copy */}
      <div className="flex items-center gap-2 w-full lg:w-auto">
        <button
          type="button"
          onClick={onReset}
          className="flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition active:scale-95"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>New URL</span>
        </button>

        <button
          type="button"
          onClick={handleCopyText}
          disabled={!hasItems}
          className="flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-700/80 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition active:scale-95 disabled:opacity-50"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5 text-slate-400" />
              <span>Copy Text</span>
            </>
          )}
        </button>

        {hasMedicine && (
          <button
            type="button"
            onClick={onOpenPushModal}
            className="flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-slate-900 border border-purple-500/40 hover:bg-purple-950/40 text-purple-300 hover:text-white text-xs font-semibold transition active:scale-95 shadow-sm"
          >
            <UploadCloud className="w-3.5 h-3.5 text-purple-400" />
            <span>Push to Spreadsheet</span>
          </button>
        )}
      </div>

      {/* Right side: Prominent Download Buttons */}
      <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-end">
        {/* Download Excel (.xlsx) Button */}
        {hasMedicine && (
          <button
            type="button"
            onClick={handleDownloadExcel}
            disabled={downloadingExcel}
            className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 via-teal-500 to-emerald-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-bold text-xs md:text-sm tracking-wide shadow-lg shadow-emerald-500/25 disabled:opacity-50 disabled:pointer-events-none transition active:scale-[0.98]"
          >
            {downloadingExcel ? (
              <Loader2 className="w-4 h-4 animate-spin text-slate-950" />
            ) : (
              <TableProperties className="w-4 h-4 text-slate-950" />
            )}
            <span>Download Excel</span>
            <span className="text-[10px] bg-slate-950/20 px-1.5 py-0.5 rounded text-slate-950 font-mono font-bold">
              .XLSX
            </span>
          </button>
        )}

        {/* Download CSV Button */}
        <button
          type="button"
          onClick={handleDownloadCsv}
          disabled={(!hasItems && !hasMedicine) || downloadingCsv}
          className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-100 font-semibold text-xs md:text-sm border border-slate-700 disabled:opacity-50 disabled:pointer-events-none transition active:scale-[0.98]"
        >
          {downloadingCsv ? (
            <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
          ) : (
            <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
          )}
          <span>Download CSV</span>
          <span className="text-[10px] bg-slate-900 px-1.5 py-0.5 rounded text-slate-400 font-mono">
            {hasMedicine ? `${medicineBatch.records.length} recs` : `${items.length} rows`}
          </span>
        </button>

        {/* Download TXT Button */}
        <button
          type="button"
          onClick={handleDownloadTxt}
          disabled={(!hasItems && !hasMedicine) || downloadingTxt}
          className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-100 font-semibold text-xs md:text-sm border border-slate-700 disabled:opacity-50 disabled:pointer-events-none transition active:scale-[0.98]"
        >
          {downloadingTxt ? (
            <Loader2 className="w-4 h-4 animate-spin text-sky-400" />
          ) : (
            <FileText className="w-4 h-4 text-sky-400" />
          )}
          <span>Download TXT</span>
        </button>
      </div>
    </div>
  );
};
