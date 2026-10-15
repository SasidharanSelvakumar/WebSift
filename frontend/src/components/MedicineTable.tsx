import React, { useState, useMemo } from 'react';
import { MedicineBatch } from '../types';
import { Search, Sparkles, AlertCircle, Eye, X, Filter } from 'lucide-react';

interface MedicineTableProps {
  batch: MedicineBatch;
}

export const MedicineTable: React.FC<MedicineTableProps> = ({ batch }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCell, setSelectedCell] = useState<{ header: string; value: string; medicine: string } | null>(null);

  const columns = batch.all_discovered_fields;
  const records = batch.records;

  // Filter records based on search term across all attributes
  const filteredRecords = useMemo(() => {
    if (!searchTerm.trim()) return records;
    const term = searchTerm.toLowerCase();
    return records.filter((rec) => {
      if (rec.medicine_name.toLowerCase().includes(term)) return true;
      return Object.values(rec.attributes).some((v) =>
        String(v).toLowerCase().includes(term)
      );
    });
  }, [records, searchTerm]);

  return (
    <div className="space-y-4">
      {/* Header Info & Attribute Pills */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-400 font-medium">Discovered Attributes:</span>
          <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-semibold">
            {batch.unique_attributes_count} Total Columns
          </span>
          {batch.new_fields.length > 0 && (
            <span className="px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20 font-semibold flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              {batch.new_fields.length} Dynamic Custom Fields
            </span>
          )}
        </div>

        {/* Search Input */}
        <div className="relative w-full md:w-72">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search attributes & medicines..."
            className="w-full pl-9 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs md:text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50"
          />
        </div>
      </div>

      {/* Discovered Columns Badge Strip */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-2 text-xs no-scrollbar">
        <span className="text-slate-500 shrink-0 text-[11px] uppercase tracking-wider font-semibold mr-1">
          Active Columns:
        </span>
        {columns.map((col) => {
          const isNew = batch.new_fields.includes(col);
          return (
            <span
              key={col}
              className={`px-2.5 py-1 rounded-lg shrink-0 text-xs font-medium border transition ${
                isNew
                  ? 'bg-purple-950/60 text-purple-300 border-purple-500/30'
                  : 'bg-slate-900 text-slate-300 border-slate-800'
              }`}
            >
              {col}
            </span>
          );
        })}
      </div>

      {/* Dynamic Grid Table Container */}
      <div className="glass-panel rounded-2xl border border-slate-800 shadow-2xl overflow-hidden">
        <div className="overflow-x-auto max-h-[600px] relative">
          <table className="w-full text-left text-xs md:text-sm border-collapse min-w-max">
            <thead className="bg-slate-900 sticky top-0 z-20 text-slate-300 uppercase text-[11px] font-bold border-b border-slate-800 shadow-sm">
              <tr>
                <th className="px-4 py-3.5 bg-slate-900 sticky left-0 z-30 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.5)]">
                  #
                </th>
                {columns.map((col) => (
                  <th
                    key={col}
                    className={`px-4 py-3.5 whitespace-nowrap ${
                      col === 'Medicine Name' ? 'bg-slate-900 sticky left-8 z-30 font-extrabold text-white' : ''
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span>{col}</span>
                      {batch.new_fields.includes(col) && (
                        <span className="w-1.5 h-1.5 rounded-full bg-purple-400" title="Newly discovered dynamic column"></span>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={columns.length + 1} className="px-4 py-12 text-center text-slate-500">
                    No medicine records match your search.
                  </td>
                </tr>
              ) : (
                filteredRecords.map((record, rIdx) => (
                  <tr
                    key={record.record_id || rIdx}
                    className="hover:bg-slate-900/50 transition-colors group"
                  >
                    <td className="px-4 py-3 font-mono text-slate-500 text-xs bg-slate-950/80 sticky left-0 z-10 group-hover:bg-slate-900/90 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.5)]">
                      {rIdx + 1}
                    </td>

                    {columns.map((col) => {
                      let val = '';
                      if (col === 'Medicine Name') val = record.medicine_name;
                      else if (col === 'Source URL') val = record.source_url;
                      else if (col === 'Extracted At') val = record.extracted_at;
                      else if (col in record.attributes) val = record.attributes[col];

                      const isLong = typeof val === 'string' && val.length > 70;
                      const isStickyName = col === 'Medicine Name';

                      return (
                        <td
                          key={col}
                          className={`px-4 py-3 text-xs md:text-sm leading-relaxed max-w-sm ${
                            isStickyName
                              ? 'bg-slate-950/80 sticky left-8 z-10 font-bold text-emerald-400 group-hover:bg-slate-900/90'
                              : 'text-slate-200'
                          }`}
                        >
                          {val ? (
                            <div className="flex items-start justify-between gap-1.5">
                              <span className="truncate block" title={typeof val === 'string' ? val : ''}>
                                {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                              </span>
                              {isLong && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedCell({
                                      header: col,
                                      value: String(val),
                                      medicine: record.medicine_name,
                                    })
                                  }
                                  className="text-slate-500 hover:text-emerald-400 p-0.5 rounded shrink-0 transition"
                                  title="View complete text"
                                >
                                  <Eye className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-600 font-mono">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer info */}
        <div className="px-4 py-2.5 bg-slate-900/70 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>
            Displaying <strong className="text-slate-200">{filteredRecords.length}</strong> medicine records across{' '}
            <strong className="text-emerald-400">{columns.length}</strong> dynamic columns.
          </span>
          <span className="hidden sm:inline text-slate-500">
            Unshared attributes remain blank (never fabricated).
          </span>
        </div>
      </div>

      {/* Inspect Cell Modal */}
      {selectedCell && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
          <div className="glass-panel w-full max-w-2xl rounded-2xl border border-slate-700 p-6 shadow-2xl space-y-4">
            <div className="flex items-start justify-between pb-3 border-b border-slate-800">
              <div>
                <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">
                  {selectedCell.header}
                </span>
                <h3 className="text-lg font-bold text-white">{selectedCell.medicine}</h3>
              </div>
              <button
                onClick={() => setSelectedCell(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 text-sm text-slate-200 leading-relaxed max-h-96 overflow-y-auto whitespace-pre-wrap font-sans">
              {selectedCell.value}
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setSelectedCell(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
