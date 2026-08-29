import React, { useState } from "react";
import {
  Check,
  X,
  Copy,
  CheckCheck,
  Split,
  Eye,
  ArrowDownRight,
  ArrowUpRight,
  ShieldAlert,
} from "lucide-react";
import { ReconciliationRecordItem } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/formatters";
import { StatusBadge } from "./StatusBadge";

interface ReconciliationTableProps {
  records: ReconciliationRecordItem[];
  highlightedRecordId: string | null;
  onApprove: (recordId: string) => void;
  onDeny: (recordId: string) => void;
  onOpenConflict: (record: ReconciliationRecordItem) => void;
  onOpenException: (record: ReconciliationRecordItem) => void;
  loading: boolean;
}

export const ReconciliationTable: React.FC<ReconciliationTableProps> = ({
  records,
  highlightedRecordId,
  onApprove,
  onDeny,
  onOpenConflict,
  onOpenException,
  loading,
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  if (loading && records.length === 0) {
    return (
      <div className="bg-[#0f1624] border border-[#1c2b42] rounded p-12 text-center text-slate-400">
        <div className="inline-block animate-spin rounded-full h-7 w-7 border-t-2 border-b-2 border-blue-500 mb-2.5"></div>
        <p className="text-xs font-mono">Running deterministic 4-tier reconciliation engine...</p>
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="bg-[#0f1624] border border-[#1c2b42] rounded p-12 text-center text-slate-400">
        <p className="text-xs font-mono">No reconciliation records match the selected filter criteria.</p>
      </div>
    );
  }

  return (
    <div className="bg-[#0f1624] border border-[#1c2b42] rounded overflow-hidden shadow-sm">
      <div className="overflow-x-auto max-h-[640px] overflow-y-auto touch-scroll">
        <table className="w-full text-left border-collapse text-xs min-w-[760px] sm:min-w-full">
          <thead className="sticky top-0 bg-[#0c121e] z-20 border-b border-[#1c2b42] text-slate-400 font-semibold uppercase tracking-wider text-[9px] sm:text-[10px]">
            <tr>
              <th className="py-2 px-2.5 sm:px-3 w-24">Date</th>
              <th className="py-2 px-2.5 sm:px-3 min-w-[200px] sm:min-w-[230px]">Bank UTR / Narrative</th>
              <th className="py-2 px-2.5 sm:px-3 text-right w-28 sm:w-32">Bank Amt</th>
              <th className="py-2 px-2.5 sm:px-3 w-36 sm:w-40">RZP Settlement ID</th>
              <th className="py-2 px-2.5 sm:px-3 text-right w-32 sm:w-36">RZP Net (Gross)</th>
              <th className="py-2 px-2.5 sm:px-3 text-right w-24 sm:w-28">Delta</th>
              <th className="py-2 px-2.5 sm:px-3 w-32 sm:w-36 text-center">Status & Diagnostic</th>
              <th className="py-2 px-2.5 sm:px-3 text-right w-20 sm:w-24">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#152236] font-sans">
            {records.map((r) => {
              const isHighlighted = highlightedRecordId === r.id;
              const isDebit = r.bank_direction === "DEBIT";
              const deltaNum = parseFloat(r.delta_amount || "0");
              const hasNonZeroDelta = deltaNum > 0;

              return (
                <tr
                  key={r.id}
                  id={`record-${r.id}`}
                  className={`hover:bg-[#131d2e] transition-colors duration-100 ${
                    isHighlighted ? "bg-blue-950/40 ring-1 ring-blue-500" : ""
                  } ${isDebit ? "bg-rose-950/15" : ""}`}
                >
                  {/* Date */}
                  <td className="py-2 px-2.5 sm:px-3 text-slate-300 font-mono whitespace-nowrap text-[10px] sm:text-[11px] font-tabular">
                    {formatDate(r.date)}
                  </td>

                  {/* Bank UTR & Description */}
                  <td className="py-2 px-2.5 sm:px-3">
                    <div className="flex flex-col">
                      {r.bank_utr ? (
                        <div className="flex items-center gap-1">
                          <span className="font-mono font-semibold text-slate-200 text-[10px] sm:text-[11px] tracking-tight">
                            {r.bank_utr}
                          </span>
                          <button
                            onClick={() => handleCopy(r.bank_utr || "", `utr-${r.id}`)}
                            className="text-slate-500 hover:text-slate-300 transition p-0.5"
                            title="Copy UTR to Clipboard"
                          >
                            {copiedId === `utr-${r.id}` ? (
                              <CheckCheck className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-500 text-[9px] sm:text-[10px] font-mono italic">No UTR Detected</span>
                      )}
                      <span className="text-slate-400 text-[10px] sm:text-[11px] truncate max-w-[170px] sm:max-w-xs md:max-w-sm" title={r.bank_description}>
                        {r.bank_description}
                      </span>
                    </div>
                  </td>

                  {/* Bank Amount */}
                  <td className="py-2 px-2.5 sm:px-3 text-right font-mono whitespace-nowrap font-tabular">
                    {isDebit ? (
                      <div className="text-rose-400 flex items-center justify-end gap-1">
                        <span className="text-[8px] sm:text-[9px] font-semibold bg-rose-950/80 px-1 py-0.2 rounded border border-rose-800">
                          DR
                        </span>
                        <span className="font-semibold text-[10px] sm:text-[11px]">({formatINR(r.bank_amount)})</span>
                      </div>
                    ) : (
                      <div className="text-slate-100 flex items-center justify-end gap-1">
                        <span className="text-[8px] sm:text-[9px] font-semibold bg-emerald-950/60 text-emerald-300 px-1 py-0.2 rounded border border-emerald-800/60">
                          CR
                        </span>
                        <span className="font-semibold text-[10px] sm:text-[11px]">{formatINR(r.bank_amount)}</span>
                      </div>
                    )}
                  </td>

                  {/* RZP Settlement ID */}
                  <td className="py-2 px-2.5 sm:px-3 whitespace-nowrap">
                    {r.rzp_settlement_id ? (
                      <div className="flex items-center gap-1 font-mono text-[10px] sm:text-[11px] text-blue-400">
                        <span className="truncate max-w-[100px] sm:max-w-[110px]" title={r.rzp_settlement_id}>
                          {r.rzp_settlement_id}
                        </span>
                        <button
                          onClick={() => handleCopy(r.rzp_settlement_id || "", `setl-${r.id}`)}
                          className="text-slate-500 hover:text-slate-300 transition p-0.5"
                          title="Copy Settlement ID"
                        >
                          {copiedId === `setl-${r.id}` ? (
                            <CheckCheck className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <Copy className="w-3 h-3" />
                          )}
                        </button>
                      </div>
                    ) : (
                      <span className="text-slate-600 text-[10px] sm:text-[11px] font-mono">--</span>
                    )}
                  </td>

                  {/* RZP Net & Gross Split */}
                  <td className="py-2 px-2.5 sm:px-3 text-right font-mono whitespace-nowrap text-[10px] sm:text-[11px] font-tabular">
                    {r.rzp_amount ? (
                      <div>
                        <div className="font-semibold text-slate-200">{formatINR(r.rzp_amount)}</div>
                        {r.rzp_gross_amount && r.rzp_gross_amount !== r.rzp_amount && (
                          <div className="text-[9px] sm:text-[10px] text-slate-400 font-mono">
                            Gross {formatINR(r.rzp_gross_amount)}
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="text-slate-600">--</span>
                    )}
                  </td>

                  {/* Delta / Discrepancy Amount */}
                  <td className="py-2 px-2.5 sm:px-3 text-right font-mono whitespace-nowrap text-[10px] sm:text-[11px] font-tabular">
                    {hasNonZeroDelta ? (
                      <span
                        className={
                          r.match_status === "MATCHED" && r.diagnostic_type === "FEE_DEDUCTION"
                            ? "text-amber-400 font-medium"
                            : r.match_status === "MATCHED" && r.diagnostic_type === "TDS_194O_DEDUCTION"
                            ? "text-yellow-400 font-medium"
                            : "text-rose-400 font-medium"
                        }
                      >
                        {formatINR(r.delta_amount)}
                      </span>
                    ) : (
                      <span className="text-emerald-500/70 text-[9px] sm:text-[10px]">₹ 0.00</span>
                    )}
                  </td>

                  {/* Status & Diagnostic Badge */}
                  <td className="py-2 px-2.5 sm:px-3 text-center whitespace-nowrap">
                    <StatusBadge
                      status={r.match_status}
                      tier={r.match_tier}
                      diagnosticType={r.diagnostic_type}
                      confidence={r.confidence_score}
                      note={r.diagnostic_note}
                      onClick={() => {
                        if (r.match_status === "CONFLICT") onOpenConflict(r);
                        if (r.match_status === "EXCEPTION") onOpenException(r);
                      }}
                    />
                  </td>

                  {/* Actions */}
                  <td className="py-2 px-2.5 sm:px-3 text-right whitespace-nowrap">
                    {r.match_status === "SUGGESTED" && (
                      <div className="inline-flex items-center gap-1">
                        <button
                          onClick={() => onApprove(r.id)}
                          className="p-1 sm:p-1.5 bg-[#0e281e] hover:bg-[#153f30] border border-[#165a42] text-emerald-300 rounded transition"
                          title="Approve Match (CA Action)"
                        >
                          <Check className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                        </button>
                        <button
                          onClick={() => onDeny(r.id)}
                          className="p-1 sm:p-1.5 bg-[#2d1219] hover:bg-[#471925] border border-[#5a1e2c] text-rose-300 rounded transition"
                          title="Deny / Mark Exception"
                        >
                          <X className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                        </button>
                      </div>
                    )}

                    {r.match_status === "CONFLICT" && (
                      <button
                        onClick={() => onOpenConflict(r)}
                        className="px-2 py-0.5 sm:py-1 bg-[#2d190e] hover:bg-[#462413] border border-[#582f14] text-orange-300 rounded text-[9px] sm:text-[10px] font-mono transition flex items-center gap-1 ml-auto"
                      >
                        <Split className="w-3 h-3" />
                        Resolve
                      </button>
                    )}

                    {r.match_status === "EXCEPTION" && (
                      <button
                        onClick={() => onOpenException(r)}
                        className="px-2 py-0.5 sm:py-1 bg-[#141b2a] hover:bg-[#1a253b] border border-[#233552] text-slate-300 rounded text-[9px] sm:text-[10px] font-mono transition flex items-center gap-1 ml-auto"
                      >
                        <Eye className="w-3 h-3" />
                        Audit
                      </button>
                    )}

                    {r.match_status === "MATCHED" && (
                      <span className="text-[9px] sm:text-[10px] font-mono text-emerald-500/80 uppercase tracking-tight">
                        {r.human_action ? `CA ${r.human_action}` : "AUTO OK"}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
