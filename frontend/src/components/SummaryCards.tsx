import React, { useState } from "react";
import {
  ArrowUpRight,
  CheckCircle,
  Clock,
  ShieldAlert,
  Scale,
  Layers,
  AlertTriangle,
  TrendingUp,
  Percent,
  CheckCircle2,
  HelpCircle,
  ArrowDownLeft,
  DollarSign,
  Info,
  Zap,
} from "lucide-react";
import { DiagnosticType, ReconciliationRecordItem, ReconciliationStatus } from "@/lib/types";
import { formatINR } from "@/lib/formatters";
import { FeeWaterfallBar } from "./FeeWaterfallBar";

interface SummaryCardsProps {
  status: ReconciliationStatus | null;
  records?: ReconciliationRecordItem[];
  activeDiagnostic?: DiagnosticType | "ALL" | string;
  activeTab?: string;
  onOpenUpload: () => void;
  onOpenSync?: () => void;
  onFilterTab: (tab: string) => void;
  onSelectDiagnostic?: (diagnostic: DiagnosticType | "ALL") => void;
}

export const SummaryCards: React.FC<SummaryCardsProps> = ({
  status,
  records = [],
  activeDiagnostic = "ALL",
  activeTab = "ALL",
  onOpenUpload,
  onOpenSync,
  onFilterTab,
  onSelectDiagnostic,
}) => {
  const [hoveredSegment, setHoveredSegment] = useState<string | null>(null);

  if (!status || status.total_records === 0) {
    return (
      <div className="fin-card rounded-xl p-8 mb-4 text-center shadow-xs border border-[#1e222d]">
        <div className="max-w-lg mx-auto space-y-4">
          <div className="w-11 h-11 rounded-lg bg-neutral-800 border border-neutral-700 flex items-center justify-center mx-auto text-neutral-300">
            <ArrowUpRight className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-neutral-100 font-sans">
              No bank statement loaded for this reconciliation cycle
            </h3>
            <p className="text-xs text-neutral-400 font-sans leading-relaxed">
              Upload an HDFC, ICICI, SBI, or Axis bank statement CSV/PDF, or click <strong className="text-neutral-300 font-medium">Seed Test Data</strong> below to populate golden test records.
            </p>
          </div>
          <div className="pt-2 flex flex-wrap justify-center gap-2.5">
            <button
              onClick={onOpenUpload}
              className="px-3.5 py-1.5 bg-neutral-100 hover:bg-white text-neutral-900 rounded-md text-xs font-semibold shadow-xs transition transform active:scale-98 cursor-pointer"
            >
              Upload Bank Statement
            </button>
            {onOpenSync && (
              <button
                onClick={onOpenSync}
                className="px-3.5 py-1.5 bg-[#151820] hover:bg-[#1c202b] border border-[#282e3d] text-neutral-300 hover:text-white rounded-md text-xs font-medium transition transform active:scale-98 cursor-pointer flex items-center gap-1.5"
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Seed Test Data</span>
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const matchRate = status.match_rate_percentage || 0;
  const isHealthy = matchRate >= 90;
  const totalReviewItems = (status.suggested_count || 0) + (status.conflict_count || 0);
  const pendingItems = status.pending_count || 0;

  // Segment percentages for visual distribution bar
  const totalRecs = status.total_records || 1;
  const matchedPct = ((status.matched_count || 0) / totalRecs) * 100;
  const suggestedPct = ((status.suggested_count || 0) / totalRecs) * 100;
  const conflictPct = ((status.conflict_count || 0) / totalRecs) * 100;
  const exceptionPct = ((status.exception_count || 0) / totalRecs) * 100;
  const pendingPct = (pendingItems / totalRecs) * 100;

  // Numerical helpers for variance
  const totalVarianceAmount =
    status.total_unresolved_variance !== undefined
      ? status.total_unresolved_variance
      : status.total_exception_amount;

  const totalCreditAmt = status.total_credit_amount || status.total_ingested_amount;
  const totalDebitAmt = status.total_debit_amount || "0.00";
  const hasDebits = parseFloat(totalDebitAmt) > 0;
  const netIngested = status.net_ingested_amount || status.total_ingested_amount;

  const isInBalance =
    status.is_in_balance ??
    (status.exception_count === 0 &&
      status.suggested_count === 0 &&
      status.conflict_count === 0 &&
      pendingItems === 0);

  return (
    <div className="space-y-2.5 mb-4">
      {/* 4-Column Executive Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {/* Metric 1: Total Ingested Ledger */}
        <div
          onClick={() => onFilterTab("ALL")}
          className="fin-card fin-card-hover rounded-lg p-3.5 shadow-xs cursor-pointer group transition-all"
          role="button"
          tabIndex={0}
          aria-label="Filter by All Ingested Records"
        >
          <div className="flex items-center justify-between text-[11px] text-neutral-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide text-neutral-400 group-hover:text-neutral-200 transition-colors flex items-center gap-1.5">
              <span>TOTAL INGESTED LEDGER</span>
            </span>
            <span className="text-[10px] font-mono text-neutral-300 bg-neutral-900 px-2 py-0.5 rounded border border-neutral-800 font-tabular font-medium">
              {status.total_records} txns
            </span>
          </div>

          <div className="text-lg sm:text-xl font-bold font-mono text-neutral-100 tracking-tight font-tabular">
            {formatINR(status.total_ingested_amount)}
          </div>

          {/* Gross Cash Flow Breakdown */}
          <div className="mt-1.5 flex items-center justify-between text-[10px] font-mono text-neutral-400 font-tabular">
            <span className="text-emerald-400 font-medium">
              +{formatINR(totalCreditAmt)} Cr
            </span>
            {hasDebits && (
              <span className="text-rose-400 font-medium">
                -{formatINR(totalDebitAmt)} Dr
              </span>
            )}
            <span className="text-neutral-300 font-medium">
              Net: {formatINR(netIngested)}
            </span>
          </div>

          <div className="mt-2 text-[10px] text-neutral-400 flex items-center justify-between font-mono pt-1.5 border-t border-[#1e222d]">
            <span className="flex items-center gap-1.5 text-neutral-300">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-neutral-400"></span>
              <span>100% Ingested & Parsed</span>
            </span>
            <span className="text-neutral-500 group-hover:text-neutral-300 transition-colors">
              View All &rarr;
            </span>
          </div>
        </div>

        {/* Metric 2: Auto-Reconciled Net */}
        <div
          onClick={() => onFilterTab("MATCHED")}
          className="fin-card fin-card-hover rounded-lg p-3.5 shadow-xs cursor-pointer group transition-all"
          role="button"
          tabIndex={0}
          aria-label="Filter by Matched Records"
        >
          <div className="flex items-center justify-between text-[11px] text-neutral-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide text-neutral-400 group-hover:text-emerald-300 transition-colors">
              AUTO-RECONCILED NET
            </span>
            <div className="flex items-center text-emerald-400 text-[10px] gap-1 font-mono bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/60 font-medium">
              <CheckCircle className="w-3 h-3" />
              <span>{status.matched_count} txns</span>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={`text-lg sm:text-xl font-bold font-mono font-tabular ${
                isHealthy ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {matchRate.toFixed(1)}%
            </span>
            <span className="text-[11px] font-mono text-neutral-400 font-tabular truncate">
              ({formatINR(status.total_reconciled_amount)})
            </span>
          </div>
          {/* Progress Bar */}
          <div className="mt-2.5 w-full bg-neutral-800 rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                isHealthy ? "bg-emerald-400" : "bg-amber-400"
              }`}
              style={{ width: `${Math.min(matchRate, 100)}%` }}
            />
          </div>
          <div className="mt-2 text-[10px] text-neutral-400 flex items-center justify-between font-mono pt-1.5 border-t border-[#1e222d]">
            <span className="flex items-center gap-1 text-emerald-400/90">
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span>Zero Delta Variance</span>
            </span>
            <span className="text-neutral-500 group-hover:text-emerald-300 transition-colors">
              Matched &rarr;
            </span>
          </div>
        </div>

        {/* Metric 3: Suggested & Conflict Review */}
        <div
          onClick={() =>
            onFilterTab(status.conflict_count > 0 ? "CONFLICT" : "SUGGESTED")
          }
          className="fin-card fin-card-hover rounded-lg p-3.5 shadow-xs cursor-pointer group transition-all"
          role="button"
          tabIndex={0}
          aria-label="Filter by Review Required"
        >
          <div className="flex items-center justify-between text-[11px] text-neutral-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide text-neutral-400 group-hover:text-sky-300 transition-colors">
              CA REVIEW REQUIRED
            </span>
            {totalReviewItems > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-sky-950/60 text-sky-300 border border-sky-800/60 text-[10px] font-mono font-medium">
                {status.conflict_count > 0
                  ? `${status.conflict_count} Conflicts`
                  : `${status.suggested_count} Suggested`}
              </span>
            )}
          </div>
          <div className="text-lg sm:text-xl font-bold font-mono text-sky-300 font-tabular flex items-baseline gap-1.5">
            {totalReviewItems}
            <span className="text-[11px] font-normal text-neutral-400 font-sans">
              ({status.suggested_count} suggested, {status.conflict_count} conflict)
            </span>
          </div>
          <div className="mt-2 text-[10px] text-neutral-400 flex items-center justify-between font-mono pt-1.5 border-t border-[#1e222d]">
            <span className="flex items-center gap-1 text-sky-400/90">
              <Clock className="w-3 h-3 text-sky-400" />
              <span>1-Click Approve & Resolve</span>
            </span>
            <span className="text-neutral-500 group-hover:text-sky-300 transition-colors">
              Review &rarr;
            </span>
          </div>
        </div>

        {/* Metric 4: Unresolved Variance */}
        <div
          onClick={() => onFilterTab("EXCEPTION")}
          className="fin-card fin-card-hover rounded-lg p-3.5 shadow-xs cursor-pointer group transition-all"
          role="button"
          tabIndex={0}
          aria-label="Filter by Exceptions & Unresolved Variance"
        >
          <div className="flex items-center justify-between text-[11px] text-neutral-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide text-neutral-400 group-hover:text-rose-300 transition-colors">
              UNRESOLVED VARIANCE
            </span>
            <span className="flex items-center text-rose-400 text-[10px] font-mono gap-1 bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-800/60 font-medium">
              <ShieldAlert className="w-3 h-3" />
              {status.exception_count} txns
            </span>
          </div>
          <div className="text-lg sm:text-xl font-bold font-mono text-rose-400 font-tabular">
            {formatINR(totalVarianceAmount)}
          </div>
          <div className="mt-2 text-[10px] text-neutral-400 flex items-center justify-between font-mono pt-1.5 border-t border-[#1e222d]">
            <span className="flex items-center gap-1 truncate max-w-[200px] text-rose-400/90">
              <AlertTriangle className="w-3 h-3 text-rose-400 shrink-0" />
              <span>
                {status.exception_count > 0
                  ? "Audit Exceptions & Unmatched"
                  : "All Exceptions Cleared"}
              </span>
            </span>
            <span className="text-neutral-500 group-hover:text-rose-300 transition-colors">
              Audit &rarr;
            </span>
          </div>
        </div>
      </div>

      {/* Visual Fee & Tax Waterfall Breakdown Bar for Settlement Deductions */}
      <FeeWaterfallBar
        records={records}
        status={status}
        activeDiagnostic={activeDiagnostic}
        activeTab={activeTab}
        onSelectDiagnostic={onSelectDiagnostic}
        onFilterTab={onFilterTab}
      />

      {/* Visual Ledger Distribution Bar */}
      <div className="fin-card rounded-lg p-3 shadow-xs space-y-2">
        <div className="flex flex-wrap items-center justify-between text-[10px] sm:text-[11px] font-mono text-neutral-400 gap-2">
          <div className="flex items-center gap-2">
            <Layers className="w-3.5 h-3.5 text-neutral-400" />
            <span className="font-medium text-neutral-200">
              Ledger Composition & Distribution
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2.5 sm:gap-3">
            <button
              onClick={() => onFilterTab("MATCHED")}
              className="flex items-center gap-1 hover:text-emerald-300 transition-colors cursor-pointer"
            >
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span>Matched ({matchedPct.toFixed(0)}%)</span>
            </button>
            <button
              onClick={() => onFilterTab("SUGGESTED")}
              className="flex items-center gap-1 hover:text-sky-300 transition-colors cursor-pointer"
            >
              <span className="w-2 h-2 rounded-full bg-sky-500"></span>
              <span>Suggested ({suggestedPct.toFixed(0)}%)</span>
            </button>
            {status.conflict_count > 0 && (
              <button
                onClick={() => onFilterTab("CONFLICT")}
                className="flex items-center gap-1 hover:text-amber-300 transition-colors cursor-pointer"
              >
                <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                <span>Conflicts ({conflictPct.toFixed(0)}%)</span>
              </button>
            )}
            {pendingItems > 0 && (
              <button
                onClick={() => onFilterTab("PENDING_SETTLEMENT_DATA")}
                className="flex items-center gap-1 hover:text-purple-300 transition-colors cursor-pointer"
              >
                <span className="w-2 h-2 rounded-full bg-purple-500"></span>
                <span>In-Transit ({pendingPct.toFixed(0)}%)</span>
              </button>
            )}
            <button
              onClick={() => onFilterTab("EXCEPTION")}
              className="flex items-center gap-1 hover:text-rose-300 transition-colors cursor-pointer"
            >
              <span className="w-2 h-2 rounded-full bg-rose-500"></span>
              <span>Exceptions ({exceptionPct.toFixed(0)}%)</span>
            </button>
          </div>
        </div>

        {/* Multi-Segment Bar */}
        <div className="w-full bg-[#0c0e12] rounded h-2 flex overflow-hidden p-0.5 border border-[#1e222d] gap-0.5">
          {matchedPct > 0 && (
            <div
              style={{ width: `${matchedPct}%` }}
              className="bg-emerald-500 hover:bg-emerald-400 transition-all rounded-xs cursor-pointer"
              title={`Matched: ${status.matched_count} txns (${formatINR(status.total_reconciled_amount)})`}
              onClick={() => onFilterTab("MATCHED")}
            />
          )}
          {suggestedPct > 0 && (
            <div
              style={{ width: `${suggestedPct}%` }}
              className="bg-sky-500 hover:bg-sky-400 transition-all rounded-xs cursor-pointer"
              title={`Suggested: ${status.suggested_count} txns`}
              onClick={() => onFilterTab("SUGGESTED")}
            />
          )}
          {conflictPct > 0 && (
            <div
              style={{ width: `${conflictPct}%` }}
              className="bg-amber-500 hover:bg-amber-400 transition-all rounded-xs cursor-pointer"
              title={`Conflicts: ${status.conflict_count} txns`}
              onClick={() => onFilterTab("CONFLICT")}
            />
          )}
          {pendingPct > 0 && (
            <div
              style={{ width: `${pendingPct}%` }}
              className="bg-purple-500 hover:bg-purple-400 transition-all rounded-xs cursor-pointer"
              title={`In-Transit: ${pendingItems} txns (${formatINR(status.total_pending_amount || "0")})`}
              onClick={() => onFilterTab("PENDING_SETTLEMENT_DATA")}
            />
          )}
          {exceptionPct > 0 && (
            <div
              style={{ width: `${exceptionPct}%` }}
              className="bg-rose-500 hover:bg-rose-400 transition-all rounded-xs cursor-pointer"
              title={`Exceptions: ${status.exception_count} txns (${formatINR(status.total_exception_amount)})`}
              onClick={() => onFilterTab("EXCEPTION")}
            />
          )}
        </div>
      </div>

      {/* Trial Balance Reconciliation Control Strip */}
      <div className="bg-[#111318] border border-[#1e222d] rounded-lg px-3.5 py-2 flex flex-col md:flex-row items-start md:items-center justify-between text-[11px] text-neutral-400 font-mono gap-2 shadow-xs">
        <div className="flex items-center gap-2 flex-wrap">
          <Scale className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
          <span className="leading-snug">
            <strong className="text-neutral-200">Reconciliation Control:</strong>{" "}
            Ingested ({formatINR(status.total_ingested_amount)}) = Reconciled ({formatINR(status.total_reconciled_amount)})
            {totalReviewItems > 0 && (
              <span> + Review Pending ({totalReviewItems} txns)</span>
            )}
            {pendingItems > 0 && (
              <span> + In-Transit ({formatINR(status.total_pending_amount || "0")})</span>
            )}
            <span> + Exceptions ({formatINR(status.total_exception_amount)})</span>
          </span>
        </div>

        <div className="flex items-center gap-2 text-[10px] shrink-0 self-end md:self-auto">
          {isInBalance ? (
            <span className="text-emerald-300 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/60 flex items-center gap-1.5 font-medium">
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span>Trial Balance In-Balance (₹0.00 Variance)</span>
            </span>
          ) : (
            <span className="text-amber-300 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-800/60 flex items-center gap-1.5 font-medium">
              <AlertTriangle className="w-3 h-3 text-amber-400" />
              <span>Variance Pending CA Audit: {formatINR(totalVarianceAmount)}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
