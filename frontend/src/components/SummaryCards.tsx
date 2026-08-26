import React from "react";
import { ArrowUpRight, CheckCircle, AlertCircle, Clock, ShieldAlert } from "lucide-react";
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
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-6 mb-6 text-center backdrop-blur">
        <div className="max-w-md mx-auto space-y-3">
          <div className="w-10 h-10 rounded-full bg-blue-900/40 border border-blue-600/30 flex items-center justify-center mx-auto text-blue-400">
            <ArrowUpRight className="w-5 h-5" />
          </div>
          <h3 className="text-base font-semibold text-slate-200">
            No bank statement loaded for this reconciliation cycle
          </h3>
          <p className="text-xs text-slate-400">
            Upload an HDFC, ICICI, SBI, or Axis bank statement CSV to run deterministic multi-tier reconciliation.
          </p>
          <div className="pt-2 flex justify-center gap-3">
            <button
              onClick={onOpenUpload}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-medium shadow-md transition"
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

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6">
      {/* Total Ingested */}
      <div className="bg-[#0e1524] border border-[#1e2a3f] rounded-lg p-3.5 shadow-sm hover:border-slate-700 transition">
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1 font-medium">
          <span>TOTAL INGESTED</span>
          <span className="text-[11px] font-mono text-slate-500">{status.total_records} rows</span>
        </div>
        <div className="text-xl font-bold font-mono text-slate-100 tracking-tight">
          {formatINR(status.total_ingested_amount)}
        </div>
        <div className="mt-2 text-[11px] text-slate-400 flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-blue-500"></span>
          Bank statement ledger total
        </div>
      </div>

      {/* Auto-Reconciled */}
      <div
        onClick={() => onFilterTab("MATCHED")}
        className="bg-[#0e1524] border border-[#1e2a3f] rounded-lg p-3.5 shadow-sm hover:border-emerald-700/60 cursor-pointer transition"
      >
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1 font-medium">
          <span>AUTO-RECONCILED</span>
          <div className="flex items-center text-emerald-400 text-xs gap-1 font-mono">
            <CheckCircle className="w-3.5 h-3.5" />
            <span>{status.matched_count} txns</span>
          </div>
        </div>
        <div className="flex items-baseline gap-2">
          <span className={`text-xl font-bold font-mono ${isHealthy ? "text-emerald-400" : "text-amber-400"}`}>
            {matchRate.toFixed(1)}%
          </span>
          <span className="text-xs font-mono text-slate-400">
            ({formatINR(status.total_reconciled_amount)})
          </span>
        </div>
        {/* Progress Bar */}
        <div className="mt-2 w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${isHealthy ? "bg-emerald-500" : "bg-amber-500"}`}
            style={{ width: `${Math.min(matchRate, 100)}%` }}
          />
        </div>
      </div>

      {/* Suggested Matches */}
      <div
        onClick={() => onFilterTab("SUGGESTED")}
        className="bg-[#0e1524] border border-[#1e2a3f] rounded-lg p-3.5 shadow-sm hover:border-sky-700/60 cursor-pointer transition"
      >
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1 font-medium">
          <span>SUGGESTED MATCHES</span>
          {status.suggested_count > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800 text-[10px] font-mono animate-pulse">
              Needs Review
            </span>
          )}
        </div>
        <div className="text-xl font-bold font-mono text-sky-300">
          {status.suggested_count}{" "}
          <span className="text-xs font-normal text-slate-400 font-sans">txns pending CA</span>
        </div>
        <div className="mt-2 text-[11px] text-sky-400/80 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          Single-click inline approve / deny
        </div>
      </div>

      {/* Exceptions */}
      <div
        onClick={() => onFilterTab("EXCEPTION")}
        className="bg-[#0e1524] border border-[#1e2a3f] rounded-lg p-3.5 shadow-sm hover:border-rose-700/60 cursor-pointer transition"
      >
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1 font-medium">
          <span>UNRESOLVED EXCEPTIONS</span>
          <span className="flex items-center text-rose-400 text-xs font-mono gap-1">
            <ShieldAlert className="w-3.5 h-3.5" />
            {status.exception_count} txns
          </span>
        </div>
        <div className="text-xl font-bold font-mono text-rose-400">
          {formatINR(status.total_exception_amount)}
        </div>
        <div className="mt-2 text-[11px] text-rose-400/80 flex items-center gap-1">
          <AlertCircle className="w-3 h-3" />
          Honest audit list with reason codes
        </div>
      </div>
    </div>
  );
};
