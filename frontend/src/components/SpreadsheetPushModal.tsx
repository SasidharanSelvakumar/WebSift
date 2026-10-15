import React, { useState } from 'react';
import { MedicineBatch, SpreadsheetPushResponse } from '../types';
import { pushToSpreadsheet } from '../api';
import {
  FileSpreadsheet,
  Cloud,
  Layers,
  CheckCircle2,
  AlertTriangle,
  X,
  Loader2,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react';

interface SpreadsheetPushModalProps {
  batch: MedicineBatch;
  onClose: () => void;
  onNotify: (msg: string, type: 'success' | 'error') => void;
}

export const SpreadsheetPushModal: React.FC<SpreadsheetPushModalProps> = ({
  batch,
  onClose,
  onNotify,
}) => {
  const [destinationType, setDestinationType] = useState<'local_excel' | 'google_sheets'>('local_excel');
  const [filePath, setFilePath] = useState('medicines_database.xlsx');
  const [spreadsheetId, setSpreadsheetId] = useState('');
  const [worksheetName, setWorksheetName] = useState('Medicine Data');
  const [preventDuplicates, setPreventDuplicates] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<SpreadsheetPushResponse | null>(null);

  const handlePush = async () => {
    setIsSubmitting(true);
    setResult(null);

    try {
      const res = await pushToSpreadsheet(
        batch,
        destinationType,
        destinationType === 'local_excel' ? filePath : undefined,
        destinationType === 'google_sheets' ? spreadsheetId : undefined,
        worksheetName,
        preventDuplicates
      );
      setResult(res);
      if (res.success) {
        onNotify(
          `Successfully appended ${res.inserted_records} record(s) to ${res.destination}`,
          'success'
        );
      } else {
        onNotify(res.error_message || 'Spreadsheet push failed.', 'error');
      }
    } catch (err: any) {
      onNotify(err.message || 'Operation failed.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md animate-fadeIn">
      <div className="glass-panel w-full max-w-2xl rounded-2xl border border-slate-700 shadow-2xl p-6 space-y-5">
        {/* Modal Header */}
        <div className="flex items-start justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 p-0.5 flex items-center justify-center">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <FileSpreadsheet className="w-5 h-5 text-emerald-400" />
              </div>
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">Push to Existing Spreadsheet</h3>
              <p className="text-xs text-slate-400">
                Non-destructively adapt columns and append records without overwriting history.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Success or Result Screen */}
        {result && (
          <div
            className={`p-4 rounded-xl border space-y-3 ${
              result.success
                ? 'bg-emerald-950/60 border-emerald-500/40 text-emerald-200'
                : 'bg-rose-950/60 border-rose-500/40 text-rose-200'
            }`}
          >
            <div className="flex items-center gap-2 font-bold text-sm">
              {result.success ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-rose-400" />
              )}
              <span>{result.success ? 'Spreadsheet Updated Successfully' : 'Spreadsheet Update Issue'}</span>
            </div>

            <p className="text-xs leading-relaxed">
              {result.error_message || `Data appended to "${result.destination}".`}
            </p>

            <div className="grid grid-cols-3 gap-2 pt-1 text-center font-mono text-xs">
              <div className="p-2 rounded bg-slate-900/80 border border-slate-800">
                <div className="text-base font-bold text-emerald-400">{result.inserted_records}</div>
                <div className="text-[10px] text-slate-400">Inserted</div>
              </div>
              <div className="p-2 rounded bg-slate-900/80 border border-slate-800">
                <div className="text-base font-bold text-amber-400">{result.skipped_records}</div>
                <div className="text-[10px] text-slate-400">Skipped (Dups)</div>
              </div>
              <div className="p-2 rounded bg-slate-900/80 border border-slate-800">
                <div className="text-base font-bold text-sky-400">{result.newly_created_columns.length}</div>
                <div className="text-[10px] text-slate-400">New Columns</div>
              </div>
            </div>

            {result.newly_created_columns.length > 0 && (
              <div className="text-xs text-slate-300">
                <span className="font-semibold text-sky-300">Created Columns:</span>{' '}
                {result.newly_created_columns.join(', ')}
              </div>
            )}
          </div>
        )}

        {/* Configuration Options */}
        <div className="space-y-4">
          {/* Destination Type Toggle */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-2">
              Select Spreadsheet Provider:
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setDestinationType('local_excel')}
                className={`flex items-center gap-3 p-3 rounded-xl border text-left transition ${
                  destinationType === 'local_excel'
                    ? 'bg-slate-900 border-emerald-500/50 shadow-md ring-1 ring-emerald-500/20'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <FileSpreadsheet
                  className={`w-5 h-5 ${destinationType === 'local_excel' ? 'text-emerald-400' : 'text-slate-500'}`}
                />
                <div>
                  <div className="text-xs font-bold text-slate-100">Local Excel Workbook</div>
                  <div className="text-[10px] text-slate-500">.xlsx file on local drive</div>
                </div>
              </button>

              <button
                type="button"
                onClick={() => setDestinationType('google_sheets')}
                className={`flex items-center gap-3 p-3 rounded-xl border text-left transition ${
                  destinationType === 'google_sheets'
                    ? 'bg-slate-900 border-emerald-500/50 shadow-md ring-1 ring-emerald-500/20'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <Cloud
                  className={`w-5 h-5 ${destinationType === 'google_sheets' ? 'text-sky-400' : 'text-slate-500'}`}
                />
                <div>
                  <div className="text-xs font-bold text-slate-100">Google Sheets API</div>
                  <div className="text-[10px] text-slate-500">Cloud live sync</div>
                </div>
              </button>
            </div>
          </div>

          {/* Destination Path or ID */}
          {destinationType === 'local_excel' ? (
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">
                Target Excel File Path:
              </label>
              <input
                type="text"
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                placeholder="medicines_database.xlsx"
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/50"
              />
              <span className="text-[10px] text-slate-500 mt-1 block">
                If the file does not exist, it will be initialized automatically. Existing rows will be preserved.
              </span>
            </div>
          ) : (
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">
                Google Sheets Spreadsheet ID:
              </label>
              <input
                type="text"
                value={spreadsheetId}
                onChange={(e) => setSpreadsheetId(e.target.value)}
                placeholder="e.g. 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/50"
              />
              <span className="text-[10px] text-slate-500 mt-1 block">
                Requires GOOGLE_APPLICATION_CREDENTIALS service account on server.
              </span>
            </div>
          )}

          {/* Worksheet Name & Duplicate Control */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-1">
                Worksheet / Tab Name:
              </label>
              <input
                type="text"
                value={worksheetName}
                onChange={(e) => setWorksheetName(e.target.value)}
                className="w-full px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-emerald-500/50"
              />
            </div>

            <div className="flex items-center pt-5">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300 select-none">
                <input
                  type="checkbox"
                  checked={preventDuplicates}
                  onChange={(e) => setPreventDuplicates(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-700 text-emerald-500 accent-emerald-500 bg-slate-900"
                />
                <span>Prevent duplicate records</span>
              </label>
            </div>
          </div>

          {/* Schema Adaptation Summary Banner */}
          <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800/80 text-xs text-slate-300 space-y-1">
            <div className="flex items-center justify-between font-semibold text-slate-200">
              <span className="flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-emerald-400" /> Schema Adaptation Preview
              </span>
              <span className="text-emerald-400 font-mono">{batch.records.length} Records to Append</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              The engine will inspect existing column headers in the spreadsheet, dynamically append any newly discovered columns to the right, and map every record cleanly.
            </p>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-semibold"
          >
            {result?.success ? 'Done' : 'Cancel'}
          </button>

          <button
            type="button"
            onClick={handlePush}
            disabled={isSubmitting}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-slate-950 text-xs font-bold shadow-lg shadow-emerald-500/20 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-slate-950" />
                <span>Writing to Spreadsheet...</span>
              </>
            ) : (
              <>
                <span>Confirm & Push Records</span>
                <ArrowRight className="w-3.5 h-3.5 text-slate-950" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
