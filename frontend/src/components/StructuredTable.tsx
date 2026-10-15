import React, { useState, useMemo } from 'react';
import { Search, Filter, Hash, Tag, FileText } from 'lucide-react';
import { ExtractedItem } from '../types';

interface StructuredTableProps {
  items: ExtractedItem[];
}

export const StructuredTable: React.FC<StructuredTableProps> = ({ items }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Filter items based on search and type
  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchesSearch =
        searchTerm === '' ||
        item.text_content.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (item.heading && item.heading.toLowerCase().includes(searchTerm.toLowerCase()));

      let matchesType = true;
      if (selectedType === 'headings') {
        matchesType = item.content_type.startsWith('heading') || item.content_type === 'page_title';
      } else if (selectedType === 'paragraphs') {
        matchesType = item.content_type === 'paragraph' || item.content_type === 'text_block';
      } else if (selectedType === 'lists') {
        matchesType = item.content_type === 'list_item';
      } else if (selectedType === 'tables') {
        matchesType = item.content_type.startsWith('table');
      } else if (selectedType === 'links') {
        matchesType = item.content_type === 'link';
      }

      return matchesSearch && matchesType;
    });
  }, [items, searchTerm, selectedType]);

  const totalPages = Math.ceil(filteredItems.length / pageSize) || 1;
  const paginatedItems = filteredItems.slice((page - 1) * pageSize, page * pageSize);

  const getTypeBadgeClass = (type: string) => {
    if (type.startsWith('heading') || type === 'page_title') {
      return 'bg-purple-500/10 text-purple-300 border-purple-500/20';
    }
    if (type === 'list_item') {
      return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20';
    }
    if (type.startsWith('table')) {
      return 'bg-amber-500/10 text-amber-300 border-amber-500/20';
    }
    if (type === 'link') {
      return 'bg-sky-500/10 text-sky-300 border-sky-500/20';
    }
    return 'bg-slate-800 text-slate-300 border-slate-700';
  };

  return (
    <div className="space-y-4">
      {/* Search and Filters Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(1);
            }}
            placeholder="Search within extracted records..."
            className="w-full pl-9 pr-4 py-2 bg-slate-900/80 border border-slate-800 rounded-xl text-xs md:text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-500/50"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 text-xs">
          {[
            { id: 'all', label: 'All Records' },
            { id: 'headings', label: 'Headings' },
            { id: 'paragraphs', label: 'Paragraphs' },
            { id: 'lists', label: 'Lists' },
            { id: 'tables', label: 'Tables' },
            { id: 'links', label: 'Links' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setSelectedType(tab.id);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg whitespace-nowrap transition-all ${
                selectedType === tab.id
                  ? 'bg-slate-800 text-brand-400 border border-brand-500/30 font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Structured Table */}
      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs md:text-sm">
            <thead className="bg-slate-900/90 text-slate-400 uppercase text-[11px] font-semibold border-b border-slate-800">
              <tr>
                <th className="px-4 py-3 w-16">Seq #</th>
                <th className="px-4 py-3 w-32">Content Type</th>
                <th className="px-4 py-3 w-48">Heading Context</th>
                <th className="px-4 py-3">Extracted Content</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {paginatedItems.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-slate-500">
                    No matching records found.
                  </td>
                </tr>
              ) : (
                paginatedItems.map((item) => (
                  <tr
                    key={item.sequence_number}
                    className="hover:bg-slate-900/40 transition-colors"
                  >
                    <td className="px-4 py-3.5 font-mono text-slate-500 text-xs">
                      #{item.sequence_number}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border ${getTypeBadgeClass(
                          item.content_type
                        )}`}
                      >
                        {item.content_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs font-medium max-w-xs truncate">
                      {item.heading || <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-4 py-3.5 text-slate-200 leading-relaxed font-normal">
                      {item.text_content}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div className="px-4 py-3 bg-slate-900/60 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <div>
            Showing <span className="text-slate-200 font-medium">{paginatedItems.length}</span> of{' '}
            <span className="text-slate-200 font-medium">{filteredItems.length}</span> records
          </div>

          {totalPages > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(p - 1, 1))}
                disabled={page === 1}
                className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:pointer-events-none text-slate-300"
              >
                Previous
              </button>
              <span>
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                disabled={page === totalPages}
                className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:pointer-events-none text-slate-300"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
