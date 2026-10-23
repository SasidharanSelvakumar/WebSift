import React, { useState, useEffect, useRef } from 'react';
import {
  Layers,
  Play,
  Pause,
  Square,
  RotateCw,
  FileSpreadsheet,
  FileText,
  FileCode,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Settings,
  Sparkles,
  RefreshCw,
  Sliders,
  Filter,
} from 'lucide-react';
import {
  CategoryJobResponse,
  CategoryJobProduct,
  CategoryScrapeRequest,
} from '../types';
import {
  startCategoryScrape,
  getCategoryJobStatus,
  pauseCategoryJob,
  resumeCategoryJob,
  stopCategoryJob,
  retryCategoryFailed,
  downloadMasterExcel,
  downloadMasterCsv,
  downloadMasterTxt,
} from '../api';

interface CategoryScraperViewProps {
  onNotify: (message: string, type: 'success' | 'error') => void;
}

const SAMPLE_CATEGORY_URLS = [
  {
    label: 'Tata 1mg Medicines (Alphabet A)',
    url: 'https://www.1mg.com/drugs-all-medicines?label=a',
  },
  {
    label: 'Tata 1mg Medicines (Alphabet B)',
    url: 'https://www.1mg.com/drugs-all-medicines?label=b',
  },
  {
    label: 'Online Pharmacy Catalog',
    url: 'https://example.com/pharmacy/medicines',
  },
];

export const CategoryScraperView: React.FC<CategoryScraperViewProps> = ({ onNotify }) => {
  const [url, setUrl] = useState('');
  const [maxPages, setMaxPages] = useState<number | ''>('');
  const [maxProducts, setMaxProducts] = useState<number | ''>('');
  const [delaySeconds, setDelaySeconds] = useState(1.0);
  const [productSelector, setProductSelector] = useState('');
  const [nextPageSelector, setNextPageSelector] = useState('');
  const [forceBrowser, setForceBrowser] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Active Job State
  const [activeJob, setActiveJob] = useState<CategoryJobResponse | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isExporting, setIsExporting] = useState<'excel' | 'csv' | 'txt' | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const pollIntervalRef = useRef<number | null>(null);

  // Poll active job status
  useEffect(() => {
    if (!activeJob?.job_id) return;

    const shouldPoll = activeJob.job_status === 'running' || activeJob.job_status === 'paused';

    if (shouldPoll) {
      pollIntervalRef.current = window.setInterval(async () => {
        try {
          const updated = await getCategoryJobStatus(activeJob.job_id);
          setActiveJob(updated);

          if (updated.job_status === 'completed') {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            onNotify(
              `Category scraping completed! ${updated.total_completed} products saved to Master Dataset.`,
              'success'
            );
          } else if (updated.job_status === 'failed') {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            onNotify(`Category scraping ended with error: ${updated.error_message || 'Unknown error'}`, 'error');
          }
        } catch (err: any) {
          console.warn('Job polling note:', err);
        }
      }, 1500);
    } else {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [activeJob?.job_id, activeJob?.job_status]);

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim() || isStarting) return;

    setIsStarting(true);
    try {
      const requestPayload: CategoryScrapeRequest = {
        category_url: url.trim(),
        max_pages: maxPages !== '' && Number(maxPages) > 0 ? Number(maxPages) : undefined,
        max_products: maxProducts !== '' && Number(maxProducts) > 0 ? Number(maxProducts) : undefined,
        delay_seconds: Number(delaySeconds),
        product_selector: productSelector.trim() || undefined,
        next_page_selector: nextPageSelector.trim() || undefined,
        force_browser: forceBrowser,
      };

      const job = await startCategoryScrape(requestPayload);
      setActiveJob(job);
      onNotify(`Category scraper job started for ${url.trim()}`, 'success');
    } catch (err: any) {
      onNotify(err.message || 'Failed to start category scrape.', 'error');
    } finally {
      setIsStarting(false);
    }
  };

  const handlePause = async () => {
    if (!activeJob) return;
    try {
      await pauseCategoryJob(activeJob.job_id);
      setActiveJob((prev) => (prev ? { ...prev, job_status: 'paused' } : null));
      onNotify('Scraper paused.', 'success');
    } catch (err: any) {
      onNotify(err.message || 'Failed to pause scraper.', 'error');
    }
  };

  const handleResume = async () => {
    if (!activeJob) return;
    try {
      await resumeCategoryJob(activeJob.job_id);
      setActiveJob((prev) => (prev ? { ...prev, job_status: 'running' } : null));
      onNotify('Scraper resumed.', 'success');
    } catch (err: any) {
      onNotify(err.message || 'Failed to resume scraper.', 'error');
    }
  };

  const handleStop = async () => {
    if (!activeJob) return;
    try {
      await stopCategoryJob(activeJob.job_id);
      setActiveJob((prev) => (prev ? { ...prev, job_status: 'stopped' } : null));
      onNotify('Scraper stopped.', 'success');
    } catch (err: any) {
      onNotify(err.message || 'Failed to stop scraper.', 'error');
    }
  };

  const handleRetryFailed = async () => {
    if (!activeJob) return;
    try {
      const count = await retryCategoryFailed(activeJob.job_id);
      onNotify(`Retrying ${count} failed product(s)...`, 'success');
      const updated = await getCategoryJobStatus(activeJob.job_id);
      setActiveJob(updated);
    } catch (err: any) {
      onNotify(err.message || 'Failed to retry items.', 'error');
    }
  };

  const handleExport = async (format: 'excel' | 'csv' | 'txt') => {
    setIsExporting(format);
    try {
      let filename = '';
      if (format === 'excel') {
        filename = await downloadMasterExcel(activeJob?.job_id);
      } else if (format === 'csv') {
        filename = await downloadMasterCsv(activeJob?.job_id);
      } else {
        filename = await downloadMasterTxt(activeJob?.job_id);
      }
      onNotify(`Exported ${filename} successfully!`, 'success');
    } catch (err: any) {
      onNotify(err.message || `Failed to export ${format.toUpperCase()}`, 'error');
    } finally {
      setIsExporting(null);
    }
  };

  // Progress percentage calculation
  const totalDiscovered = activeJob?.total_discovered || 0;
  const totalCompleted = activeJob?.total_completed || 0;
  const totalFailed = activeJob?.total_failed || 0;
  const totalProcessed = totalCompleted + totalFailed + (activeJob?.total_skipped || 0);
  const progressPercent =
    totalDiscovered > 0 ? Math.min(100, Math.round((totalProcessed / totalDiscovered) * 100)) : 0;

  // Filtered products
  const products = activeJob?.products || [];
  const filteredProducts = products.filter((p) => {
    if (filterStatus === 'all') return true;
    return p.status === filterStatus;
  });

  return (
    <div className="w-full max-w-6xl mx-auto space-y-6">
      {/* Category Scraping Input Panel */}
      <div className="glass-panel p-5 sm:p-6 rounded-2xl shadow-2xl border border-slate-800/90 focus-within:border-brand-500/50 transition">
        <form onSubmit={handleStart} className="space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                  Category-Wide Web Scraping
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    Mode B
                  </span>
                </h2>
                <p className="text-xs text-slate-400">
                  Crawls category listing pages, traverses pagination, extracts all products, and persists immediately to SQLite.
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition py-1 px-2 rounded-lg bg-slate-900/60 border border-slate-800"
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Advanced Crawler Config</span>
              {showAdvanced ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>

          {/* URL Input Bar */}
          <div className="flex flex-col md:flex-row gap-2.5">
            <div className="relative flex-1">
              <input
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="Enter Category or Product Listing URL (e.g. https://pharmacy.example.com/medicines/category)"
                disabled={isStarting || activeJob?.job_status === 'running'}
                className="w-full pl-4 pr-4 py-3 bg-slate-900/80 rounded-xl text-slate-100 placeholder-slate-500 text-sm md:text-base outline-none focus:bg-slate-900 border border-slate-800 focus:border-brand-500/60 transition shadow-inner"
              />
            </div>

            <button
              type="submit"
              disabled={isStarting || !url.trim() || activeJob?.job_status === 'running'}
              className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-slate-950 font-bold text-sm tracking-wide shadow-lg shadow-emerald-500/25 disabled:opacity-50 disabled:pointer-events-none transition active:scale-[0.98] shrink-0"
            >
              <Play className="w-4 h-4 fill-slate-950" />
              <span>{isStarting ? 'Initiating Crawler...' : 'Start Category Scraping'}</span>
            </button>
          </div>

          {/* Collapsible Advanced Settings */}
          {showAdvanced && (
            <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/80 space-y-4 animate-fadeIn text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1">
                  <label className="text-slate-300 font-medium">Max Listing Pages (Optional)</label>
                  <input
                    type="number"
                    min={0}
                    max={10000}
                    placeholder="Unlimited (all pages)"
                    value={maxPages}
                    onChange={(e) => setMaxPages(e.target.value === '' ? '' : Number(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-950/80 rounded-lg border border-slate-800 text-slate-200 outline-none focus:border-brand-500"
                  />
                  <span className="text-[11px] text-slate-500">Traverses all pages unless specified</span>
                </div>

                <div className="space-y-1">
                  <label className="text-slate-300 font-medium">Max Products Cap (Optional)</label>
                  <input
                    type="number"
                    min={0}
                    max={50000}
                    placeholder="Unlimited (all products)"
                    value={maxProducts}
                    onChange={(e) => setMaxProducts(e.target.value === '' ? '' : Number(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-950/80 rounded-lg border border-slate-800 text-slate-200 outline-none focus:border-brand-500"
                  />
                  <span className="text-[11px] text-slate-500">Collects all products unless specified</span>
                </div>

                <div className="space-y-1">
                  <label className="text-slate-300 font-medium">Request Delay (Seconds)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="10.0"
                    value={delaySeconds}
                    onChange={(e) => setDelaySeconds(Number(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-950/80 rounded-lg border border-slate-800 text-slate-200 outline-none focus:border-brand-500"
                  />
                  <span className="text-[11px] text-slate-500">Polite rate-limiting pause</span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-800/60">
                <div className="space-y-1">
                  <label className="text-slate-300 font-medium">Custom Product Link CSS Selector (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. .product-card a.title, [data-sku] a"
                    value={productSelector}
                    onChange={(e) => setProductSelector(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950/80 rounded-lg border border-slate-800 text-slate-200 outline-none focus:border-brand-500"
                  />
                  <span className="text-[11px] text-slate-500">Overrides automatic product link heuristics</span>
                </div>

                <div className="space-y-1">
                  <label className="text-slate-300 font-medium">Custom Next Page CSS Selector (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. a.pagination__next, a[rel='next']"
                    value={nextPageSelector}
                    onChange={(e) => setNextPageSelector(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950/80 rounded-lg border border-slate-800 text-slate-200 outline-none focus:border-brand-500"
                  />
                  <span className="text-[11px] text-slate-500">Overrides automatic pagination discovery</span>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2 border-t border-slate-800/60">
                <label className="flex items-center gap-2 cursor-pointer text-slate-300 select-none">
                  <input
                    type="checkbox"
                    checked={forceBrowser}
                    onChange={(e) => setForceBrowser(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-700 text-emerald-500 focus:ring-emerald-500 bg-slate-950 accent-emerald-500"
                  />
                  <span>Force Headless Browser for Dynamic JS Listing Pages</span>
                </label>
              </div>
            </div>
          )}

          {/* Sample Category URL Pills */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-500 flex items-center gap-1 font-medium mr-1">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Samples:
            </span>
            {SAMPLE_CATEGORY_URLS.map((sample) => (
              <button
                key={sample.label}
                type="button"
                onClick={() => setUrl(sample.url)}
                disabled={isStarting || activeJob?.job_status === 'running'}
                className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-900/60 border border-slate-800 hover:border-emerald-500/40 text-slate-300 hover:text-emerald-300 transition text-xs disabled:opacity-50"
              >
                <span>{sample.label}</span>
              </button>
            ))}
          </div>
        </form>
      </div>

      {/* Live Scraping Job Dashboard */}
      {activeJob && (
        <div className="glass-panel p-5 sm:p-6 rounded-2xl shadow-2xl border border-slate-800/90 space-y-6 animate-fadeIn">
          {/* Top Control & Status Row */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <span className="text-xs text-slate-500 font-mono">JOB ID: {activeJob.job_id}</span>
                {/* Status Badge */}
                <span
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold border uppercase tracking-wider ${
                    activeJob.job_status === 'running'
                      ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40 animate-pulse'
                      : activeJob.job_status === 'paused'
                      ? 'bg-amber-950/80 text-amber-300 border-amber-500/40'
                      : activeJob.job_status === 'completed'
                      ? 'bg-blue-950/80 text-blue-300 border-blue-500/40'
                      : activeJob.job_status === 'stopped'
                      ? 'bg-slate-800 text-slate-300 border-slate-700'
                      : 'bg-rose-950/80 text-rose-300 border-rose-500/40'
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      activeJob.job_status === 'running'
                        ? 'bg-emerald-400'
                        : activeJob.job_status === 'paused'
                        ? 'bg-amber-400'
                        : activeJob.job_status === 'completed'
                        ? 'bg-blue-400'
                        : 'bg-rose-400'
                    }`}
                  />
                  {activeJob.job_status}
                </span>
              </div>
              <p className="text-xs text-slate-400 truncate max-w-xl">
                <span className="font-semibold text-slate-300">Target Category:</span> {activeJob.category_url}
              </p>
            </div>

            {/* Scraper Control Buttons */}
            <div className="flex items-center gap-2">
              {activeJob.job_status === 'running' && (
                <button
                  type="button"
                  onClick={handlePause}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-semibold transition"
                >
                  <Pause className="w-3.5 h-3.5" />
                  <span>Pause</span>
                </button>
              )}

              {activeJob.job_status === 'paused' && (
                <button
                  type="button"
                  onClick={handleResume}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-semibold transition"
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>Resume</span>
                </button>
              )}

              {(activeJob.job_status === 'running' || activeJob.job_status === 'paused') && (
                <button
                  type="button"
                  onClick={handleStop}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-semibold transition"
                >
                  <Square className="w-3.5 h-3.5" />
                  <span>Stop</span>
                </button>
              )}

              {activeJob.total_failed > 0 && activeJob.job_status !== 'running' && (
                <button
                  type="button"
                  onClick={handleRetryFailed}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-brand-500/10 hover:bg-brand-500/20 text-brand-300 border border-brand-500/30 text-xs font-semibold transition"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Retry Failed ({activeJob.total_failed})</span>
                </button>
              )}
            </div>
          </div>

          {/* 5 KPI Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-center space-y-1">
              <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Pages Visited</span>
              <div className="text-xl sm:text-2xl font-black text-slate-100">{activeJob.pages_visited}</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-center space-y-1">
              <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Discovered</span>
              <div className="text-xl sm:text-2xl font-black text-sky-400">{activeJob.total_discovered}</div>
            </div>

            <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-500/20 text-center space-y-1">
              <span className="text-[11px] font-medium text-emerald-400 uppercase tracking-wider">Completed</span>
              <div className="text-xl sm:text-2xl font-black text-emerald-400">{activeJob.total_completed}</div>
            </div>

            <div className="p-3.5 rounded-xl bg-rose-950/20 border border-rose-500/20 text-center space-y-1">
              <span className="text-[11px] font-medium text-rose-400 uppercase tracking-wider">Failed</span>
              <div className="text-xl sm:text-2xl font-black text-rose-400">{activeJob.total_failed}</div>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-center space-y-1 col-span-2 sm:col-span-1">
              <span className="text-[11px] font-medium text-amber-400 uppercase tracking-wider">Pending</span>
              <div className="text-xl sm:text-2xl font-black text-amber-400">
                {Math.max(
                  0,
                  activeJob.total_discovered - activeJob.total_completed - activeJob.total_failed - activeJob.total_skipped
                )}
              </div>
            </div>
          </div>

          {/* Progress Bar & Current Activity Ticker */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5 font-medium">
                <Clock className="w-3.5 h-3.5 text-brand-400" /> Overall Progress
              </span>
              <span className="font-bold text-slate-200">{progressPercent}%</span>
            </div>
            <div className="w-full h-2.5 rounded-full bg-slate-900 border border-slate-800 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-brand-500 via-emerald-500 to-teal-400 transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>

            {/* Current Activity Ticker */}
            {activeJob.job_status === 'running' && (
              <div className="text-[11px] text-slate-400 font-mono truncate pt-1 bg-slate-950/40 px-3 py-1.5 rounded-lg border border-slate-900">
                {activeJob.current_product_url ? (
                  <span>Scraping product: <span className="text-emerald-400">{activeJob.current_product_url}</span></span>
                ) : activeJob.current_page_url ? (
                  <span>Crawling listing page: <span className="text-sky-400">{activeJob.current_page_url}</span></span>
                ) : (
                  <span>Preparing next batch...</span>
                )}
              </div>
            )}
          </div>

          {/* Master Dataset Export Bar */}
          <div className="p-4 rounded-xl bg-gradient-to-r from-emerald-950/30 via-slate-900/60 to-slate-900/80 border border-emerald-500/30 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                Export Combined Master Dataset
              </h3>
              <p className="text-xs text-slate-400">
                Generates a single consolidated file containing all successfully stored products from SQLite with dynamic columns.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
              {/* Excel Master */}
              <button
                type="button"
                onClick={() => handleExport('excel')}
                disabled={isExporting !== null || activeJob.total_completed === 0}
                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs shadow-lg shadow-emerald-500/20 disabled:opacity-50 transition active:scale-[0.98] flex-1 sm:flex-none"
              >
                <FileSpreadsheet className="w-4 h-4" />
                <span>{isExporting === 'excel' ? 'Generating...' : 'Master Excel (.xlsx)'}</span>
              </button>

              {/* CSV Master */}
              <button
                type="button"
                onClick={() => handleExport('csv')}
                disabled={isExporting !== null || activeJob.total_completed === 0}
                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-slate-950 font-bold text-xs shadow-lg shadow-teal-500/20 disabled:opacity-50 transition active:scale-[0.98] flex-1 sm:flex-none"
              >
                <FileCode className="w-4 h-4" />
                <span>{isExporting === 'csv' ? 'Generating...' : 'Master CSV'}</span>
              </button>

              {/* TXT Master */}
              <button
                type="button"
                onClick={() => handleExport('txt')}
                disabled={isExporting !== null || activeJob.total_completed === 0}
                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-slate-950 font-bold text-xs shadow-lg shadow-sky-500/20 disabled:opacity-50 transition active:scale-[0.98] flex-1 sm:flex-none"
              >
                <FileText className="w-4 h-4" />
                <span>{isExporting === 'txt' ? 'Generating...' : 'Master TXT'}</span>
              </button>
            </div>
          </div>

          {/* Live Feed Table of Discovered & Processed Products */}
          <div className="space-y-3 pt-2">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <span>Discovered Products Live Feed</span>
                <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                  {products.length} records
                </span>
              </h4>

              {/* Filter Tabs */}
              <div className="flex items-center gap-1 text-xs bg-slate-900/80 p-0.5 rounded-lg border border-slate-800">
                {(['all', 'completed', 'pending', 'failed'] as const).map((status) => (
                  <button
                    key={status}
                    type="button"
                    onClick={() => setFilterStatus(status)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-medium capitalize transition ${
                      filterStatus === status
                        ? 'bg-slate-800 text-slate-100 font-semibold'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>

            {/* Table Container */}
            <div className="w-full overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 max-h-96 overflow-y-auto no-scrollbar">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-900/90 text-slate-400 sticky top-0 z-10 border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3 font-semibold">Status</th>
                    <th className="py-2.5 px-3 font-semibold">Product Name</th>
                    <th className="py-2.5 px-3 font-semibold">Price</th>
                    <th className="py-2.5 px-3 font-semibold">Strength</th>
                    <th className="py-2.5 px-3 font-semibold">Manufacturer</th>
                    <th className="py-2.5 px-3 font-semibold">Link</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-850">
                  {filteredProducts.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center py-8 text-slate-500">
                        {products.length === 0
                          ? 'Starting discovery on listing page...'
                          : `No products matching filter '${filterStatus}'.`}
                      </td>
                    </tr>
                  ) : (
                    filteredProducts.map((p, idx) => (
                      <tr key={p.product_url + idx} className="hover:bg-slate-900/40 transition">
                        <td className="py-2.5 px-3 shrink-0">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                              p.status === 'completed'
                                ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-500/30'
                                : p.status === 'failed'
                                ? 'bg-rose-950/80 text-rose-400 border border-rose-500/30'
                                : p.status === 'skipped'
                                ? 'bg-slate-800 text-slate-400 border border-slate-700'
                                : 'bg-amber-950/80 text-amber-400 border border-amber-500/30 animate-pulse'
                            }`}
                          >
                            {p.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-medium text-slate-200 max-w-xs truncate">
                          {p.product_name || (
                            <span className="text-slate-500 italic">Discovered (Pending Extraction)</span>
                          )}
                          {p.last_error && (
                            <div className="text-[10px] text-rose-400 truncate max-w-xs">
                              Error: {p.last_error}
                            </div>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-slate-300 font-mono">{p.price || '—'}</td>
                        <td className="py-2.5 px-3 text-slate-300">{p.strength || '—'}</td>
                        <td className="py-2.5 px-3 text-slate-400 max-w-[150px] truncate">
                          {p.manufacturer || '—'}
                        </td>
                        <td className="py-2.5 px-3">
                          <a
                            href={p.product_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-emerald-400 transition"
                            title={p.product_url}
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
