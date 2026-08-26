import React, { useState } from "react";
import { X, AlertTriangle, Check, Split } from "lucide-react";
import { ReconciliationRecordItem } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/formatters";

interface ConflictDrawerProps {
  record: ReconciliationRecordItem | null;
  onClose: () => void;
  onResolve: (recordId: string, chosenSettlementId: string, note?: string) => void;
}

export const ConflictDrawer: React.FC<ConflictDrawerProps> = ({
  record,
  onClose,
  onResolve,
}) => {
  const [note, setNote] = useState("");

  if (!record) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="bg-[#0e1626] border border-orange-600/40 rounded-xl max-w-lg w-full overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="p-4 bg-orange-950/40 border-b border-orange-800/40 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-orange-400 shrink-0" />
            <div>
              <h3 className="text-sm font-semibold text-slate-100">
                Resolve Multi-Candidate Conflict
              </h3>
              <p className="text-[11px] text-orange-300/80">
                Settlement is claimed by multiple bank statement transactions
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

        {/* Content */}
        <div className="p-4 space-y-4 text-xs">
          {/* Target Bank Transaction */}
          <div className="bg-[#141f33] border border-slate-700/60 rounded-lg p-3 space-y-1.5">
            <div className="text-[10px] uppercase font-semibold text-slate-400">
              Bank Transaction
            </div>
            <div className="flex justify-between items-baseline">
              <span className="font-mono text-slate-200 font-semibold">
                {record.bank_utr || "No UTR"}
              </span>
              <span className="font-mono text-slate-100 font-bold text-sm">
                {formatINR(record.bank_amount)}
              </span>
            </div>
            <p className="text-slate-400 text-[11px] font-mono">{record.bank_description}</p>
            <div className="text-[10px] text-slate-500 font-mono">Date: {formatDate(record.date)}</div>
          </div>

          {/* Target Razorpay Settlement */}
          <div className="bg-[#141f33] border border-slate-700/60 rounded-lg p-3 space-y-1.5">
            <div className="text-[10px] uppercase font-semibold text-slate-400">
              Razorpay Settlement
            </div>
            <div className="flex justify-between items-baseline">
              <span className="font-mono text-blue-400 font-semibold">
                {record.rzp_settlement_id || "Unlinked"}
              </span>
              <span className="font-mono text-emerald-400 font-bold text-sm">
                {formatINR(record.rzp_amount)}
              </span>
            </div>
            <p className="text-slate-400 text-[11px]">
              Gross: {formatINR(record.rzp_gross_amount)} | Fees: {formatINR(record.rzp_fees)} | GST: {formatINR(record.rzp_tax)}
            </p>
          </div>

          {/* Audit Note */}
          <div>
            <label className="block text-[11px] font-medium text-slate-300 mb-1">
              CA Resolution Note (Audit Trail)
            </label>
            <input
              type="text"
              placeholder="e.g. Verified with bank branch reference"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full px-3 py-2 bg-[#090e18] border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="p-3.5 bg-[#0a101d] border-t border-[#182337] flex justify-end gap-2 text-xs">
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              if (record.rzp_settlement_id) {
                onResolve(record.id, record.rzp_settlement_id, note);
                onClose();
              }
            }}
            className="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 text-white font-medium rounded-lg shadow-md transition flex items-center gap-1.5"
          >
            <Check className="w-3.5 h-3.5" />
            <span>Confirm Match & Resolve</span>
          </button>
        </div>
      </div>
    </div>
  );
};
