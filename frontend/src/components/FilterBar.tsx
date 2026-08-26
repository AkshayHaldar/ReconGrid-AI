import React from "react";
import { Search, Download, FileSpreadsheet, FileJson, Layers } from "lucide-react";
import { ReconciliationStatus } from "@/lib/types";

interface FilterBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  status: ReconciliationStatus | null;
  onExportCsv: () => void;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
  status,
  onExportCsv,
}) => {
  const tabs = [
    { id: "ALL", label: "All", count: status?.total_records || 0 },
    { id: "MATCHED", label: "Matched", count: status?.matched_count || 0, color: "text-emerald-400" },
    { id: "SUGGESTED", label: "Suggested", count: status?.suggested_count || 0, color: "text-sky-400" },
    { id: "CONFLICT", label: "Conflicts", count: status?.conflict_count || 0, color: "text-orange-400" },
    { id: "EXCEPTION", label: "Exceptions", count: status?.exception_count || 0, color: "text-rose-400" },
  ];

  return (
    <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 mb-3.5">
      {/* Status Filter Tabs */}
      <div className="flex items-center gap-1 bg-[#0e1524] border border-[#1e2a3f] p-1 rounded-lg overflow-x-auto text-xs">
        {tabs.map((t) => {
          const isActive = activeTab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => onTabChange(t.id)}
              className={`px-3 py-1.5 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap ${
                isActive
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <span>{t.label}</span>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
                  isActive ? "bg-blue-800 text-blue-100" : "bg-slate-800 text-slate-400"
                }`}
              >
                {t.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Search and Export Actions */}
      <div className="flex items-center gap-2.5">
        <div className="relative flex-1 sm:w-64">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search UTR, Order, Settlement ID..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-[#0e1524] border border-[#1e2a3f] rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition font-mono"
          />
        </div>

        <button
          onClick={onExportCsv}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0e1524] hover:bg-slate-800 border border-[#1e2a3f] hover:border-slate-600 rounded-lg text-xs font-medium text-slate-200 transition shrink-0"
          title="Download CA-Ready Audit CSV"
        >
          <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
          <span>Export Audit CSV</span>
        </button>
      </div>
    </div>
  );
};
