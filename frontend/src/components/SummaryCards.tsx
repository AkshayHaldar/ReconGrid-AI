import React from "react";
import {
  ArrowUpRight,
  CheckCircle,
  Clock,
  ShieldAlert,
  Scale,
  Sparkles,
  Layers,
  AlertTriangle,
} from "lucide-react";
import { ReconciliationStatus } from "@/lib/types";
import { formatINR } from "@/lib/formatters";

interface SummaryCardsProps {
  status: ReconciliationStatus | null;
  onOpenUpload: () => void;
  onFilterTab: (tab: string) => void;
}

export const SummaryCards: React.FC<SummaryCardsProps> = ({
  status,
  onOpenUpload,
  onFilterTab,
}) => {
  if (!status || status.total_records === 0) {
    return (
      <div className="bg-[#0f1624] border border-[#1c2b42] rounded-lg p-6 mb-4 text-center">
        <div className="max-w-md mx-auto space-y-3">
          <div className="w-10 h-10 rounded bg-[#131d2e] border border-[#223552] flex items-center justify-center mx-auto text-blue-400">
            <ArrowUpRight className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-slate-100 font-sans">
            No bank statement loaded for this reconciliation cycle
          </h3>
          <p className="text-xs text-slate-400 font-sans">
            Upload an HDFC, ICICI, SBI, or Axis bank statement CSV, or click Sync/Seed to populate synthetic transactions.
          </p>
          <div className="pt-2 flex justify-center gap-2.5">
            <button
              onClick={onOpenUpload}
              className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-medium transition shadow-sm"
            >
              Upload Bank Statement CSV
            </button>
          </div>
        </div>
      </div>
    );
  }

  const matchRate = status.match_rate_percentage || 0;
  const isHealthy = matchRate >= 90;
  const totalReviewItems = (status.suggested_count || 0) + (status.conflict_count || 0);

  return (
    <div className="space-y-2 sm:space-y-2.5 mb-3 sm:mb-4">
      {/* 4-Column Accounting Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-2.5">
        {/* Metric 1: Total Ingested */}
        <div className="bg-[#0f1624] border border-[#1c2b42] rounded p-2.5 sm:p-3 shadow-sm hover:border-[#2a3d5e] transition">
          <div className="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-400 mb-1 font-medium font-sans">
            <span>TOTAL INGESTED LEDGER</span>
            <span className="text-[9px] sm:text-[10px] font-mono text-slate-400 bg-[#131b2c] px-1.5 py-0.2 rounded border border-[#1e2d44]">
              {status.total_records} rows
            </span>
          </div>
          <div className="text-base sm:text-lg font-bold font-mono text-slate-100 tracking-tight font-tabular">
            {formatINR(status.total_ingested_amount)}
          </div>
          <div className="mt-1 sm:mt-1.5 text-[9px] sm:text-[10px] text-slate-400 flex items-center justify-between font-mono">
            <span className="flex items-center gap-1 text-slate-400">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400"></span>
              Bank Statement Flow
            </span>
            <span className="text-slate-500">100% Ingested</span>
          </div>
        </div>

        {/* Metric 2: Auto-Reconciled */}
        <div
          onClick={() => onFilterTab("MATCHED")}
          className="bg-[#0f1624] border border-[#1c2b42] rounded p-2.5 sm:p-3 shadow-sm hover:border-emerald-700/60 cursor-pointer transition"
        >
          <div className="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-400 mb-1 font-medium font-sans">
            <span>AUTO-RECONCILED NET</span>
            <div className="flex items-center text-emerald-400 text-[9px] sm:text-[10px] gap-1 font-mono">
              <CheckCircle className="w-3 h-3" />
              <span>{status.matched_count} txns</span>
            </div>
          </div>
          <div className="flex items-baseline gap-1.5 sm:gap-2">
            <span
              className={`text-base sm:text-lg font-bold font-mono font-tabular ${
                isHealthy ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {matchRate.toFixed(1)}%
            </span>
            <span className="text-[10px] sm:text-[11px] font-mono text-slate-400 font-tabular truncate">
              ({formatINR(status.total_reconciled_amount)})
            </span>
          </div>
          {/* Subtle Progress Bar */}
          <div className="mt-1.5 sm:mt-2 w-full bg-[#141e30] rounded-full h-1 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                isHealthy ? "bg-emerald-500" : "bg-amber-500"
              }`}
              style={{ width: `${Math.min(matchRate, 100)}%` }}
            />
          </div>
        </div>

        {/* Metric 3: Suggested & Conflict Review */}
        <div
          onClick={() => onFilterTab(status.conflict_count > 0 ? "CONFLICT" : "SUGGESTED")}
          className="bg-[#0f1624] border border-[#1c2b42] rounded p-2.5 sm:p-3 shadow-sm hover:border-sky-700/60 cursor-pointer transition"
        >
          <div className="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-400 mb-1 font-medium font-sans">
            <span>CA REVIEW REQUIRED</span>
            {totalReviewItems > 0 && (
              <span className="px-1.5 py-0.2 rounded bg-[#10243e] text-sky-300 border border-[#1b4372] text-[9px] sm:text-[10px] font-mono">
                {status.conflict_count > 0 ? `${status.conflict_count} Conflict` : "Needs Review"}
              </span>
            )}
          </div>
          <div className="text-base sm:text-lg font-bold font-mono text-sky-300 font-tabular">
            {totalReviewItems}{" "}
            <span className="text-[10px] sm:text-xs font-normal text-slate-400 font-sans">
              ({status.suggested_count} sugg, {status.conflict_count} confl)
            </span>
          </div>
          <div className="mt-1 sm:mt-1.5 text-[9px] sm:text-[10px] text-sky-400/80 flex items-center gap-1 font-mono">
            <Clock className="w-3 h-3" />
            <span>Single-click Approve & Resolve →</span>
          </div>
        </div>

        {/* Metric 4: Unresolved Exceptions */}
        <div
          onClick={() => onFilterTab("EXCEPTION")}
          className="bg-[#0f1624] border border-[#1c2b42] rounded p-2.5 sm:p-3 shadow-sm hover:border-rose-700/60 cursor-pointer transition"
        >
          <div className="flex items-center justify-between text-[10px] sm:text-[11px] text-slate-400 mb-1 font-medium font-sans">
            <span>UNRESOLVED VARIANCE</span>
            <span className="flex items-center text-rose-400 text-[9px] sm:text-[10px] font-mono gap-1">
              <ShieldAlert className="w-3 h-3" />
              {status.exception_count} txns
            </span>
          </div>
          <div className="text-base sm:text-lg font-bold font-mono text-rose-400 font-tabular">
            {formatINR(status.total_exception_amount)}
          </div>
          <div className="mt-1 sm:mt-1.5 text-[9px] sm:text-[10px] text-rose-400/80 flex items-center gap-1 font-mono">
            <AlertTriangle className="w-3 h-3" />
            <span>Auditable exception ledger →</span>
          </div>
        </div>
      </div>

      {/* Trial Balance Reconciliation Status Strip */}
      <div className="bg-[#0b111c] border border-[#18253a] rounded px-2.5 sm:px-3 py-1.5 flex flex-col md:flex-row items-start md:items-center justify-between text-[10px] sm:text-[11px] text-slate-400 font-mono gap-1.5 sm:gap-2">
        <div className="flex items-start sm:items-center gap-2">
          <Scale className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5 sm:mt-0" />
          <span className="leading-snug">
            <strong className="text-slate-200">Reconciliation Control:</strong>{" "}
            Ingested ({formatINR(status.total_ingested_amount)}) = Reconciled ({formatINR(status.total_reconciled_amount)}) + Exceptions ({formatINR(status.total_exception_amount)})
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[9px] sm:text-[10px] shrink-0 self-end md:self-auto">
          {status.exception_count === 0 ? (
            <span className="text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/60 flex items-center gap-1">
              <CheckCircle className="w-3 h-3" />
              Trial Balance In-Balance (₹0.00 Variance)
            </span>
          ) : (
            <span className="text-amber-400 bg-amber-950/40 px-2 py-0.5 rounded border border-amber-800/50 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Variance Pending CA Audit: {formatINR(status.total_exception_amount)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
