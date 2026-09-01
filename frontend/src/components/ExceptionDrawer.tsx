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
      <div className="fixed inset-y-0 right-0 w-full sm:w-[540px] bg-[#070b14] border-l border-[#18263a] shadow-2xl z-50 flex flex-col backdrop-blur-xl animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 bg-[#0a101d] border-b border-[#18263a] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 shrink-0">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100 font-sans">
                Forensic Audit Inspector
              </h3>
              <p className="text-[11px] text-rose-300 font-mono truncate max-w-[280px] sm:max-w-sm">
                Diagnostic: {record.diagnostic_type} • Variance: {formatINR(record.delta_amount)}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-800/50 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-3.5 text-xs overflow-y-auto font-sans touch-scroll flex-1">
          {/* Diagnostic Root-Cause Banner */}
          <div className="bg-rose-950/25 border border-rose-800/50 rounded-xl p-3.5 space-y-1.5 shadow-sm">
            <div className="text-[10px] uppercase font-bold text-rose-400 font-mono tracking-wider flex items-center justify-between">
              <span>Root-Cause Diagnostic Note</span>
              <span className="text-rose-300/80">Tier: {record.match_tier}</span>
            </div>
            <p className="text-slate-200 font-sans text-xs leading-relaxed">
              {record.diagnostic_note}
            </p>
          </div>

          {/* Structured Inspection Cards */}
          <div className="space-y-3">
            {/* Raw Bank Statement Entry */}
            <div className="fin-card rounded-xl p-3.5 space-y-2 shadow-sm">
              <div className="flex items-center justify-between text-[10px] uppercase font-bold text-slate-400 font-mono">
                <span className="flex items-center gap-1.5 text-blue-400">
                  <FileText className="w-3.5 h-3.5" />
                  Bank Statement Ledger Data
                </span>
                {record.raw_csv_row && (
                  <button
                    onClick={() => copyJson(record.raw_csv_row, "bank")}
                    className="text-slate-400 hover:text-slate-200 flex items-center gap-1 text-[10px] lowercase font-mono transition p-0.5"
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

              <div className="space-y-1.5 text-slate-300 font-mono text-[11px] font-tabular bg-[#060a12] p-3 rounded-lg border border-[#141f32]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Date:</span> <span>{formatDate(record.date)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Amount & Direction:</span>{" "}
                  <span className={record.bank_direction === "DEBIT" ? "text-rose-400 font-bold" : "text-emerald-400 font-bold"}>
                    {formatINR(record.bank_amount)} ({record.bank_direction})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">UTR Reference:</span>{" "}
                  <span className="text-slate-200 font-semibold">{record.bank_utr || "N/A"}</span>
                </div>
                <div className="pt-1.5 border-t border-[#141f32]">
                  <span className="text-slate-500 block text-[10px] mb-0.5">Narrative:</span>
                  <span className="text-slate-300 font-sans text-xs leading-normal">{record.bank_description}</span>
                </div>
              </div>

              {record.raw_csv_row && (
                <div className="pt-1">
                  <pre className="text-[10px] font-mono text-slate-400 bg-[#050810] p-2.5 rounded-lg overflow-x-auto max-h-32 border border-[#121a28]">
                    {JSON.stringify(record.raw_csv_row, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Linked Razorpay Data */}
            <div className="fin-card rounded-xl p-3.5 space-y-2 shadow-sm">
              <div className="flex items-center justify-between text-[10px] uppercase font-bold text-slate-400 font-mono">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <Code2 className="w-3.5 h-3.5" />
                  Linked Razorpay Gateway Payload
                </span>
                {record.raw_rzp_payload && (
                  <button
                    onClick={() => copyJson(record.raw_rzp_payload, "rzp")}
                    className="text-slate-400 hover:text-slate-200 flex items-center gap-1 text-[10px] lowercase font-mono transition p-0.5"
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
                <div className="space-y-1.5 text-slate-300 font-mono text-[11px] font-tabular bg-[#060a12] p-3 rounded-lg border border-[#141f32]">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Settlement ID:</span> <span className="text-blue-300 font-semibold">{record.rzp_settlement_id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Net Payout:</span>{" "}
                    <span className="text-emerald-400 font-bold">{formatINR(record.rzp_amount)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Gross Amount:</span>{" "}
                    <span className="text-slate-200">{formatINR(record.rzp_gross_amount)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Gateway Fees + GST:</span>{" "}
                    <span>
                      {formatINR(record.rzp_fees)} + {formatINR(record.rzp_tax)}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="bg-[#060a12] p-3 rounded-lg border border-[#141f32] text-center text-slate-500 italic font-mono text-[11px]">
                  No candidate Razorpay settlement found matching within date/amount proximity window.
                </div>
              )}

              {record.raw_rzp_payload && (
                <div className="pt-1">
                  <pre className="text-[10px] font-mono text-slate-400 bg-[#050810] p-2.5 rounded-lg overflow-x-auto max-h-32 border border-[#121a28]">
                    {JSON.stringify(record.raw_rzp_payload, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Recommended CA Audit Steps */}
            <div className="p-3 bg-blue-950/20 border border-blue-900/40 rounded-xl space-y-1.5 text-[11px] text-blue-200/90 font-sans">
              <div className="font-semibold text-blue-300 flex items-center gap-1.5">
                <Info className="w-3.5 h-3.5 text-blue-400" />
                <span>Recommended CA Audit Action</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-[10px] text-slate-300">
                <li>Verify transaction in Razorpay Merchant Dashboard under Settlement Reports.</li>
                <li>Cross-reference 2B / GSTR-2B filing for Input Tax Credit on payment gateway MDR.</li>
                <li>If reversal or chargeback, ensure journal entry debits Gateway Suspense A/c.</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#0a101d] border-t border-[#18263a] flex justify-end text-xs font-sans shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 bg-[#0e1626] hover:bg-[#162338] border border-[#18263a] text-slate-200 rounded-xl transition font-semibold text-center"
          >
            Close Audit Inspector
          </button>
        </div>
      </div>
    </>
  );
};
