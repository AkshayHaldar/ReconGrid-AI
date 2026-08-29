import React from "react";
import {
  Search,
  FileSpreadsheet,
  CheckCheck,
  Filter,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { ReconciliationStatus } from "@/lib/types";

interface FilterBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  status: ReconciliationStatus | null;
  onExportCsv: () => void;
  selectedDiagnostic?: string;
  onDiagnosticChange?: (d: string) => void;
  onBatchApprove?: () => void;
  batchApproveLoading?: boolean;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
  status,
  onExportCsv,
  selectedDiagnostic = "ALL",
  onDiagnosticChange,
  onBatchApprove,
  batchApproveLoading = false,
}) => {
  const tabs = [
    { id: "ALL", label: "All Records", count: status?.total_records || 0, shortcut: "1" },
    {
      id: "MATCHED",
      label: "Matched",
      count: status?.matched_count || 0,
      shortcut: "2",
      color: "text-emerald-400",
    },
    {
      id: "SUGGESTED",
      label: "Suggested",
      count: status?.suggested_count || 0,
      shortcut: "3",
      color: "text-sky-400",
    },
    {
      id: "CONFLICT",
      label: "Conflicts",
      count: status?.conflict_count || 0,
      shortcut: "4",
      color: "text-orange-400",
    },
    {
      id: "EXCEPTION",
      label: "Exceptions",
      count: status?.exception_count || 0,
      shortcut: "5",
      color: "text-rose-400",
    },
  ];

  return (
    <div className="flex flex-col gap-2 sm:gap-2.5 mb-3">
      <div className="flex flex-col xl:flex-row items-stretch xl:items-center justify-between gap-2 sm:gap-2.5">
        {/* Status Filter Tabs */}
        <div className="flex items-center gap-1 bg-[#0f1624] border border-[#1c2b42] p-1 rounded overflow-x-auto text-xs touch-scroll scrollbar-none">
          {tabs.map((t) => {
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => onTabChange(t.id)}
                className={`px-2.5 sm:px-3 py-1 rounded font-medium transition flex items-center gap-1 sm:gap-1.5 whitespace-nowrap text-[11px] sm:text-xs shrink-0 ${
                  isActive
                    ? "bg-[#18263e] text-blue-300 border border-[#233c64] shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-[#131d2e]"
                }`}
              >
                <span>{t.label}</span>
                <span
                  className={`text-[9px] sm:text-[10px] font-mono px-1.5 py-0.2 rounded ${
                    isActive
                      ? "bg-blue-950 text-blue-300 border border-blue-800"
                      : "bg-[#0b101b] text-slate-400"
                  }`}
                >
                  {t.count}
                </span>
                <span className="hidden md:inline text-[9px] font-mono opacity-60 text-slate-400">
                  [{t.shortcut}]
                </span>
              </button>
            );
          })}
        </div>

        {/* Search, Diagnostic Sub-Filter, and Export */}
        <div className="flex flex-wrap sm:flex-nowrap items-center gap-1.5 sm:gap-2">
          {/* Diagnostic Sub-Filter */}
          {onDiagnosticChange && (
            <div className="flex items-center gap-1 px-2 py-1 bg-[#0f1624] border border-[#1c2b42] rounded text-xs text-slate-300 flex-1 sm:flex-initial min-w-0">
              <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <select
                value={selectedDiagnostic}
                onChange={(e) => onDiagnosticChange(e.target.value)}
                className="bg-transparent border-none text-[11px] sm:text-xs text-slate-200 focus:outline-none cursor-pointer font-sans w-full truncate"
              >
                <option value="ALL" className="bg-[#0f1624] text-slate-200">
                  All Diagnostics
                </option>
                <option value="FEE_DEDUCTION" className="bg-[#0f1624] text-slate-200">
                  Fee Deductions (MDR + GST)
                </option>
                <option value="TDS_194O_DEDUCTION" className="bg-[#0f1624] text-slate-200">
                  Section 194-O TDS (1%)
                </option>
                <option value="BATCHED_SETTLEMENT" className="bg-[#0f1624] text-slate-200">
                  Batched Settlements
                </option>
                <option value="REFUND_ADJUSTED" className="bg-[#0f1624] text-slate-200">
                  Refund Adjustments
                </option>
                <option value="FX_ADJUSTED" className="bg-[#0f1624] text-slate-200">
                  FX Adjustments
                </option>
                <option value="REVERSAL" className="bg-[#0f1624] text-slate-200">
                  Debit Reversals
                </option>
                <option value="UNRESOLVED" className="bg-[#0f1624] text-slate-200">
                  Unresolved Exceptions
                </option>
              </select>
            </div>
          )}

          {/* Search Box */}
          <div className="relative w-full sm:w-48 md:w-56 shrink-0">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              id="ledger-search-input"
              placeholder="Search UTR, Order, Settlement..."
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-8 pr-7 py-1 bg-[#0f1624] border border-[#1c2b42] rounded text-[11px] sm:text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition font-mono"
            />
            <span className="hidden sm:inline absolute right-2 top-1/2 -translate-y-1/2 text-[9px] font-mono text-slate-400 bg-[#0a0f19] px-1 py-0.2 rounded border border-[#182338]">
              /
            </span>
          </div>

          {/* Power Batch Action: Approve High-Confidence */}
          {onBatchApprove && (activeTab === "SUGGESTED" || (status?.suggested_count || 0) > 0) && (
            <button
              onClick={onBatchApprove}
              disabled={batchApproveLoading || (status?.suggested_count || 0) === 0}
              className="flex items-center justify-center gap-1.5 px-2.5 py-1 bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-700/80 text-emerald-300 hover:text-emerald-100 rounded text-xs font-medium transition disabled:opacity-50 whitespace-nowrap shrink-0"
              title="Batch approve all suggestions with confidence ≥ 90%"
            >
              <CheckCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>
                {batchApproveLoading ? "Approving..." : "Batch Approve (≥90%)"}
              </span>
            </button>
          )}

          {/* Export CA Audit CSV */}
          <button
            onClick={onExportCsv}
            className="flex items-center justify-center gap-1.5 px-2.5 py-1 bg-[#0f1624] hover:bg-[#152033] border border-[#1c2b42] hover:border-slate-600 rounded text-xs font-medium text-slate-200 transition shrink-0 whitespace-nowrap"
            title="Download full CA-Ready Audit CSV with GST and Settlement Logs"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden sm:inline">Export Audit CSV</span>
            <span className="sm:hidden">CSV</span>
          </button>
        </div>
      </div>
    </div>
  );
};
