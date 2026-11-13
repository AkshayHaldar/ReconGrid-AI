"use client";

import React, { useState, useMemo } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Scale,
  Receipt,
  Layers,
  ArrowRight,
  Filter,
  Info,
  X,
} from "lucide-react";
import {
  DiagnosticType,
  MatchStatus,
  ReconciliationRecordItem,
  ReconciliationStatus,
  WaterfallSegmentId,
  FeeWaterfallStage,
} from "@/lib/types";
import { computeFeeWaterfall } from "@/lib/waterfall";
import { formatINR } from "@/lib/formatters";

interface FeeWaterfallBarProps {
  records?: ReconciliationRecordItem[];
  status?: ReconciliationStatus | null;
  activeDiagnostic?: DiagnosticType | "ALL" | string;
  activeTab?: string;
  onSelectDiagnostic?: (diagnostic: DiagnosticType | "ALL") => void;
  onFilterTab?: (tab: string) => void;
}

export const FeeWaterfallBar: React.FC<FeeWaterfallBarProps> = ({
  records = [],
  status,
  activeDiagnostic = "ALL",
  activeTab = "ALL",
  onSelectDiagnostic,
  onFilterTab,
}) => {
  const [hoveredStageId, setHoveredStageId] = useState<WaterfallSegmentId | null>(null);

  // Compute aggregated deductions ensuring mathematical conservation: Gross - (Fees + GST + TDS) = Net
  const breakdown = useMemo(() => {
    return computeFeeWaterfall(records, status);
  }, [records, status]);

  if (!breakdown || breakdown.grossAmount === 0) {
    return null;
  }

  // Handle segment click to filter the ledger table below
  const handleStageClick = (stage: FeeWaterfallStage) => {
    if (stage.id === "GROSS") {
      onSelectDiagnostic?.("ALL");
      onFilterTab?.("ALL");
    } else if (stage.id === "NET_CREDIT") {
      onSelectDiagnostic?.("ALL");
      onFilterTab?.("MATCHED");
    } else if (stage.diagnosticFilter) {
      // Toggle off if already selected
      if (activeDiagnostic === stage.diagnosticFilter) {
        onSelectDiagnostic?.("ALL");
      } else {
        onSelectDiagnostic?.(stage.diagnosticFilter);
      }
    }
  };

  const isStageActive = (stage: FeeWaterfallStage): boolean => {
    if (stage.id === "GROSS") {
      return activeDiagnostic === "ALL" && activeTab === "ALL";
    }
    if (stage.id === "NET_CREDIT") {
      return activeTab === "MATCHED" && activeDiagnostic === "ALL";
    }
    if (stage.id === "MDR_FEE" || stage.id === "GST_TAX") {
      return activeDiagnostic === "FEE_DEDUCTION";
    }
    if (stage.id === "TDS_194O") {
      return activeDiagnostic === "TDS_194O_DEDUCTION";
    }
    return false;
  };

  // Stacked bar segments: Net Bank Inflow + MDR Fees + GST on Fees + TDS = Gross (100%)
  const stackedSlices: {
    stage: FeeWaterfallStage;
    widthPct: number;
    barColor: string;
  }[] = [
    {
      stage: breakdown.stages.find((s) => s.id === "NET_CREDIT")!,
      widthPct: breakdown.grossAmount > 0
        ? Math.max(1.5, (breakdown.netBankAmount / breakdown.grossAmount) * 100)
        : 0,
      barColor: "bg-emerald-500 hover:bg-emerald-400",
    },
    {
      stage: breakdown.stages.find((s) => s.id === "MDR_FEE")!,
      widthPct: breakdown.grossAmount > 0 && breakdown.mdrFeeAmount > 0
        ? Math.max(1.5, (breakdown.mdrFeeAmount / breakdown.grossAmount) * 100)
        : 0,
      barColor: "bg-indigo-500 hover:bg-indigo-400",
    },
    {
      stage: breakdown.stages.find((s) => s.id === "GST_TAX")!,
      widthPct: breakdown.grossAmount > 0 && breakdown.gstTaxAmount > 0
        ? Math.max(1.5, (breakdown.gstTaxAmount / breakdown.grossAmount) * 100)
        : 0,
      barColor: "bg-amber-500 hover:bg-amber-400",
    },
    {
      stage: breakdown.stages.find((s) => s.id === "TDS_194O")!,
      widthPct: breakdown.grossAmount > 0 && breakdown.tdsAmount > 0
        ? Math.max(1.5, (breakdown.tdsAmount / breakdown.grossAmount) * 100)
        : 0,
      barColor: "bg-violet-500 hover:bg-violet-400",
    },
  ].filter((s) => Boolean(s.stage && s.stage.amount > 0));

  const hoveredStage = hoveredStageId
    ? breakdown.stages.find((s) => s.id === hoveredStageId)
    : null;

  return (
    <div
      className="fin-card rounded-lg p-3.5 shadow-xs border border-[#1e222d] space-y-3 font-sans transition-all"
      aria-label="Fee and Tax Waterfall Breakdown"
    >
      {/* Header with Title, Statutory Rates, and Trial Balance In-Balance Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-[#1e222d]">
        <div className="flex items-start sm:items-center gap-2">
          <div className="w-7 h-7 rounded bg-indigo-950/60 border border-indigo-800/60 flex items-center justify-center shrink-0 text-indigo-300">
            <Receipt className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="text-xs font-semibold text-neutral-100 uppercase tracking-wide">
                Fee & Tax Waterfall Deduction Breakdown
              </h4>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-800 border border-neutral-700 text-neutral-300">
                Institutional Audit
              </span>
            </div>
            <p className="text-[11px] text-neutral-400 font-sans mt-0.5">
              Statutory verification of Gateway MDR (2%), GST (18%), and Section 194-O TDS (1%) settlement leakages
            </p>
          </div>
        </div>

        {/* Trial Balance In-Balance Badge */}
        <div className="flex items-center gap-2 shrink-0 self-start sm:self-center">
          {breakdown.isInBalance ? (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-950/60 border border-emerald-800/70 text-emerald-300 text-[11px] font-mono font-medium shadow-xs"
              title="Mathematical Conservation verified: Gross - Deductions = Net Bank Credit (₹0.00 Variance)"
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span>Trial Balance: In Balance (₹0.00 Variance)</span>
            </div>
          ) : (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-950/60 border border-amber-800/70 text-amber-300 text-[11px] font-mono font-medium shadow-xs"
              title={`Variance: ${formatINR(breakdown.varianceAmount)}`}
            >
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>Variance: {formatINR(breakdown.varianceAmount)}</span>
            </div>
          )}

          {activeDiagnostic !== "ALL" && (
            <button
              onClick={() => onSelectDiagnostic?.("ALL")}
              className="flex items-center gap-1 px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 text-[10px] font-mono border border-neutral-700 transition cursor-pointer"
              title="Reset waterfall filter"
            >
              <X className="w-3 h-3" />
              <span>Reset Filter</span>
            </button>
          )}
        </div>
      </div>

      {/* 5-Stage Mathematical Decomposition Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 pt-0.5">
        {breakdown.stages.map((stage, idx) => {
          const active = isStageActive(stage);
          const isDeduction =
            stage.id === "MDR_FEE" || stage.id === "GST_TAX" || stage.id === "TDS_194O";
          const isResult = stage.id === "NET_CREDIT";

          return (
            <div
              key={stage.id}
              onClick={() => handleStageClick(stage)}
              onMouseEnter={() => setHoveredStageId(stage.id)}
              onMouseLeave={() => setHoveredStageId(null)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleStageClick(stage);
                }
              }}
              className={`relative rounded-lg p-2.5 border transition-all cursor-pointer select-none ${
                stage.color.bg
              } ${
                active
                  ? "ring-2 ring-indigo-400 border-indigo-400 shadow-md"
                  : stage.color.border
              } ${stage.color.hoverBg}`}
              title={`${stage.label}: Click to filter transactions`}
            >
              {/* Header Label and Statutory Operator */}
              <div className="flex items-center justify-between gap-1 mb-1 text-[10px] font-mono">
                <span className={`font-semibold truncate ${stage.color.text}`}>
                  {isDeduction && "− "}
                  {isResult && "= "}
                  {stage.shortLabel}
                </span>
                {stage.rateLabel && (
                  <span
                    className={`text-[9px] px-1 py-0.2 rounded border font-mono font-medium ${stage.color.badgeBg}`}
                  >
                    {stage.rateLabel}
                  </span>
                )}
              </div>

              {/* Absolute Rupee Value */}
              <div
                className={`text-sm sm:text-base font-bold font-mono font-tabular tracking-tight ${stage.color.text}`}
              >
                {stage.formattedAmount}
              </div>

              {/* Metadata: Percent of Gross & Count */}
              <div className="mt-1.5 flex items-center justify-between text-[10px] text-neutral-400 font-mono pt-1 border-t border-white/5">
                <span>{stage.percentageOfGross.toFixed(1)}% gross</span>
                <span className="truncate">{stage.transactionCount} txns</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Horizontal Stacked Waterfall Bar with Proportional Fintech Color Segments */}
      <div className="space-y-1.5 pt-1">
        <div className="flex items-center justify-between text-[10px] font-mono text-neutral-400">
          <div className="flex items-center gap-1.5">
            <Layers className="w-3 h-3 text-neutral-500" />
            <span>Settlement Capital Conservation Bar</span>
          </div>
          <div className="text-[10px] text-neutral-400 font-mono hidden sm:flex items-center gap-3">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              Net Bank ({( (breakdown.netBankAmount / (breakdown.grossAmount || 1)) * 100 ).toFixed(1)}%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
              MDR Fees ({( (breakdown.mdrFeeAmount / (breakdown.grossAmount || 1)) * 100 ).toFixed(1)}%)
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-500"></span>
              GST ({( (breakdown.gstTaxAmount / (breakdown.grossAmount || 1)) * 100 ).toFixed(1)}%)
            </span>
            {breakdown.tdsAmount > 0 && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-violet-500"></span>
                1% TDS ({( (breakdown.tdsAmount / (breakdown.grossAmount || 1)) * 100 ).toFixed(1)}%)
              </span>
            )}
          </div>
        </div>

        {/* Stacked Proportional Bar */}
        <div
          className="w-full bg-[#0c0e12] rounded h-3.5 flex overflow-hidden p-0.5 border border-[#1e222d] gap-0.5"
          role="progressbar"
          aria-label="Settlement capital conservation distribution"
        >
          {stackedSlices.map(({ stage, widthPct, barColor }) => {
            const active = isStageActive(stage);
            return (
              <div
                key={stage.id}
                style={{ width: `${widthPct}%` }}
                onClick={() => handleStageClick(stage)}
                onMouseEnter={() => setHoveredStageId(stage.id)}
                onMouseLeave={() => setHoveredStageId(null)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleStageClick(stage);
                  }
                }}
                className={`${barColor} transition-all rounded-xs cursor-pointer relative ${
                  active ? "ring-2 ring-white" : ""
                }`}
                aria-label={`${stage.label}: ${stage.formattedAmount}`}
              />
            );
          })}
        </div>
      </div>

      {/* Interactive Tooltip Card on Hover / Selection */}
      {hoveredStage && (
        <div className="bg-[#12151c] border border-indigo-900/50 rounded-md p-2.5 flex flex-col sm:flex-row items-start sm:items-center justify-between text-xs font-sans gap-2 animate-in fade-in duration-150">
          <div className="flex items-center gap-2.5">
            <div className="w-2 h-2 rounded-full shrink-0 bg-indigo-400" />
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-neutral-100">
                  {hoveredStage.label}
                </span>
                {hoveredStage.rateLabel && (
                  <span className="text-[10px] font-mono px-1 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                    {hoveredStage.rateLabel}
                  </span>
                )}
                <span className="text-neutral-400 font-mono text-[11px]">
                  • {hoveredStage.percentageOfGross.toFixed(2)}% of Gross GMV
                </span>
              </div>
              <p className="text-[11px] text-neutral-400 mt-0.5">
                {hoveredStage.description}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 self-end sm:self-center shrink-0">
            <div className="text-right">
              <div className="text-sm font-bold font-mono text-neutral-100">
                {hoveredStage.formattedAmount}
              </div>
              <div className="text-[10px] text-neutral-400 font-mono">
                {hoveredStage.transactionCount} transactions impacted
              </div>
            </div>
            <button
              onClick={() => handleStageClick(hoveredStage)}
              className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-medium rounded flex items-center gap-1 transition cursor-pointer"
            >
              <Filter className="w-3 h-3" />
              <span>Filter</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
