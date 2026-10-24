import React, { useState, useEffect, useRef } from 'react';
import {
  Image as ImageIcon,
  Play,
  Square,
  FolderOpen,
  Copy,
  Check,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  Sliders,
  ChevronDown,
  ChevronUp,
  HardDrive,
  ExternalLink,
  FileCheck,
} from 'lucide-react';
import {
  ImageJobResponse,
  ImageScrapeRequest,
  ImageStorageStatus,
} from '../types';
import {
  startImageScrapeJob,
  getImageJobStatus,
  stopImageJob,
  openOutputFolder,
  getImageStorageStatus,
} from '../api';

interface ImageDownloaderViewProps {
  onNotify: (message: string, type: 'success' | 'error') => void;
}

const SAMPLE_LISTING_URLS = [
  {
    label: 'Tata 1mg (Alphabet P)',
    url: 'https://www.1mg.com/drugs-all-medicines?label=p',
  },
  {
    label: 'Tata 1mg (Alphabet A)',
    url: 'https://www.1mg.com/drugs-all-medicines?label=a',
  },
  {
    label: 'Tata 1mg (Alphabet C)',
    url: 'https://www.1mg.com/drugs-all-medicines?label=c',
  },
];

export const ImageDownloaderView: React.FC<ImageDownloaderViewProps> = ({ onNotify }) => {
  const [url, setUrl] = useState('');
  const [maxPages, setMaxPages] = useState<number | ''>('');
  const [maxImages, setMaxImages] = useState<number | ''>('');
  const [delaySeconds, setDelaySeconds] = useState(0.5);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Active Job State
  const [activeJob, setActiveJob] = useState<ImageJobResponse | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [storageStatus, setStorageStatus] = useState<ImageStorageStatus | null>(null);
  const [copiedPath, setCopiedPath] = useState(false);
  const [isOpeningFolder, setIsOpeningFolder] = useState(false);

  const pollIntervalRef = useRef<number | null>(null);

  // Load storage status on mount
  useEffect(() => {
    refreshStorageStatus();
  }, []);

  const refreshStorageStatus = async () => {
    try {
      const status = await getImageStorageStatus();
      setStorageStatus(status);
    } catch {
      // Ignore initial silent failures
    }
  };

  // Poll active job status
  useEffect(() => {
    if (!activeJob?.job_id) return;

    const isFinished = ['completed', 'failed', 'stopped'].includes(activeJob.job_status);
    if (isFinished) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      refreshStorageStatus();
      return;
    }

    pollIntervalRef.current = window.setInterval(async () => {
      try {
        const updated = await getImageJobStatus(activeJob.job_id);
        setActiveJob(updated);
        if (['completed', 'failed', 'stopped'].includes(updated.job_status)) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          refreshStorageStatus();
          if (updated.job_status === 'completed') {
            onNotify(
              `Mode C complete: Successfully downloaded ${updated.images_downloaded} images!`,
              'success'
            );
          }
        }
      } catch (err: any) {
        console.error('Failed to poll image job status:', err);
      }
    }, 1500);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [activeJob?.job_id, activeJob?.job_status]);

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) {
      onNotify('Please enter a valid listing URL.', 'error');
      return;
    }

    setIsStarting(true);
    try {
      const req: ImageScrapeRequest = {
        listing_url: url.trim(),
        max_pages: maxPages === '' ? null : Number(maxPages),
        max_images: maxImages === '' ? null : Number(maxImages),
        delay_seconds: delaySeconds,
      };

      const job = await startImageScrapeJob(req);
      setActiveJob(job);
      onNotify(`Mode C job started for: ${url.trim()}`, 'success');
    } catch (err: any) {
      onNotify(err.message || 'Failed to start image download job.', 'error');
    } finally {
      setIsStarting(false);
    }
  };

  const handleStop = async () => {
    if (!activeJob?.job_id) return;
    try {
      const updated = await stopImageJob(activeJob.job_id);
      setActiveJob(updated);
      onNotify('Image download job stopped.', 'success');
    } catch (err: any) {
      onNotify(err.message || 'Failed to stop job.', 'error');
    }
  };

  const handleOpenFolder = async () => {
    setIsOpeningFolder(true);
    try {
      const res = await openOutputFolder(activeJob?.output_dir || storageStatus?.folder_path);
      if (res.success) {
        onNotify('Opened medicine images folder in File Explorer.', 'success');
      } else {
        onNotify(res.error_message || 'Could not open folder automatically.', 'error');
      }
    } catch (err: any) {
      onNotify(err.message || 'Failed to open folder.', 'error');
    } finally {
      setIsOpeningFolder(false);
    }
  };

  const handleCopyPath = () => {
    const path = activeJob?.output_dir || storageStatus?.folder_path;
    if (path) {
      navigator.clipboard.writeText(path);
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 2000);
      onNotify('Copied folder path to clipboard.', 'success');
    }
  };

  const isJobRunning = activeJob?.job_status === 'running' || activeJob?.job_status === 'pending';

  // Calculate progress percent
  const totalProcessed = (activeJob?.images_downloaded || 0) + (activeJob?.images_skipped || 0) + (activeJob?.images_failed || 0);
  const totalDiscovered = activeJob?.total_discovered || 0;
  const progressPercent = totalDiscovered > 0 ? Math.min(100, Math.round((totalProcessed / totalDiscovered) * 100)) : 0;

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header Banner */}
      <div className="text-center space-y-3 pt-2 pb-2">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs font-semibold">
          <ImageIcon className="w-3.5 h-3.5" />
          <span>Mode C &bull; Local Image Archival Engine</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight bg-gradient-to-r from-sky-200 via-sky-100 to-indigo-300 bg-clip-text text-transparent">
          Medicine Image Downloader
        </h1>
        <p className="text-sm sm:text-base text-slate-400 max-w-2xl mx-auto leading-relaxed">
          Traverse medicine catalog pages, extract high-resolution product images, and save them directly to your disk formatted as{' '}
          <span className="font-mono text-sky-300 bg-sky-950/40 px-1.5 py-0.5 rounded border border-sky-800/40">Dolo_650.webp</span> or{' '}
          <span className="font-mono text-indigo-300 bg-indigo-950/40 px-1.5 py-0.5 rounded border border-indigo-800/40">Zincovit_Tablet.jpg</span>.
        </p>
      </div>

      {/* Directory Status Card */}
      <div className="max-w-4xl mx-auto glass-panel p-4 rounded-2xl border border-sky-500/20 bg-slate-900/60 shadow-xl flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <div className="w-10 h-10 rounded-xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center shrink-0 text-sky-400">
            <HardDrive className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <span>Local Storage Directory</span>
              {storageStatus && (
                <span className="text-[11px] font-mono font-medium px-2 py-0.5 rounded-full bg-sky-950/80 text-sky-300 border border-sky-800/50">
                  {storageStatus.total_images} images on disk
                </span>
              )}
            </div>
            <div className="text-xs font-mono text-slate-200 truncate max-w-md pt-0.5" title={activeJob?.output_dir || storageStatus?.folder_path || 'output/medicine_images'}>
              {activeJob?.output_dir || storageStatus?.folder_path || 'output/medicine_images/'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto shrink-0 justify-end">
          <button
            type="button"
            onClick={handleCopyPath}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 transition"
            title="Copy path to clipboard"
          >
            {copiedPath ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copiedPath ? 'Copied' : 'Copy Path'}</span>
          </button>

          <button
            type="button"
            onClick={handleOpenFolder}
            disabled={isOpeningFolder}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-sky-950 bg-gradient-to-r from-sky-400 to-indigo-400 hover:from-sky-300 hover:to-indigo-300 shadow-md shadow-sky-500/20 transition disabled:opacity-50"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            <span>Open Folder</span>
          </button>
        </div>
      </div>

      {/* Input Form Panel */}
      <div className="max-w-4xl mx-auto glass-panel p-6 sm:p-7 rounded-3xl border border-slate-800/90 bg-slate-900/80 shadow-2xl space-y-6">
        <form onSubmit={handleStart} className="space-y-5">
          {/* Main URL Input */}
          <div className="space-y-2">
            <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider">
              Medicine Category or Listing URL
            </label>
            <div className="relative">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="e.g. https://www.1mg.com/drugs-all-medicines?label=p"
                required
                disabled={isJobRunning || isStarting}
                className="w-full pl-4 pr-12 py-3.5 bg-slate-950/80 border border-slate-700/80 rounded-2xl text-slate-100 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition disabled:opacity-60"
              />
              <div className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500">
                <ImageIcon className="w-4 h-4 text-sky-400/60" />
              </div>
            </div>

            {/* Presets */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[11px] text-slate-500 font-medium">Quick Presets:</span>
              {SAMPLE_LISTING_URLS.map((sample) => (
                <button
                  key={sample.url}
                  type="button"
                  onClick={() => setUrl(sample.url)}
                  disabled={isJobRunning || isStarting}
                  className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-800/70 hover:bg-slate-700/70 border border-slate-700/60 text-slate-300 hover:text-white transition disabled:opacity-50"
                >
                  {sample.label}
                </button>
              ))}
            </div>
          </div>

          {/* Advanced Traversal Settings Toggle */}
          <div className="pt-1 border-t border-slate-800/60">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition py-1 font-medium"
            >
              <Sliders className="w-3.5 h-3.5 text-sky-400" />
              <span>Optional Download & Rate Limits</span>
              {showAdvanced ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>

            {showAdvanced && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-3 mt-2 p-4 rounded-2xl bg-slate-950/50 border border-slate-800">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Max Listing Pages
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={10000}
                    value={maxPages}
                    onChange={(e) => setMaxPages(e.target.value === '' ? '' : Number(e.target.value))}
                    placeholder="Unlimited"
                    disabled={isJobRunning || isStarting}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                  <span className="text-[10px] text-slate-500">Traverse all pages if blank</span>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Max Images Limit
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={50000}
                    value={maxImages}
                    onChange={(e) => setMaxImages(e.target.value === '' ? '' : Number(e.target.value))}
                    placeholder="Unlimited"
                    disabled={isJobRunning || isStarting}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                  <span className="text-[10px] text-slate-500">Download all images if blank</span>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Delay Between Requests
                  </label>
                  <input
                    type="number"
                    step={0.1}
                    min={0.0}
                    max={10.0}
                    value={delaySeconds}
                    onChange={(e) => setDelaySeconds(Number(e.target.value))}
                    disabled={isJobRunning || isStarting}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                  <span className="text-[10px] text-slate-500">Default 0.5s polite delay</span>
                </div>
              </div>
            )}
          </div>

          {/* Action Button */}
          <div className="pt-2">
            {!isJobRunning ? (
              <button
                type="submit"
                disabled={isStarting}
                className="w-full flex items-center justify-center gap-2 py-3.5 px-6 rounded-2xl text-sm font-bold text-slate-950 bg-gradient-to-r from-sky-400 via-sky-300 to-indigo-400 hover:from-sky-300 hover:to-indigo-300 shadow-lg shadow-sky-500/20 transition-all transform active:scale-[0.99] disabled:opacity-50"
              >
                {isStarting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
                    <span>Initiating Image Traversal...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-slate-950" />
                    <span>Start Downloading Images</span>
                  </>
                )}
              </button>
            ) : (
              <button
                type="button"
                onClick={handleStop}
                className="w-full flex items-center justify-center gap-2 py-3.5 px-6 rounded-2xl text-sm font-bold text-white bg-rose-600 hover:bg-rose-500 shadow-lg shadow-rose-600/20 transition transform active:scale-[0.99]"
              >
                <Square className="w-4 h-4 fill-white" />
                <span>Stop Image Download</span>
              </button>
            )}
          </div>
        </form>
      </div>

      {/* Live Job Monitor Panel */}
      {activeJob && (
        <div className="max-w-4xl mx-auto glass-panel p-6 sm:p-7 rounded-3xl border border-slate-800/90 bg-slate-900/80 shadow-2xl space-y-6">
          {/* Top Job Status Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Job ID:</span>
                <span className="font-mono text-xs text-sky-400 font-bold">{activeJob.job_id}</span>
                <span
                  className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
                    activeJob.job_status === 'running'
                      ? 'bg-sky-950 text-sky-300 border-sky-600 animate-pulse'
                      : activeJob.job_status === 'completed'
                      ? 'bg-emerald-950 text-emerald-300 border-emerald-600'
                      : activeJob.job_status === 'stopped'
                      ? 'bg-amber-950 text-amber-300 border-amber-600'
                      : 'bg-rose-950 text-rose-300 border-rose-600'
                  }`}
                >
                  {activeJob.job_status}
                </span>
              </div>
              <div className="text-xs text-slate-400 truncate max-w-xl">
                Source: <span className="text-slate-200 font-mono">{activeJob.listing_url}</span>
              </div>
            </div>

            {/* Folder button in status bar */}
            <button
              type="button"
              onClick={handleOpenFolder}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-sky-300 bg-sky-950/60 hover:bg-sky-900/60 border border-sky-800/60 transition self-start sm:self-auto"
            >
              <FolderOpen className="w-3.5 h-3.5" />
              <span>Open Output Folder</span>
            </button>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 rounded-2xl bg-emerald-950/20 border border-emerald-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider">
                Downloaded
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-emerald-300 font-mono">
                {activeJob.images_downloaded.toLocaleString()}
              </div>
              <div className="text-[10px] text-emerald-400/70">Saved to disk</div>
            </div>

            <div className="p-4 rounded-2xl bg-sky-950/20 border border-sky-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-sky-400 uppercase tracking-wider">
                Remaining
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-sky-300 font-mono">
                {activeJob.images_remaining.toLocaleString()}
              </div>
              <div className="text-[10px] text-sky-400/70">Queue in progress</div>
            </div>

            <div className="p-4 rounded-2xl bg-amber-950/20 border border-amber-500/20 space-y-1">
              <div className="text-[11px] font-semibold text-amber-400 uppercase tracking-wider">
                Already Exists
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-amber-300 font-mono">
                {activeJob.images_skipped.toLocaleString()}
              </div>
              <div className="text-[10px] text-amber-400/70">Duplicate skipped</div>
            </div>

            <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800 space-y-1">
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Pages & Discovered
              </div>
              <div className="text-2xl sm:text-3xl font-extrabold text-slate-200 font-mono">
                {activeJob.pages_visited} <span className="text-xs text-slate-500 font-normal">/ {activeJob.total_discovered}</span>
              </div>
              <div className="text-[10px] text-slate-500">Pages visited & products</div>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs text-slate-400">
              <span className="flex items-center gap-1.5">
                {isJobRunning && <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping inline-block" />}
                <span>
                  {activeJob.current_medicine_name
                    ? `Processing: ${activeJob.current_medicine_name}`
                    : activeJob.job_status === 'completed'
                    ? 'All images downloaded successfully'
                    : 'Traversing catalog...'}
                </span>
              </span>
              <span className="font-mono font-semibold text-slate-300">{progressPercent}%</span>
            </div>
            <div className="w-full h-2.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
              <div
                className="h-full bg-gradient-to-r from-sky-500 via-indigo-500 to-emerald-400 transition-all duration-300 ease-out"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Activity Feed: Recent Saved Images */}
          {activeJob.recent_downloads && activeJob.recent_downloads.length > 0 && (
            <div className="space-y-2 pt-2">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                <span>Recent Download Feed</span>
                <span className="text-[10px] font-normal text-slate-500">Live stream</span>
              </div>
              <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1 font-mono text-xs">
                {activeJob.recent_downloads.slice().reverse().map((item, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/60 border border-slate-800/80 text-slate-300 hover:border-slate-700 transition"
                  >
                    <div className="flex items-center gap-2 truncate pr-3">
                      {item.status === 'downloaded' ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                      ) : item.status === 'skipped_exists' ? (
                        <FileCheck className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                      ) : (
                        <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                      )}
                      <span className="text-slate-100 font-semibold truncate">{item.filename}</span>
                      <span className="text-[10px] text-slate-500 truncate hidden sm:inline">
                        ({item.medicine_name})
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {item.size_bytes && (
                        <span className="text-[10px] text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800">
                          {(item.size_bytes / 1024).toFixed(1)} KB
                        </span>
                      )}
                      <span
                        className={`text-[9px] uppercase px-1.5 py-0.5 rounded font-bold ${
                          item.status === 'downloaded'
                            ? 'bg-emerald-950 text-emerald-300'
                            : item.status === 'skipped_exists'
                            ? 'bg-amber-950 text-amber-300'
                            : 'bg-rose-950 text-rose-300'
                        }`}
                      >
                        {item.status === 'skipped_exists' ? 'exists' : item.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Completion Celebration Message */}
          {activeJob.job_status === 'completed' && (
            <div className="p-4 rounded-2xl bg-emerald-950/40 border border-emerald-500/30 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
                <div>
                  <div className="text-sm font-bold text-emerald-200">Image Crawl Completed</div>
                  <div className="text-xs text-emerald-300/80">
                    All available images saved into <span className="font-mono">{activeJob.output_dir}</span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={handleOpenFolder}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-emerald-950 bg-emerald-400 hover:bg-emerald-300 shadow-md shadow-emerald-500/20 transition shrink-0"
              >
                <FolderOpen className="w-4 h-4" />
                <span>Open Folder</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
