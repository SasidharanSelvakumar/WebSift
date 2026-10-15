import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { UrlInputBar } from './components/UrlInputBar';
import { LoadingState } from './components/LoadingState';
import { StatsBanner } from './components/StatsBanner';
import { DownloadBar } from './components/DownloadBar';
import { StructuredTable } from './components/StructuredTable';
import { ReaderView } from './components/ReaderView';
import { RawExportView } from './components/RawExportView';
import { MedicineTable } from './components/MedicineTable';
import { SpreadsheetPushModal } from './components/SpreadsheetPushModal';
import { checkBackendHealth, extractWebpage } from './api';
import { ExtractResponse, HealthStatus } from './types';
import { AlertCircle, Table, BookOpen, Code, CheckCircle, X, Pill } from 'lucide-react';

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [extractionResult, setExtractionResult] = useState<ExtractResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'medicine' | 'table' | 'reader' | 'raw'>('medicine');
  const [showPushModal, setShowPushModal] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  // Check backend health on initial load
  useEffect(() => {
    checkBackendHealth()
      .then(setHealth)
      .catch((err) => {
        console.warn('Backend health check note:', err);
      });
  }, []);

  const handleNotify = (message: string, type: 'success' | 'error') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification((prev) => (prev?.message === message ? null : prev));
    }, 4500);
  };

  const handleExtract = async (url: string, mode: 'main' | 'full', forceBrowser: boolean) => {
    setIsLoading(true);
    setError(null);
    setExtractionResult(null);

    try {
      const data = await extractWebpage(url, mode, forceBrowser);
      setExtractionResult(data);
      if (data.medicine_batch && data.medicine_batch.records && data.medicine_batch.records.length > 0) {
        setActiveTab('medicine');
        handleNotify(
          `Extracted ${data.medicine_batch.records.length} medicine record(s) with ${data.medicine_batch.all_discovered_fields.length} dynamic columns!`,
          'success'
        );
      } else {
        setActiveTab('table');
        handleNotify(
          `Extracted ${data.stats.block_count} blocks (${data.stats.word_count.toLocaleString()} words)`,
          'success'
        );
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred during extraction.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setExtractionResult(null);
    setError(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#070c18] text-slate-100 font-sans">
      <Header health={health} />

      {/* Toast Notification */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 animate-bounce duration-300">
          <div
            className={`flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium ${
              notification.type === 'success'
                ? 'bg-emerald-950/90 text-emerald-200 border-emerald-500/40'
                : 'bg-rose-950/90 text-rose-200 border-rose-500/40'
            }`}
          >
            {notification.type === 'success' ? (
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{notification.message}</span>
            <button
              onClick={() => setNotification(null)}
              className="ml-2 hover:opacity-75 p-0.5 rounded"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Main Body */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Hero & Input Section */}
        {!extractionResult && (
          <div className="text-center space-y-3 pt-6 pb-2">
            <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
              Precision Web Scraping & Content Export
            </h1>
            <p className="text-sm sm:text-base text-slate-400 max-w-2xl mx-auto leading-relaxed">
              Extract readable textual content and dynamic medicine details with automatic attribute discovery. Download as <span className="text-emerald-400 font-semibold">Excel (.xlsx)</span>, <span className="text-teal-400 font-semibold">CSV</span>, or <span className="text-sky-400 font-semibold">TXT</span>, or push directly to spreadsheets.
            </p>
          </div>
        )}

        <UrlInputBar onSubmit={handleExtract} isLoading={isLoading} />

        {/* Loading Progress */}
        {isLoading && <LoadingState />}

        {/* Error Alert */}
        {error && !isLoading && (
          <div className="w-full max-w-3xl mx-auto glass-panel p-5 rounded-2xl border border-rose-500/30 bg-rose-500/5 shadow-2xl flex items-start gap-3.5 text-rose-200">
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h3 className="font-bold text-sm text-rose-300">Extraction Error</h3>
              <p className="text-xs sm:text-sm text-rose-200/90 leading-relaxed">{error}</p>
              <div className="text-[11px] text-rose-300/70 pt-1">
                Tip: Verify the URL is publicly reachable, uses HTTP/HTTPS, and is not a private or restricted network address.
              </div>
            </div>
          </div>
        )}

        {/* Successful Result Views */}
        {extractionResult && !isLoading && (
          <div className="space-y-6 animate-fadeIn">
            {/* Top Stats Banner */}
            <StatsBanner data={extractionResult} />

            {/* Prominent Download and Action Bar */}
            <DownloadBar
              items={extractionResult.items}
              medicineBatch={extractionResult.medicine_batch}
              sourceUrl={extractionResult.source_url}
              pageTitle={extractionResult.page_title}
              mode={extractionResult.mode}
              fullTextPreview={extractionResult.full_text_preview}
              onReset={handleReset}
              onNotify={handleNotify}
              onOpenPushModal={() => setShowPushModal(true)}
            />

            {/* View Tabs */}
            <div className="flex items-center gap-2 border-b border-slate-800 pb-2 overflow-x-auto no-scrollbar">
              {extractionResult.medicine_batch && extractionResult.medicine_batch.records.length > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveTab('medicine')}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition shrink-0 ${
                    activeTab === 'medicine'
                      ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-500/40 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                  }`}
                >
                  <Pill className="w-4 h-4 text-emerald-400" />
                  <span>Medicine Records ({extractionResult.medicine_batch.records.length})</span>
                  <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-[10px] font-mono">
                    {extractionResult.medicine_batch.all_discovered_fields.length} cols
                  </span>
                </button>
              )}

              <button
                type="button"
                onClick={() => setActiveTab('table')}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition shrink-0 ${
                  activeTab === 'table'
                    ? 'bg-slate-800 text-brand-400 border border-brand-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Table className="w-4 h-4" />
                <span>Structured Blocks ({extractionResult.items.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('reader')}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition shrink-0 ${
                  activeTab === 'reader'
                    ? 'bg-slate-800 text-brand-400 border border-brand-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <BookOpen className="w-4 h-4" />
                <span>Article Reader View</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('raw')}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-semibold transition shrink-0 ${
                  activeTab === 'raw'
                    ? 'bg-slate-800 text-brand-400 border border-brand-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                }`}
              >
                <Code className="w-4 h-4" />
                <span>Raw File Preview</span>
              </button>
            </div>

            {/* Active Tab Panel */}
            <div className="mt-4">
              {activeTab === 'medicine' && extractionResult.medicine_batch && (
                <MedicineTable batch={extractionResult.medicine_batch} />
              )}
              {activeTab === 'table' && <StructuredTable items={extractionResult.items} />}
              {activeTab === 'reader' && (
                <ReaderView
                  items={extractionResult.items}
                  pageTitle={extractionResult.page_title}
                />
              )}
              {activeTab === 'raw' && (
                <RawExportView
                  items={extractionResult.items}
                  sourceUrl={extractionResult.source_url}
                  pageTitle={extractionResult.page_title}
                  fullTextPreview={extractionResult.full_text_preview}
                  onNotify={handleNotify}
                />
              )}
            </div>
          </div>
        )}

        {/* Spreadsheet Push Modal */}
        {showPushModal && extractionResult?.medicine_batch && (
          <SpreadsheetPushModal
            batch={extractionResult.medicine_batch}
            onClose={() => setShowPushModal(false)}
            onNotify={handleNotify}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>WebSift — Web Scraping & Content Export Agent</span>
          <span>RFC-4180 CSV with UTF-8 BOM • Reading-Order TXT • SSRF Guarded</span>
        </div>
      </footer>
    </div>
  );
};
