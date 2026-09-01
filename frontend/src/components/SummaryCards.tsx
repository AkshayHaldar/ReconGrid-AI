import React, { useState } from "react";
import {
  ArrowUpRight,
  CheckCircle,
  Clock,
  ShieldAlert,
  Scale,
  Sparkles,
  Layers,
  AlertTriangle,
  TrendingUp,
  Percent,
  CheckCircle2,
  HelpCircle,
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
  const [hoveredSegment, setHoveredSegment] = useState<string | null>(null);

  if (!status || status.total_records === 0) {
    return (
      <div className="fin-card rounded-xl p-8 mb-4 text-center shadow-lg border border-[#162438]">
        <div className="max-w-lg mx-auto space-y-4">
          <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400 shadow-inner">
            <ArrowUpRight className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-base font-bold text-slate-100 font-sans">
              No bank statement loaded for this reconciliation cycle
            </h3>
            <p className="text-xs text-slate-400 font-sans leading-relaxed">
              Upload an HDFC, ICICI, SBI, or Axis bank statement CSV/PDF, or click <strong className="text-slate-300">Sync/Seed</strong> in the top bar to generate synthetic golden test records.
            </p>
          </div>
          <div className="pt-2 flex justify-center gap-3">
            <button
              onClick={onOpenUpload}
              className="px-4 py-2 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white rounded-lg text-xs font-semibold shadow-md shadow-blue-500/20 transition transform active:scale-98"
            >
              Upload Bank Statement
            </button>
          </div>
        </div>
      </div>
    );
  }

  const matchRate = status.match_rate_percentage || 0;
  const isHealthy = matchRate >= 90;
  const totalReviewItems = (status.suggested_count || 0) + (status.conflict_count || 0);

  // Segment percentages for visual distribution bar
  const totalRecs = status.total_records || 1;
  const matchedPct = ((status.matched_count || 0) / totalRecs) * 100;
  const suggestedPct = ((status.suggested_count || 0) / totalRecs) * 100;
  const conflictPct = ((status.conflict_count || 0) / totalRecs) * 100;
  const exceptionPct = ((status.exception_count || 0) / totalRecs) * 100;

  return (
    <div className="space-y-3 mb-4">
      {/* 4-Column Executive Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {/* Metric 1: Total Ingested */}
        <div className="fin-card fin-card-hover rounded-xl p-3.5 shadow-sm">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide">TOTAL INGESTED LEDGER</span>
            <span className="text-[10px] font-mono text-slate-400 bg-[#0e1628] px-2 py-0.5 rounded border border-[#18263c]">
              {status.total_records} txns
            </span>
          </div>
          <div className="text-lg sm:text-xl font-bold font-mono text-slate-100 tracking-tight font-tabular">
            {formatINR(status.total_ingested_amount)}
          </div>
          <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between font-mono pt-1.5 border-t border-[#131d2f]">
            <span className="flex items-center gap-1.5 text-slate-300">
              <span className="inline-block w-2 h-2 rounded-full bg-blue-400"></span>
              Bank Statement Flow
            </span>
            <span className="text-slate-500 font-semibold">100% Ingested</span>
          </div>
        </div>

        {/* Metric 2: Auto-Reconciled Net */}
        <div
          onClick={() => onFilterTab("MATCHED")}
          className="fin-card fin-card-hover rounded-xl p-3.5 shadow-sm hover:border-emerald-500/50 cursor-pointer group"
          role="button"
          tabIndex={0}
          aria-label="Filter by Matched Records"
        >
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide group-hover:text-emerald-300 transition-colors">
              AUTO-RECONCILED NET
            </span>
            <div className="flex items-center text-emerald-400 text-[10px] gap-1 font-mono bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/60">
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
            <span className="text-[11px] font-mono text-slate-400 font-tabular truncate">
              ({formatINR(status.total_reconciled_amount)})
            </span>
          </div>
          {/* Subtle Progress Bar */}
          <div className="mt-2.5 w-full bg-[#101928] rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                isHealthy ? "bg-gradient-to-r from-emerald-500 to-teal-400" : "bg-gradient-to-r from-amber-500 to-yellow-400"
              }`}
              style={{ width: `${Math.min(matchRate, 100)}%` }}
            />
          </div>
        </div>

        {/* Metric 3: Suggested & Conflict Review */}
        <div
          onClick={() => onFilterTab(status.conflict_count > 0 ? "CONFLICT" : "SUGGESTED")}
          className="fin-card fin-card-hover rounded-xl p-3.5 shadow-sm hover:border-sky-500/50 cursor-pointer group"
          role="button"
          tabIndex={0}
          aria-label="Filter by Review Required"
        >
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide group-hover:text-sky-300 transition-colors">
              CA REVIEW REQUIRED
            </span>
            {totalReviewItems > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800 text-[10px] font-mono">
                {status.conflict_count > 0 ? `${status.conflict_count} Conflicts` : "Review"}
              </span>
            )}
          </div>
          <div className="text-lg sm:text-xl font-bold font-mono text-sky-300 font-tabular flex items-baseline gap-1.5">
            {totalReviewItems}
            <span className="text-[11px] font-normal text-slate-400 font-sans">
              ({status.suggested_count} suggested, {status.conflict_count} conflict)
            </span>
          </div>
          <div className="mt-2 text-[10px] text-sky-400/90 flex items-center justify-between font-mono pt-1.5 border-t border-[#131d2f]">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3 text-sky-400" />
              <span>1-Click Approve & Resolve</span>
            </span>
            <span className="text-slate-500 group-hover:text-sky-300 transition-colors">View &rarr;</span>
          </div>
        </div>

        {/* Metric 4: Unresolved Exceptions */}
        <div
          onClick={() => onFilterTab("EXCEPTION")}
          className="fin-card fin-card-hover rounded-xl p-3.5 shadow-sm hover:border-rose-500/50 cursor-pointer group"
          role="button"
          tabIndex={0}
          aria-label="Filter by Exceptions"
        >
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5 font-medium font-sans">
            <span className="tracking-wide group-hover:text-rose-300 transition-colors">
              UNRESOLVED VARIANCE
            </span>
            <span className="flex items-center text-rose-400 text-[10px] font-mono gap-1 bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-800/60">
              <ShieldAlert className="w-3 h-3" />
              {status.exception_count} txns
            </span>
          </div>
          <div className="text-lg sm:text-xl font-bold font-mono text-rose-400 font-tabular">
            {formatINR(status.total_exception_amount)}
          </div>
          <div className="mt-2 text-[10px] text-rose-400/90 flex items-center justify-between font-mono pt-1.5 border-t border-[#131d2f]">
            <span className="flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 text-rose-400" />
              <span>Auditable Exception Ledger</span>
            </span>
            <span className="text-slate-500 group-hover:text-rose-300 transition-colors">Audit &rarr;</span>
          </div>
        </div>
      </div>

      {/* Visual Ledger Distribution Bar */}
      <div className="fin-card rounded-xl p-3 shadow-sm space-y-2">
        <div className="flex items-center justify-between text-[10px] sm:text-[11px] font-mono text-slate-400">
          <div className="flex items-center gap-2">
            <Layers className="w-3.5 h-3.5 text-blue-400" />
            <span className="font-semibold text-slate-200">Ledger Composition & Distribution</span>
          </div>
          <div className="flex items-center gap-3">
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
        <div className="w-full bg-[#080d16] rounded-lg h-2.5 flex overflow-hidden p-0.5 border border-[#162337] gap-0.5">
          {matchedPct > 0 && (
            <div
              style={{ width: `${matchedPct}%` }}
              className="bg-emerald-500 hover:bg-emerald-400 transition-all rounded-sm cursor-pointer"
              title={`Matched: ${status.matched_count} txns (${formatINR(status.total_reconciled_amount)})`}
              onClick={() => onFilterTab("MATCHED")}
            />
          )}
          {suggestedPct > 0 && (
            <div
              style={{ width: `${suggestedPct}%` }}
              className="bg-sky-500 hover:bg-sky-400 transition-all rounded-sm cursor-pointer"
              title={`Suggested: ${status.suggested_count} txns`}
              onClick={() => onFilterTab("SUGGESTED")}
            />
          )}
          {conflictPct > 0 && (
            <div
              style={{ width: `${conflictPct}%` }}
              className="bg-amber-500 hover:bg-amber-400 transition-all rounded-sm cursor-pointer"
              title={`Conflicts: ${status.conflict_count} txns`}
              onClick={() => onFilterTab("CONFLICT")}
            />
          )}
          {exceptionPct > 0 && (
            <div
              style={{ width: `${exceptionPct}%` }}
              className="bg-rose-500 hover:bg-rose-400 transition-all rounded-sm cursor-pointer"
              title={`Exceptions: ${status.exception_count} txns (${formatINR(status.total_exception_amount)})`}
              onClick={() => onFilterTab("EXCEPTION")}
            />
          )}
        </div>
      </div>

      {/* Trial Balance Reconciliation Control Strip */}
      <div className="bg-[#080d17] border border-[#162438] rounded-xl px-3.5 py-2 flex flex-col md:flex-row items-start md:items-center justify-between text-[11px] text-slate-400 font-mono gap-2 shadow-xs">
        <div className="flex items-center gap-2">
          <Scale className="w-4 h-4 text-blue-400 shrink-0" />
          <span className="leading-snug">
            <strong className="text-slate-200">Reconciliation Control:</strong>{" "}
            Ingested ({formatINR(status.total_ingested_amount)}) = Reconciled ({formatINR(status.total_reconciled_amount)}) + Exceptions ({formatINR(status.total_exception_amount)})
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] shrink-0 self-end md:self-auto">
          {status.exception_count === 0 ? (
            <span className="text-emerald-300 bg-emerald-950/70 px-2.5 py-0.5 rounded-full border border-emerald-800/80 flex items-center gap-1.5 shadow-xs">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Trial Balance In-Balance (₹0.00 Variance)</span>
            </span>
          ) : (
            <span className="text-amber-300 bg-amber-950/50 px-2.5 py-0.5 rounded-full border border-amber-800/60 flex items-center gap-1.5 shadow-xs">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              <span>Variance Pending CA Audit: {formatINR(status.total_exception_amount)}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
