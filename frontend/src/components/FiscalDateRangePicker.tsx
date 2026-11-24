import React, { useState, useRef, useEffect, useMemo } from "react";
import { Calendar, ChevronDown, RotateCcw, Check, X } from "lucide-react";
import {
  getCurrentIndianQuarter,
  getPreviousIndianQuarter,
  getLast30Days,
  formatCompactDate,
  formatCompactDateShort,
} from "@/lib/fiscalDate";

export interface FiscalDateRangePickerProps {
  fromDate?: string;
  toDate?: string;
  onChange: (fromDate?: string, toDate?: string) => void;
  periodDate?: string | Date | null;
}

export const FiscalDateRangePicker: React.FC<FiscalDateRangePickerProps> = ({
  fromDate,
  toDate,
  onChange,
  periodDate,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Dynamic calculations based on reference / current date in IST
  const currentQuarter = useMemo(() => getCurrentIndianQuarter(periodDate), [periodDate]);
  const previousQuarter = useMemo(() => getPreviousIndianQuarter(periodDate), [periodDate]);
  const last30Days = useMemo(() => getLast30Days(periodDate), [periodDate]);

  // Local state for custom range inputs
  const [customFrom, setCustomFrom] = useState(fromDate || "");
  const [customTo, setCustomTo] = useState(toDate || "");
  const [customError, setCustomError] = useState<string | null>(null);

  // Sync custom inputs with props when opened or props change
  useEffect(() => {
    setCustomFrom(fromDate || "");
    setCustomTo(toDate || "");
    setCustomError(null);
  }, [fromDate, toDate, isOpen]);

  // Detect which preset is currently active
  const activePreset = useMemo(() => {
    if (!fromDate && !toDate) return "ALL";
    if (fromDate === currentQuarter.fromDate && toDate === currentQuarter.toDate) {
      return "CURRENT_QUARTER";
    }
    if (fromDate === previousQuarter.fromDate && toDate === previousQuarter.toDate) {
      return "PREVIOUS_QUARTER";
    }
    if (fromDate === last30Days.fromDate && toDate === last30Days.toDate) {
      return "LAST_30_DAYS";
    }
    return "CUSTOM";
  }, [fromDate, toDate, currentQuarter, previousQuarter, last30Days]);

  // Click outside to close
  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleOutsideClick);
    }
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  // Label for trigger button
  const triggerLabel = useMemo(() => {
    if (activePreset === "CURRENT_QUARTER") {
      return `FY ${currentQuarter.quarter} (${currentQuarter.quarterLabel.split(" ")[1]?.replace(/[()]/g, "") || "Cur"})`;
    }
    if (activePreset === "PREVIOUS_QUARTER") {
      return `FY ${previousQuarter.quarter} (${previousQuarter.quarterLabel.split(" ")[1]?.replace(/[()]/g, "") || "Prev"})`;
    }
    if (activePreset === "LAST_30_DAYS") {
      return "Last 30 Days";
    }
    if (activePreset === "CUSTOM") {
      if (fromDate && toDate) {
        return `${formatCompactDateShort(fromDate)} – ${formatCompactDateShort(toDate)}`;
      }
      if (fromDate) return `From ${formatCompactDateShort(fromDate)}`;
      if (toDate) return `Until ${formatCompactDateShort(toDate)}`;
    }
    return "Date Range";
  }, [activePreset, currentQuarter, previousQuarter, fromDate, toDate]);

  const handleApplyPreset = (start: string, end: string) => {
    onChange(start, end);
    setIsOpen(false);
  };

  const handleReset = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    onChange(undefined, undefined);
    setCustomFrom("");
    setCustomTo("");
    setCustomError(null);
    setIsOpen(false);
  };

  const handleApplyCustom = () => {
    setCustomError(null);
    if (!customFrom && !customTo) {
      handleReset();
      return;
    }
    if (customFrom && customTo && customFrom > customTo) {
      setCustomError("Start date cannot be after end date");
      return;
    }
    onChange(customFrom || undefined, customTo || undefined);
    setIsOpen(false);
  };

  const isFiltered = Boolean(fromDate || toDate);

  return (
    <div className="relative inline-block text-left" ref={containerRef}>
      {/* Trigger Button or Split Button Group */}
      {!isFiltered ? (
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          aria-expanded={isOpen}
          aria-haspopup="true"
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition cursor-pointer shadow-xs select-none bg-[#111318] border border-[#1e222d] hover:border-neutral-700 text-neutral-300"
          title="Filter by Indian FY Quarter or Date Range"
        >
          <Calendar className="w-3.5 h-3.5 shrink-0 text-neutral-400" />
          <span className="whitespace-nowrap font-medium text-[11px] sm:text-xs">{triggerLabel}</span>
          <ChevronDown
            className={`w-3 h-3 shrink-0 transition-transform duration-150 text-neutral-400 ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </button>
      ) : (
        <div className="inline-flex items-stretch rounded-md shadow-xs bg-sky-950/40 border border-sky-700/70 text-sky-200">
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            aria-expanded={isOpen}
            aria-haspopup="true"
            className="flex items-center gap-1.5 pl-2.5 pr-2 py-1.5 text-xs font-medium transition cursor-pointer select-none rounded-l-md hover:bg-sky-950/60"
            title={`Active Filter: ${fromDate || "any"} to ${toDate || "any"} (IST)`}
          >
            <Calendar className="w-3.5 h-3.5 shrink-0 text-sky-400" />
            <span className="whitespace-nowrap font-medium text-[11px] sm:text-xs">{triggerLabel}</span>
            <ChevronDown
              className={`w-3 h-3 shrink-0 transition-transform duration-150 text-sky-400 ${
                isOpen ? "rotate-180" : ""
              }`}
            />
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="px-2 py-1.5 text-sky-300 hover:text-white hover:bg-sky-900/60 transition cursor-pointer rounded-r-md border-l border-sky-700/70 flex items-center justify-center"
            title="Reset Dates"
            aria-label="Reset Dates"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Popover Dropdown */}
      {isOpen && (
        <div className="absolute right-0 sm:left-0 sm:right-auto mt-1.5 w-76 sm:w-80 bg-[#111318] border border-[#1e222d] rounded-lg shadow-2xl p-3 z-50 animate-in fade-in zoom-in-95 duration-100 font-sans">
          {/* Header */}
          <div className="flex items-center justify-between pb-2 mb-2.5 border-b border-[#1e222d]">
            <div>
              <div className="text-xs font-semibold text-neutral-200">Fiscal Date Range</div>
              <div className="text-[10px] text-neutral-400">Indian Financial Year (IST / Asia/Kolkata)</div>
            </div>
            {isFiltered && (
              <button
                type="button"
                onClick={handleReset}
                className="flex items-center gap-1 text-[11px] font-mono text-neutral-400 hover:text-neutral-100 transition px-1.5 py-0.5 rounded hover:bg-neutral-800 cursor-pointer"
                title="Clear all date filters"
              >
                <RotateCcw className="w-2.5 h-2.5" />
                <span>Reset</span>
              </button>
            )}
          </div>

          {/* Quick Presets */}
          <div className="space-y-1.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 px-1 font-semibold">
              Financial Year Presets
            </div>

            {/* Current Quarter Button */}
            <button
              type="button"
              onClick={() => handleApplyPreset(currentQuarter.fromDate, currentQuarter.toDate)}
              className={`w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs transition cursor-pointer text-left ${
                activePreset === "CURRENT_QUARTER"
                  ? "bg-sky-950/60 border border-sky-700/80 text-sky-200 font-medium"
                  : "bg-[#151820] hover:bg-[#1c202a] border border-[#1e222d] text-neutral-300"
              }`}
            >
              <div className="min-w-0 pr-2">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-neutral-100 text-xs">
                    Current Quarter ({currentQuarter.quarter})
                  </span>
                  <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-neutral-900 border border-neutral-700 text-neutral-300">
                    {currentQuarter.fyLabel}
                  </span>
                </div>
                <div className="text-[10px] text-neutral-400 truncate mt-0.5 font-mono">
                  {formatCompactDate(currentQuarter.fromDate)} – {formatCompactDate(currentQuarter.toDate)}
                </div>
              </div>
              {activePreset === "CURRENT_QUARTER" && <Check className="w-3.5 h-3.5 text-sky-400 shrink-0" />}
            </button>

            {/* Previous Quarter Button */}
            <button
              type="button"
              onClick={() => handleApplyPreset(previousQuarter.fromDate, previousQuarter.toDate)}
              className={`w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs transition cursor-pointer text-left ${
                activePreset === "PREVIOUS_QUARTER"
                  ? "bg-sky-950/60 border border-sky-700/80 text-sky-200 font-medium"
                  : "bg-[#151820] hover:bg-[#1c202a] border border-[#1e222d] text-neutral-300"
              }`}
            >
              <div className="min-w-0 pr-2">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-neutral-100 text-xs">
                    Previous Quarter ({previousQuarter.quarter})
                  </span>
                  <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-neutral-900 border border-neutral-700 text-neutral-300">
                    {previousQuarter.fyLabel}
                  </span>
                </div>
                <div className="text-[10px] text-neutral-400 truncate mt-0.5 font-mono">
                  {formatCompactDate(previousQuarter.fromDate)} – {formatCompactDate(previousQuarter.toDate)}
                </div>
              </div>
              {activePreset === "PREVIOUS_QUARTER" && <Check className="w-3.5 h-3.5 text-sky-400 shrink-0" />}
            </button>

            {/* Last 30 Days Button */}
            <button
              type="button"
              onClick={() => handleApplyPreset(last30Days.fromDate, last30Days.toDate)}
              className={`w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs transition cursor-pointer text-left ${
                activePreset === "LAST_30_DAYS"
                  ? "bg-sky-950/60 border border-sky-700/80 text-sky-200 font-medium"
                  : "bg-[#151820] hover:bg-[#1c202a] border border-[#1e222d] text-neutral-300"
              }`}
            >
              <div className="min-w-0 pr-2">
                <div className="font-semibold text-neutral-100 text-xs">Last 30 Days</div>
                <div className="text-[10px] text-neutral-400 truncate mt-0.5 font-mono">
                  {formatCompactDate(last30Days.fromDate)} – {formatCompactDate(last30Days.toDate)}
                </div>
              </div>
              {activePreset === "LAST_30_DAYS" && <Check className="w-3.5 h-3.5 text-sky-400 shrink-0" />}
            </button>
          </div>

          {/* Divider */}
          <div className="border-t border-[#1e222d] my-2.5" />

          {/* Custom Date Range */}
          <div className="space-y-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 px-1 font-semibold">
              Custom Range
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] text-neutral-400 font-mono mb-1">Start Date</label>
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => {
                    setCustomFrom(e.target.value);
                    setCustomError(null);
                  }}
                  className="w-full bg-[#090a0f] border border-[#1e222d] hover:border-neutral-700 focus:border-neutral-500 rounded px-2 py-1 text-xs text-neutral-200 font-mono focus:outline-none [color-scheme:dark]"
                />
              </div>
              <div>
                <label className="block text-[10px] text-neutral-400 font-mono mb-1">End Date</label>
                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => {
                    setCustomTo(e.target.value);
                    setCustomError(null);
                  }}
                  className="w-full bg-[#090a0f] border border-[#1e222d] hover:border-neutral-700 focus:border-neutral-500 rounded px-2 py-1 text-xs text-neutral-200 font-mono focus:outline-none [color-scheme:dark]"
                />
              </div>
            </div>

            {customError && <div className="text-[11px] text-rose-400 font-medium px-1">{customError}</div>}

            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={handleApplyCustom}
                disabled={!customFrom && !customTo}
                className="flex-1 py-1.5 px-3 bg-neutral-800 hover:bg-neutral-700 disabled:opacity-40 disabled:pointer-events-none text-neutral-100 font-medium rounded-md text-xs transition cursor-pointer text-center"
              >
                Apply Range
              </button>
              {isFiltered && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="py-1.5 px-3 bg-[#151820] hover:bg-[#1f2430] border border-[#1e222d] text-neutral-300 font-medium rounded-md text-xs transition cursor-pointer text-center"
                >
                  Reset Dates
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
