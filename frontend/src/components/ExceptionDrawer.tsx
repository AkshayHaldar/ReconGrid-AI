import React, { useState, useEffect } from "react";
import {
  X,
  ShieldAlert,
  Code2,
  Copy,
  CheckCheck,
  CheckCircle2,
  AlertTriangle,
  FileText,
  FileSpreadsheet,
  Layers,
  ArrowDownRight,
  Info,
} from "lucide-react";
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
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-xs z-40"
        onClick={onClose}
      />

      {/* Slide-out Drawer */}
      <div className="fixed inset-y-0 right-0 w-full sm:w-[540px] bg-[#0c0e12] border-l border-[#1e222d] shadow-2xl z-50 flex flex-col backdrop-blur-xl animate-in slide-in-from-right duration-150">
        {/* Header */}
        <div className="p-4 bg-[#111318] border-b border-[#1e222d] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-md bg-rose-950/40 border border-rose-800/50 text-rose-400 shrink-0">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-neutral-100 font-sans">
                Forensic Audit Inspector
              </h3>
              <p className="text-[11px] text-rose-300 font-mono truncate max-w-[280px] sm:max-w-sm">
                Diagnostic: {record.diagnostic_type} • Variance: {formatINR(record.delta_amount)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-200 p-1.5 rounded-md hover:bg-neutral-800 transition cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-3.5 text-xs overflow-y-auto font-sans touch-scroll flex-1">
          {/* Diagnostic Root-Cause Banner */}
          <div className="bg-rose-950/20 border border-rose-800/40 rounded-lg p-3.5 space-y-1.5 shadow-xs">
            <div className="text-[10px] uppercase font-semibold text-rose-400 font-mono tracking-wider flex items-center justify-between">
              <span>Root-Cause Diagnostic Note</span>
              <span className="text-rose-300/80">Tier: {record.match_tier}</span>
            </div>
            <p className="text-neutral-200 font-sans text-xs leading-relaxed">
              {record.diagnostic_note}
            </p>
          </div>

          {/* Structured Inspection Cards */}
          <div className="space-y-3">
            {/* Raw Bank Statement Entry */}
            <div className="fin-card rounded-lg p-3.5 space-y-2 shadow-xs">
              <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-neutral-400 font-mono">
                <span className="flex items-center gap-1.5 text-neutral-300">
                  <FileText className="w-3.5 h-3.5" />
                  Bank Statement Ledger Data
                </span>
                {record.raw_csv_row && (
                  <button
                    onClick={() => copyJson(record.raw_csv_row, "bank")}
                    className="text-neutral-400 hover:text-neutral-200 flex items-center gap-1 text-[10px] lowercase font-mono transition p-0.5 cursor-pointer"
                  >
                    {copiedBank ? (
                      <CheckCheck className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                    <span>{copiedBank ? "copied" : "copy json"}</span>
                  </button>
                )}
              </div>

              <div className="space-y-1.5 text-neutral-300 font-mono text-[11px] font-tabular bg-[#0c0e12] p-3 rounded border border-[#1e222d]">
                <div className="flex justify-between">
                  <span className="text-neutral-500">Date:</span> <span>{formatDate(record.date)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-500">Amount & Direction:</span>{" "}
                  <span className={record.bank_direction === "DEBIT" ? "text-rose-400 font-semibold" : "text-emerald-400 font-semibold"}>
                    {formatINR(record.bank_amount)} ({record.bank_direction})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-500">UTR Reference:</span>{" "}
                  <span className="text-neutral-200 font-medium">{record.bank_utr || "N/A"}</span>
                </div>
                <div className="pt-1.5 border-t border-[#1e222d]">
                  <span className="text-neutral-500 block text-[10px] mb-0.5">Narrative:</span>
                  <span className="text-neutral-300 font-sans text-xs leading-normal">{record.bank_description}</span>
                </div>
              </div>

              {record.raw_csv_row && (
                <div className="pt-1">
                  <pre className="text-[10px] font-mono text-neutral-300 bg-[#08090d] p-2.5 rounded overflow-x-auto max-h-32 border border-[#1e222d]">
                    {JSON.stringify(record.raw_csv_row, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Linked Razorpay Data */}
            <div className="fin-card rounded-lg p-3.5 space-y-2 shadow-xs">
              <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-neutral-400 font-mono">
                <span className="flex items-center gap-1.5 text-neutral-300">
                  <Code2 className="w-3.5 h-3.5" />
                  Linked Razorpay Gateway Payload
                </span>
                {record.raw_rzp_payload && (
                  <button
                    onClick={() => copyJson(record.raw_rzp_payload, "rzp")}
                    className="text-neutral-400 hover:text-neutral-200 flex items-center gap-1 text-[10px] lowercase font-mono transition p-0.5 cursor-pointer"
                  >
                    {copiedRzp ? (
                      <CheckCheck className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                    <span>{copiedRzp ? "copied" : "copy json"}</span>
                  </button>
                )}
              </div>

              {record.rzp_settlement_id ? (
                <div className="space-y-1.5 text-neutral-300 font-mono text-[11px] font-tabular bg-[#0c0e12] p-3 rounded border border-[#1e222d]">
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Settlement ID:</span> <span className="text-neutral-200 font-medium">{record.rzp_settlement_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Net Payout:</span>{" "}
                    <span className="text-emerald-400 font-semibold">{formatINR(record.rzp_amount)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Gross Amount:</span>{" "}
                    <span className="text-neutral-200">{formatINR(record.rzp_gross_amount)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">Gateway Fees + GST:</span>{" "}
                    <span>
                      {formatINR(record.rzp_fees)} + {formatINR(record.rzp_tax)}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="bg-[#0c0e12] p-3 rounded border border-[#1e222d] text-center text-neutral-500 italic font-mono text-[11px]">
                  No candidate Razorpay settlement found matching within date/amount proximity window.
                </div>
              )}

              {record.raw_rzp_payload && (
                <div className="pt-1">
                  <pre className="text-[10px] font-mono text-neutral-300 bg-[#08090d] p-2.5 rounded overflow-x-auto max-h-32 border border-[#1e222d]">
                    {JSON.stringify(record.raw_rzp_payload, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Recommended CA Audit Steps */}
            <div className="p-3 bg-[#151820] border border-[#1e222d] rounded-lg space-y-1.5 text-[11px] text-neutral-300 font-sans">
              <div className="font-semibold text-neutral-200 flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-neutral-400" />
                <span>Recommended CA Audit Action</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-[10px] text-neutral-400">
                <li>Verify transaction in Razorpay Merchant Dashboard under Settlement Reports.</li>
                <li>Cross-reference 2B / GSTR-2B filing for Input Tax Credit on payment gateway MDR.</li>
                <li>If reversal or chargeback, ensure journal entry debits Gateway Suspense A/c.</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#111318] border-t border-[#1e222d] flex justify-end text-xs font-sans shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 rounded-md transition font-medium text-center cursor-pointer"
          >
            Close Audit Inspector
          </button>
        </div>
      </div>
    </>
  );
};
