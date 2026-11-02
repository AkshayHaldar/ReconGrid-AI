import React from "react";
import {
  Search,
  FileSpreadsheet,
  CheckCheck,
  Filter,
  SlidersHorizontal,
  X,
  Layers,
  ArrowDownLeft,
  ArrowUpRight,
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
      activeBg: "bg-emerald-950/40 text-emerald-300 border-emerald-700/60",
    },
    {
      id: "SUGGESTED",
      label: "Suggested",
      count: status?.suggested_count || 0,
      shortcut: "3",
      color: "text-sky-400",
      activeBg: "bg-sky-950/40 text-sky-300 border-sky-700/60",
    },
    {
      id: "CONFLICT",
      label: "Conflicts",
      count: status?.conflict_count || 0,
      shortcut: "4",
      color: "text-amber-400",
      activeBg: "bg-amber-950/40 text-amber-300 border-amber-700/60",
    },
    ...(status?.pending_count && status.pending_count > 0
      ? [
          {
            id: "PENDING_SETTLEMENT_DATA",
            label: "In-Transit",
            count: status.pending_count,
            shortcut: "6",
            color: "text-purple-400",
            activeBg: "bg-purple-950/40 text-purple-300 border-purple-700/60",
          },
        ]
      : []),
    {
      id: "EXCEPTION",
      label: "Exceptions",
      count: status?.exception_count || 0,
      shortcut: "5",
      color: "text-rose-400",
      activeBg: "bg-rose-950/40 text-rose-300 border-rose-700/60",
    },
  ];

  const highConfidenceCandidates = (status?.suggested_count || 0);

  return (
    <div className="flex flex-col gap-2.5 mb-3.5">
      <div className="flex flex-col xl:flex-row items-stretch xl:items-center justify-between gap-2.5">
        {/* Status Filter Tabs */}
        <div className="flex items-center gap-1 bg-[#111318] border border-[#1e222d] p-1 rounded-lg overflow-x-auto text-xs touch-scroll scrollbar-none shadow-xs">
          {tabs.map((t) => {
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => onTabChange(t.id)}
                className={`px-3 py-1.5 rounded-md font-medium transition flex items-center gap-1.5 whitespace-nowrap text-xs shrink-0 cursor-pointer ${
                  isActive
                    ? "bg-neutral-800 text-neutral-100 border border-neutral-700 shadow-xs"
                    : "text-neutral-400 hover:text-neutral-200 hover:bg-[#151820]"
                }`}
              >
                <span>{t.label}</span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.2 rounded font-tabular ${
                    isActive
                      ? "bg-neutral-900 text-neutral-200 border border-neutral-700"
                      : "bg-[#090a0f] text-neutral-400"
                  }`}
                >
                  {t.count}
                </span>
                <span className="hidden md:inline text-[9px] font-mono opacity-50 text-neutral-400">
                  [{t.shortcut}]
                </span>
              </button>
            );
          })}
        </div>

        {/* Search, Diagnostic Sub-Filter, and Export */}
        <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
          {/* Diagnostic Sub-Filter */}
          {onDiagnosticChange && (
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#111318] border border-[#1e222d] hover:border-neutral-700 rounded-md text-xs text-neutral-300 flex-1 sm:flex-initial min-w-0 transition shadow-xs">
              <SlidersHorizontal className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
              <select
                value={selectedDiagnostic}
                onChange={(e) => onDiagnosticChange(e.target.value)}
                className="bg-transparent border-none text-[11px] sm:text-xs text-neutral-200 focus:outline-none cursor-pointer font-sans w-full truncate pr-1"
                aria-label="Filter by Diagnostic Sub-Type"
              >
                <option value="ALL" className="bg-[#111318] text-neutral-200">
                  All Diagnostics
                </option>
                <option value="FEE_DEDUCTION" className="bg-[#111318] text-neutral-200">
                  MDR Fee Deductions (2% + 18% GST)
                </option>
                <option value="TDS_194O_DEDUCTION" className="bg-[#111318] text-neutral-200">
                  Section 194-O TDS (1%)
                </option>
                <option value="BATCHED_SETTLEMENT" className="bg-[#111318] text-neutral-200">
                  Batched Settlements
                </option>
                <option value="REFUND_ADJUSTED" className="bg-[#111318] text-neutral-200">
                  Customer Refund Adjustments
                </option>
                <option value="FX_ADJUSTED" className="bg-[#111318] text-neutral-200">
                  FX Conversion Adjustments
                </option>
                <option value="REVERSAL" className="bg-[#111318] text-neutral-200">
                  Direct Debit Reversals
                </option>
                <option value="PENDING_SETTLEMENT" className="bg-[#111318] text-neutral-200">
                  In-Transit Pending Settlements
                </option>
                <option value="UNRESOLVED" className="bg-[#111318] text-neutral-200">
                  Unresolved Exceptions
                </option>
              </select>
            </div>
          )}

          {/* Search Box */}
          <div className="relative w-full sm:w-52 md:w-60 shrink-0">
            <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              id="ledger-search-input"
              placeholder="Search UTR, Order, Settlement..."
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-8 pr-8 py-1.5 bg-[#111318] border border-[#1e222d] hover:border-neutral-700 rounded-md text-xs text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-neutral-500 transition font-mono shadow-xs"
            />
            {searchQuery ? (
              <button
                onClick={() => onSearchChange("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-200 p-0.5 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            ) : (
              <span className="hidden sm:inline absolute right-2.5 top-1/2 -translate-y-1/2 text-[9px] font-mono text-neutral-400 bg-neutral-900 px-1.5 py-0.2 rounded border border-neutral-800">
                /
              </span>
            )}
          </div>

          {/* Power Batch Action: Approve High-Confidence */}
          {onBatchApprove && (activeTab === "SUGGESTED" || highConfidenceCandidates > 0) && (
            <button
              onClick={onBatchApprove}
              disabled={batchApproveLoading || highConfidenceCandidates === 0}
              className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-emerald-950/60 hover:bg-emerald-900/80 border border-emerald-800/80 text-emerald-300 hover:text-emerald-100 rounded-md text-xs font-semibold transition disabled:opacity-50 whitespace-nowrap shadow-xs shrink-0 cursor-pointer"
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
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-[#111318] hover:bg-[#161922] border border-[#1e222d] hover:border-neutral-700 rounded-md text-xs font-medium text-neutral-200 transition shrink-0 whitespace-nowrap shadow-xs cursor-pointer"
            title="Download full CA-Ready Audit CSV with GST and Settlement Logs"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-neutral-400" />
            <span className="hidden sm:inline">Export Audit CSV</span>
            <span className="sm:hidden">CSV</span>
          </button>
        </div>
      </div>
    </div>
  );
};
