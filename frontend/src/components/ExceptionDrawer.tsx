import React, { useState, useEffect } from "react";
import { X, ShieldAlert, Code2, Copy, CheckCheck, CheckCircle2, AlertTriangle } from "lucide-react";
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
  const [copiedBank, setCopiedBank] = useState(false);
  const [copiedRzp, setCopiedRzp] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!record) return null;

  const copyJson = (data: any, type: "bank" | "rzp") => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    if (type === "bank") {
      setCopiedBank(true);
      setTimeout(() => setCopiedBank(false), 1500);
    } else {
      setCopiedRzp(true);
      setTimeout(() => setCopiedRzp(false), 1500);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-2.5 sm:p-4">
      <div className="bg-[#0f1624] border border-[#3b1c24] rounded-lg max-w-2xl w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-3 sm:p-3.5 bg-[#1a0e14] border-b border-[#3b1c24] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
            <div>
              <h3 className="text-xs font-semibold text-slate-100 font-sans">
                Forensic Audit Inspector — Exception Row
              </h3>
              <p className="text-[9px] sm:text-[10px] text-rose-300/80 font-mono truncate max-w-[240px] sm:max-w-md">
                Reason: {record.diagnostic_type} • Delta Variance: {formatINR(record.delta_amount)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1 rounded transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-3 sm:p-4 space-y-3 sm:space-y-3.5 text-xs overflow-y-auto font-sans touch-scroll flex-1">
          {/* Diagnostic Note */}
          <div className="bg-[#180e14] border border-[#3a1d26] rounded p-2.5 sm:p-3">
            <div className="text-[9px] sm:text-[10px] uppercase font-semibold text-rose-400 mb-1 font-mono">
              Audit Diagnostic Note
            </div>
            <p className="text-slate-200 font-sans text-[11px] sm:text-xs leading-relaxed">
              {record.diagnostic_note}
            </p>
          </div>

          {/* Side by side raw payloads */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 sm:gap-3">
            {/* Raw Bank CSV Row */}
            <div className="bg-[#0b101b] border border-[#1c2b42] rounded p-2.5 sm:p-3 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between text-[9px] sm:text-[10px] uppercase font-semibold text-slate-400 mb-2 font-mono">
                  <span className="flex items-center gap-1">
                    <Code2 className="w-3.5 h-3.5 text-blue-400" />
                    Bank CSV Row Data
                  </span>
                  {record.raw_csv_row && (
                    <button
                      onClick={() => copyJson(record.raw_csv_row, "bank")}
                      className="text-slate-400 hover:text-slate-200 flex items-center gap-1 text-[9px] lowercase font-mono transition p-0.5"
                    >
                      {copiedBank ? (
                        <CheckCheck className="w-3 h-3 text-emerald-400" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                      <span>copy json</span>
                    </button>
                  )}
                </div>
                <div className="space-y-1 text-slate-300 font-mono text-[10px] sm:text-[11px] font-tabular">
                  <div>
                    <span className="text-slate-500">Date:</span> {formatDate(record.date)}
                  </div>
                  <div>
                    <span className="text-slate-500">Amount:</span> {formatINR(record.bank_amount)} (
                    {record.bank_direction})
                  </div>
                  <div>
                    <span className="text-slate-500">UTR:</span> {record.bank_utr || "N/A"}
                  </div>
                  <div className="pt-1">
                    <span className="text-slate-500">Narrative:</span>{" "}
                    <span className="text-slate-300 font-sans text-[11px] sm:text-xs">{record.bank_description}</span>
                  </div>
                </div>
              </div>
              {record.raw_csv_row && (
                <div className="mt-2.5 pt-2 border-t border-[#172338]">
                  <pre className="text-[9px] sm:text-[10px] font-mono text-slate-400 bg-[#070b13] p-2 rounded overflow-x-auto max-h-28">
                    {JSON.stringify(record.raw_csv_row, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Linked Razorpay Data */}
            <div className="bg-[#0b101b] border border-[#1c2b42] rounded p-2.5 sm:p-3 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between text-[9px] sm:text-[10px] uppercase font-semibold text-slate-400 mb-2 font-mono">
                  <span className="flex items-center gap-1">
                    <Code2 className="w-3.5 h-3.5 text-emerald-400" />
                    Razorpay Settlement Data
                  </span>
                  {record.raw_rzp_payload && (
                    <button
                      onClick={() => copyJson(record.raw_rzp_payload, "rzp")}
                      className="text-slate-400 hover:text-slate-200 flex items-center gap-1 text-[9px] lowercase font-mono transition p-0.5"
                    >
                      {copiedRzp ? (
                        <CheckCheck className="w-3 h-3 text-emerald-400" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                      <span>copy json</span>
                    </button>
                  )}
                </div>
                {record.rzp_settlement_id ? (
                  <div className="space-y-1 text-slate-300 font-mono text-[10px] sm:text-[11px] font-tabular">
                    <div>
                      <span className="text-slate-500">Settlement ID:</span> {record.rzp_settlement_id}
                    </div>
                    <div>
                      <span className="text-slate-500">Net Amount:</span> {formatINR(record.rzp_amount)}
                    </div>
                    <div>
                      <span className="text-slate-500">Gross Amount:</span> {formatINR(record.rzp_gross_amount)}
                    </div>
                    <div>
                      <span className="text-slate-500">Fees + GST:</span> {formatINR(record.rzp_fees)} +{" "}
                      {formatINR(record.rzp_tax)}
                    </div>
                  </div>
                ) : (
                  <p className="text-slate-500 italic font-mono text-[10px] sm:text-[11px] py-2">
                    No candidate Razorpay settlement found matching within date/amount window.
                  </p>
                )}
              </div>
              {record.raw_rzp_payload && (
                <div className="mt-2.5 pt-2 border-t border-[#172338]">
                  <pre className="text-[9px] sm:text-[10px] font-mono text-slate-400 bg-[#070b13] p-2 rounded overflow-x-auto max-h-28">
                    {JSON.stringify(record.raw_rzp_payload, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-2.5 sm:p-3 bg-[#0a0f19] border-t border-[#182538] flex justify-end text-xs font-sans shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-3.5 py-1.5 bg-[#121b2b] hover:bg-[#182338] border border-[#1c2b42] text-slate-200 rounded transition font-medium text-center"
          >
            Close Audit Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
