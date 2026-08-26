import React, { useState } from "react";
import {
  Check,
  X,
  Copy,
  CheckCheck,
  ExternalLink,
  Split,
  Eye,
  ArrowDownRight,
  ArrowUpRight,
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
      <div className="bg-[#0e1524] border border-[#1e2a3f] rounded-lg p-12 text-center text-slate-400">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500 mb-3"></div>
        <p className="text-xs font-mono">Running deterministic multi-tier reconciliation engine...</p>
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="bg-[#0e1524] border border-[#1e2a3f] rounded-lg p-12 text-center text-slate-400">
        <p className="text-xs font-mono">No records match the current filter criteria.</p>
      </div>
    );
  }

  return (
    <div className="bg-[#0e1524] border border-[#1e2a3f] rounded-lg overflow-hidden shadow-md">
      <div className="overflow-x-auto max-h-[620px] overflow-y-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead className="sticky top-0 bg-[#121b2d] z-20 border-b border-[#1e2a3f] text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
            <tr>
              <th className="py-2.5 px-3 w-24">Date</th>
              <th className="py-2.5 px-3 min-w-[240px]">Bank UTR / Description</th>
              <th className="py-2.5 px-3 text-right w-32">Bank Amt</th>
              <th className="py-2.5 px-3 w-44">RZP Settlement ID</th>
              <th className="py-2.5 px-3 text-right w-32">RZP Net (Gross)</th>
              <th className="py-2.5 px-3 w-40 text-center">Status & Diagnostics</th>
              <th className="py-2.5 px-3 text-right w-28">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#182337] font-sans">
            {records.map((r) => {
              const isHighlighted = highlightedRecordId === r.id;
              const isDebit = r.bank_direction === "DEBIT";

              return (
                <tr
                  key={r.id}
                  id={`record-${r.id}`}
                  className={`hover:bg-[#141e33] transition-colors duration-150 ${
                    isHighlighted ? "bg-blue-950/50 ring-1 ring-blue-500" : ""
                  } ${isDebit ? "bg-rose-950/10" : ""}`}
                >
                  {/* Date */}
                  <td className="py-2 px-3 text-slate-300 font-mono whitespace-nowrap text-[11px]">
                    {formatDate(r.date)}
                  </td>

                  {/* Bank UTR & Description */}
                  <td className="py-2 px-3">
                    <div className="flex flex-col">
                      {r.bank_utr ? (
                        <div className="flex items-center gap-1">
                          <span className="font-mono font-semibold text-slate-200 text-[11px] tracking-tight">
                            {r.bank_utr}
                          </span>
                          <button
                            onClick={() => handleCopy(r.bank_utr || "", `utr-${r.id}`)}
                            className="text-slate-500 hover:text-slate-300 transition"
                            title="Copy UTR"
                          >
                            {copiedId === `utr-${r.id}` ? (
                              <CheckCheck className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-500 text-[10px] font-mono italic">No UTR Detected</span>
                      )}
                      <span className="text-slate-400 text-[11px] truncate max-w-sm" title={r.bank_description}>
                        {r.bank_description}
                      </span>
                    </div>
                  </td>

                  {/* Bank Amount */}
                  <td className="py-2 px-3 text-right font-mono whitespace-nowrap">
                    {isDebit ? (
                      <div className="text-rose-400 flex items-center justify-end gap-1">
                        <span className="text-[10px] font-semibold bg-rose-950/80 px-1 py-0.2 rounded border border-rose-800">
                          DEBIT
                        </span>
                        <span className="font-semibold">{formatINR(r.bank_amount)}</span>
                      </div>
                    ) : (
                      <span className="font-semibold text-slate-100">
                        {formatINR(r.bank_amount)}
                      </span>
                    )}
                  </td>

                  {/* RZP Settlement ID */}
                  <td className="py-2 px-3 whitespace-nowrap">
                    {r.rzp_settlement_id ? (
                      <div className="flex items-center gap-1.5 font-mono text-[11px] text-blue-400">
                        <span className="truncate max-w-[120px]" title={r.rzp_settlement_id}>
                          {r.rzp_settlement_id}
                        </span>
                        <button
                          onClick={() => handleCopy(r.rzp_settlement_id || "", `setl-${r.id}`)}
                          className="text-slate-500 hover:text-slate-300 transition"
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
                      <span className="text-slate-600 text-[11px] font-mono">--</span>
                    )}
                  </td>

                  {/* RZP Amount */}
                  <td className="py-2 px-3 text-right font-mono whitespace-nowrap text-[11px]">
                    {r.rzp_amount ? (
                      <div>
                        <div className="font-semibold text-slate-200">{formatINR(r.rzp_amount)}</div>
                        {r.rzp_gross_amount && r.rzp_gross_amount !== r.rzp_amount && (
                          <div className="text-[10px] text-slate-500">
                            Gross: {formatINR(r.rzp_gross_amount)}
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="text-slate-600">--</span>
                    )}
                  </td>

                  {/* Status & Diagnostic Badge */}
                  <td className="py-2 px-3 text-center whitespace-nowrap">
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
                  <td className="py-2 px-3 text-right whitespace-nowrap">
                    {r.match_status === "SUGGESTED" && (
                      <div className="inline-flex items-center gap-1">
                        <button
                          onClick={() => onApprove(r.id)}
                          className="p-1 bg-emerald-950 hover:bg-emerald-900 border border-emerald-700 text-emerald-300 rounded transition"
                          title="Approve Match"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onDeny(r.id)}
                          className="p-1 bg-rose-950 hover:bg-rose-900 border border-rose-700 text-rose-300 rounded transition"
                          title="Deny / Mark Exception"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}

                    {r.match_status === "CONFLICT" && (
                      <button
                        onClick={() => onOpenConflict(r)}
                        className="px-2 py-0.5 bg-orange-950 hover:bg-orange-900 border border-orange-700 text-orange-300 rounded text-[11px] font-mono transition flex items-center gap-1 ml-auto"
                      >
                        <Split className="w-3 h-3" />
                        Resolve
                      </button>
                    )}

                    {r.match_status === "EXCEPTION" && (
                      <button
                        onClick={() => onOpenException(r)}
                        className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300 rounded text-[11px] font-mono transition flex items-center gap-1 ml-auto"
                      >
                        <Eye className="w-3 h-3" />
                        Audit
                      </button>
                    )}

                    {r.match_status === "MATCHED" && (
                      <span className="text-[10px] font-mono text-emerald-500/80 uppercase">
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
