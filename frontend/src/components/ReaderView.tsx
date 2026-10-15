import React from 'react';
import { ExtractedItem } from '../types';

interface ReaderViewProps {
  items: ExtractedItem[];
  pageTitle: string;
}

export const ReaderView: React.FC<ReaderViewProps> = ({ items, pageTitle }) => {
  return (
    <div className="glass-panel p-6 sm:p-10 rounded-2xl border border-slate-800 shadow-2xl max-w-4xl mx-auto font-sans leading-relaxed text-slate-200">
      <div className="space-y-4">
        {items.map((item) => {
          const { sequence_number, content_type, text_content } = item;

          if (content_type === 'page_title') {
            return (
              <div key={sequence_number} className="pb-4 border-b border-slate-800">
                <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                  {text_content}
                </h1>
              </div>
            );
          }

          if (content_type === 'heading_1') {
            return (
              <h2
                key={sequence_number}
                className="text-xl sm:text-2xl font-bold text-white pt-6 pb-2 border-b border-slate-800/80 tracking-tight"
              >
                {text_content}
              </h2>
            );
          }

          if (content_type === 'heading_2') {
            return (
              <h3
                key={sequence_number}
                className="text-lg sm:text-xl font-bold text-slate-100 pt-5 pb-1 tracking-tight"
              >
                {text_content}
              </h3>
            );
          }

          if (content_type.startsWith('heading_')) {
            return (
              <h4
                key={sequence_number}
                className="text-base sm:text-lg font-semibold text-slate-200 pt-3"
              >
                {text_content}
              </h4>
            );
          }

          if (content_type === 'list_item') {
            return (
              <div
                key={sequence_number}
                className="flex items-start gap-2.5 pl-4 text-sm text-slate-300"
              >
                <span className="text-brand-400 mt-1 shrink-0">•</span>
                <span>{text_content.replace(/^[•\-\*]\s*/, '')}</span>
              </div>
            );
          }

          if (content_type.startsWith('table')) {
            return (
              <div
                key={sequence_number}
                className="my-2 p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-xs font-mono text-slate-300 overflow-x-auto"
              >
                {text_content}
              </div>
            );
          }

          if (content_type === 'blockquote') {
            return (
              <blockquote
                key={sequence_number}
                className="border-l-4 border-brand-500 pl-4 py-1 italic text-slate-400 my-3 text-sm"
              >
                {text_content}
              </blockquote>
            );
          }

          if (content_type === 'code_block') {
            return (
              <pre
                key={sequence_number}
                className="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono text-emerald-400 overflow-x-auto my-3"
              >
                <code>{text_content}</code>
              </pre>
            );
          }

          if (content_type === 'link') {
            return (
              <div key={sequence_number} className="text-xs text-sky-400 my-1">
                🔗 {text_content}
              </div>
            );
          }

          // Default paragraph
          return (
            <p key={sequence_number} className="text-sm md:text-base text-slate-300 leading-relaxed">
              {text_content}
            </p>
          );
        })}
      </div>
    </div>
  );
};
