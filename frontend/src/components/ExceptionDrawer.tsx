import React from "react";
import { X, ShieldAlert, Code2 } from "lucide-react";
import { ReconciliationRecordItem } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/formatters";

interface ExceptionDrawerProps {
  record: ReconciliationRecordItem | null;
  onClose: () => void;
}

export const ExceptionDrawer: React.FC<ExceptionDrawerProps> = ({
  record,
  onClose,
}) => {
  if (!record) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="bg-[#0c1322] border border-rose-600/40 rounded-xl max-w-2xl w-full overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="p-4 bg-rose-950/40 border-b border-rose-800/40 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0" />
            <div>
              <h3 className="text-sm font-semibold text-slate-100">
                Manual Audit Inspection — Exception Row
              </h3>
              <p className="text-[11px] text-rose-300/80">
                Deterministic reason code: {record.diagnostic_type} • Delta: {formatINR(record.delta_amount)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1 rounded-md transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4 text-xs max-h-[70vh] overflow-y-auto">
          {/* Diagnostic Note */}
          <div className="bg-rose-950/20 border border-rose-900/50 rounded-lg p-3">
            <div className="text-[10px] uppercase font-semibold text-rose-400 mb-1">
              Audit Diagnostic Note
            </div>
            <p className="text-slate-200 font-mono text-[11px] leading-relaxed">
              {record.diagnostic_note}
            </p>
          </div>

          {/* Side by side raw payloads */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Raw Bank CSV Row */}
            <div className="bg-[#10182b] border border-slate-700/60 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-[10px] uppercase font-semibold text-slate-400 mb-2">
                <Code2 className="w-3.5 h-3.5 text-blue-400" />
                Raw Bank CSV Data
              </div>
              <div className="space-y-1 text-slate-300 font-mono text-[11px]">
                <div><span className="text-slate-500">Date:</span> {formatDate(record.date)}</div>
                <div><span className="text-slate-500">Amount:</span> {formatINR(record.bank_amount)}</div>
                <div><span className="text-slate-500">Direction:</span> {record.bank_direction}</div>
                <div><span className="text-slate-500">UTR:</span> {record.bank_utr || "N/A"}</div>
                <div className="pt-1"><span className="text-slate-500">Narrative:</span> {record.bank_description}</div>
              </div>
              {record.raw_csv_row && (
                <div className="mt-2 pt-2 border-t border-slate-800">
                  <div className="text-[9px] text-slate-500 uppercase font-mono mb-1">CSV Row JSON:</div>
                  <pre className="text-[10px] font-mono text-slate-400 bg-slate-950/80 p-2 rounded overflow-x-auto max-h-32">
                    {JSON.stringify(record.raw_csv_row, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Raw Razorpay Payload */}
            <div className="bg-[#10182b] border border-slate-700/60 rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-[10px] uppercase font-semibold text-slate-400 mb-2">
                <Code2 className="w-3.5 h-3.5 text-emerald-400" />
                Linked Razorpay Data
              </div>
              {record.rzp_settlement_id ? (
                <div className="space-y-1 text-slate-300 font-mono text-[11px]">
                  <div><span className="text-slate-500">Settlement ID:</span> {record.rzp_settlement_id}</div>
                  <div><span className="text-slate-500">Net Amount:</span> {formatINR(record.rzp_amount)}</div>
                  <div><span className="text-slate-500">Gross:</span> {formatINR(record.rzp_gross_amount)}</div>
                  <div><span className="text-slate-500">Fees + GST:</span> {formatINR(record.rzp_fees)} + {formatINR(record.rzp_tax)}</div>
                </div>
              ) : (
                <p className="text-slate-500 italic font-mono text-[11px]">
                  No candidate Razorpay settlement found in database for this date/amount window.
                </p>
              )}
              {record.raw_rzp_payload && (
                <div className="mt-2 pt-2 border-t border-slate-800">
                  <div className="text-[9px] text-slate-500 uppercase font-mono mb-1">Razorpay Payload JSON:</div>
                  <pre className="text-[10px] font-mono text-slate-400 bg-slate-950/80 p-2 rounded overflow-x-auto max-h-32">
                    {JSON.stringify(record.raw_rzp_payload, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3.5 bg-[#0a101d] border-t border-[#182337] flex justify-end gap-2 text-xs">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition font-medium"
          >
            Close Audit Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
