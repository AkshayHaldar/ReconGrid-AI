import React from "react";
import {
  Search,
  FileSpreadsheet,
  CheckCheck,
  SlidersHorizontal,
  X,
  Calendar,
  RotateCcw,
} from "lucide-react";
import { ReconciliationStatus } from "@/lib/types";
import {
  DatePresetId,
  detectDatePreset,
  getDatePresetRange,
  parseAmountInput,
} from "@/lib/filters";

interface FilterBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  status: ReconciliationStatus | null;
  onExportCsv: () => void;
  selectedDiagnostic?: string;
  onDiagnosticChange?: (d: string) => void;
  startDate?: string;
  onStartDateChange?: (d: string) => void;
  endDate?: string;
  onEndDateChange?: (d: string) => void;
  minAmount?: string;
  onMinAmountChange?: (a: string) => void;
  maxAmount?: string;
  onMaxAmountChange?: (a: string) => void;
  onClearFilters?: () => void;
  filteredCount?: number;
  totalLoadedCount?: number;
  onBatchApprove?: () => void;
  batchApproveLoading?: boolean;
}

export const sanitizeAmountInput = (raw: string): string => {
  const cleaned = raw.replace(/[^\d.,]/g, "");
  const dotIndex = cleaned.indexOf(".");
  if (dotIndex === -1) return cleaned;
  return cleaned.slice(0, dotIndex + 1) + cleaned.slice(dotIndex + 1).replace(/\./g, "");
};

export const FilterBar: React.FC<FilterBarProps> = ({
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
  status,
  onExportCsv,
  selectedDiagnostic = "ALL",
  onDiagnosticChange,
  startDate = "",
  onStartDateChange,
  endDate = "",
  onEndDateChange,
  minAmount = "",
  onMinAmountChange,
  maxAmount = "",
  onMaxAmountChange,
  onClearFilters,
  filteredCount,
  totalLoadedCount,
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

  const highConfidenceCandidates = status?.suggested_count || 0;

  const datePreset = detectDatePreset(startDate, endDate);
  const isDateRangeInverted = Boolean(startDate && endDate && startDate > endDate);

  const parsedMin = parseAmountInput(minAmount);
  const parsedMax = parseAmountInput(maxAmount);
  const isAmountRangeInverted =
    parsedMin !== null && parsedMax !== null && parsedMin > parsedMax;

  const hasDateFilter = Boolean(startDate || endDate);
  const hasAmountFilter = parsedMin !== null || parsedMax !== null;
  const hasDiagnosticFilter = selectedDiagnostic !== "ALL";
  const hasSearchFilter = Boolean(searchQuery.trim());

  const activeSecondaryCount =
    (hasDateFilter ? 1 : 0) +
    (hasAmountFilter ? 1 : 0) +
    (hasDiagnosticFilter ? 1 : 0) +
    (hasSearchFilter ? 1 : 0);

  const hasSecondaryFilters = activeSecondaryCount > 0;

  const handlePresetChange = (preset: DatePresetId) => {
    if (preset === "CUSTOM") return;
    const range = getDatePresetRange(preset);
    onStartDateChange?.(range.startDate);
    onEndDateChange?.(range.endDate);
  };

  const handleClearAllSecondary = () => {
    if (onClearFilters) {
      onClearFilters();
      return;
    }
    onStartDateChange?.("");
    onEndDateChange?.("");
    onMinAmountChange?.("");
    onMaxAmountChange?.("");
    onDiagnosticChange?.("ALL");
    onSearchChange("");
  };

  return (
    <div className="flex flex-col gap-2 mb-3.5">
      {/* Row 1: Primary Status Tabs, Search & Actions */}
      <div className="flex flex-col xl:flex-row items-stretch xl:items-center justify-between gap-2">
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

        {/* Search, Batch Approve, and Export */}
        <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
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
                type="button"
                onClick={() => onSearchChange("")}
                aria-label="Clear search query"
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

      {/* Row 2: Secondary Audit Filters (Diagnostic, Date Range, Amount Range, Clear Filters) */}
      <div className="flex flex-wrap items-center justify-between gap-2 bg-[#0d0f14] border border-[#1e222d] rounded-lg px-2.5 py-1.5 shadow-xs">
        <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
          {/* Diagnostic Sub-Filter */}
          {onDiagnosticChange && (
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 bg-[#111318] border rounded-md text-xs text-neutral-300 w-full sm:w-48 lg:w-52 shrink-0 transition shadow-xs ${
                hasDiagnosticFilter
                  ? "border-sky-800/70"
                  : "border-[#1e222d] hover:border-neutral-700"
              }`}
            >
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

          {/* Compact Date Range Filter Control */}
          {onStartDateChange && onEndDateChange && (
            <div
              className={`flex flex-wrap sm:flex-nowrap items-center gap-1.5 px-2.5 py-1 bg-[#111318] border rounded-md text-xs w-full sm:w-auto transition shadow-xs ${
                isDateRangeInverted
                  ? "border-amber-700/70"
                  : hasDateFilter
                  ? "border-sky-800/70"
                  : "border-[#1e222d] hover:border-neutral-700 focus-within:border-neutral-500"
              }`}
              title={
                isDateRangeInverted
                  ? "Start date is after end date"
                  : "Filter transactions by statement date window"
              }
            >
              <div className="flex items-center gap-1.5 shrink-0">
                <Calendar className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
                <select
                  aria-label="Date range preset"
                  value={datePreset}
                  onChange={(e) => handlePresetChange(e.target.value as DatePresetId)}
                  className="bg-transparent border-none text-[11px] sm:text-xs text-neutral-200 font-medium focus:outline-none cursor-pointer pr-1"
                >
                  <option value="ALL" className="bg-[#111318] text-neutral-200">
                    All Dates
                  </option>
                  <option value="THIS_MONTH" className="bg-[#111318] text-neutral-200">
                    This Month
                  </option>
                  <option value="LAST_MONTH" className="bg-[#111318] text-neutral-200">
                    Last Month
                  </option>
                  <option value="LAST_7_DAYS" className="bg-[#111318] text-neutral-200">
                    Last 7 Days
                  </option>
                  <option value="LAST_30_DAYS" className="bg-[#111318] text-neutral-200">
                    Last 30 Days
                  </option>
                  {datePreset === "CUSTOM" && (
                    <option value="CUSTOM" className="bg-[#111318] text-neutral-200">
                      Custom Range
                    </option>
                  )}
                </select>
              </div>

              <span className="hidden sm:inline text-neutral-700">|</span>

              <div className="flex flex-wrap items-center gap-1.5 w-full sm:w-auto">
                <div className="flex items-center gap-1.5">
                  <label
                    htmlFor="filter-start-date"
                    className="text-[10px] font-mono uppercase text-neutral-500 select-none"
                  >
                    From
                  </label>
                  <input
                    id="filter-start-date"
                    type="date"
                    aria-label="Start date"
                    value={startDate}
                    max={endDate || undefined}
                    onChange={(e) => onStartDateChange(e.target.value)}
                    className="bg-transparent text-[11px] font-mono font-tabular text-neutral-200 focus:outline-none [color-scheme:dark] w-[112px] cursor-pointer"
                  />
                </div>

                <span className="text-neutral-600 text-xs">&ndash;</span>

                <div className="flex items-center gap-1.5">
                  <label
                    htmlFor="filter-end-date"
                    className="text-[10px] font-mono uppercase text-neutral-500 select-none"
                  >
                    To
                  </label>
                  <input
                    id="filter-end-date"
                    type="date"
                    aria-label="End date"
                    value={endDate}
                    min={startDate || undefined}
                    onChange={(e) => onEndDateChange(e.target.value)}
                    className="bg-transparent text-[11px] font-mono font-tabular text-neutral-200 focus:outline-none [color-scheme:dark] w-[112px] cursor-pointer"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Compact Amount Range Filter Control (INR Min - Max) */}
          {onMinAmountChange && onMaxAmountChange && (
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 bg-[#111318] border rounded-md text-xs w-full sm:w-auto transition shadow-xs ${
                isAmountRangeInverted
                  ? "border-amber-700/70"
                  : hasAmountFilter
                  ? "border-sky-800/70"
                  : "border-[#1e222d] hover:border-neutral-700 focus-within:border-neutral-500"
              }`}
              title={
                isAmountRangeInverted
                  ? "Minimum amount exceeds maximum amount"
                  : "Filter by bank transaction amount (INR)"
              }
            >
              <span
                className="text-[11px] font-mono font-semibold text-neutral-400 shrink-0 select-none"
                aria-hidden="true"
              >
                &#8377;
              </span>
              <input
                id="filter-min-amount"
                type="text"
                inputMode="decimal"
                aria-label="Min Amount"
                placeholder="Min Amt"
                value={minAmount}
                onChange={(e) => onMinAmountChange(sanitizeAmountInput(e.target.value))}
                className="bg-transparent text-[11px] sm:text-xs font-mono font-tabular text-neutral-200 placeholder-neutral-500 focus:outline-none flex-1 min-w-0 sm:flex-none sm:w-20 lg:w-24"
              />
              <span className="text-neutral-600 text-xs shrink-0">&ndash;</span>
              <input
                id="filter-max-amount"
                type="text"
                inputMode="decimal"
                aria-label="Max Amount"
                placeholder="Max Amt"
                value={maxAmount}
                onChange={(e) => onMaxAmountChange(sanitizeAmountInput(e.target.value))}
                className="bg-transparent text-[11px] sm:text-xs font-mono font-tabular text-neutral-200 placeholder-neutral-500 focus:outline-none flex-1 min-w-0 sm:flex-none sm:w-20 lg:w-24"
              />
            </div>
          )}
        </div>

        {/* Active Count + Clear Filters Chip */}
        {hasSecondaryFilters && (
          <div className="flex items-center gap-2 shrink-0">
            {filteredCount !== undefined && totalLoadedCount !== undefined && (
              <span className="text-[10px] font-mono text-neutral-400 font-tabular px-2 py-1 bg-[#111318] border border-[#1e222d] rounded-md">
                {filteredCount} / {totalLoadedCount} shown
              </span>
            )}
            <button
              type="button"
              onClick={handleClearAllSecondary}
              aria-label="Clear Filters"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-sky-950/50 hover:bg-sky-900/70 border border-sky-800/70 text-sky-300 hover:text-sky-100 rounded-md text-[11px] font-medium transition cursor-pointer shadow-xs whitespace-nowrap"
              title="Reset all active date, amount, diagnostic, and search filters"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Clear Filters</span>
              <span className="text-[10px] font-mono bg-sky-900/80 px-1 rounded text-sky-200 font-tabular">
                {activeSecondaryCount}
              </span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
