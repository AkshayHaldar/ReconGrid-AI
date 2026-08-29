import React, { useState, useEffect } from "react";
import { X, AlertTriangle, Check, Split, ShieldAlert, Ban, Info } from "lucide-react";
import { ReconciliationRecordItem } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/formatters";

interface ConflictDrawerProps {
  record: ReconciliationRecordItem | null;
  allRecords?: ReconciliationRecordItem[];
  onClose: () => void;
  onResolve: (recordId: string, chosenSettlementId: string, note?: string) => void;
}

export const ConflictDrawer: React.FC<ConflictDrawerProps> = ({
  record,
  allRecords = [],
  onClose,
  onResolve,
}) => {
  const [note, setNote] = useState("");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!record) return null;

  // Find competing bank transactions claiming the same settlement
  const competingRecords = allRecords.filter(
    (r) =>
      r.id !== record.id &&
      r.match_status === "CONFLICT" &&
      ((r.rzp_settlement_id && r.rzp_settlement_id === record.rzp_settlement_id) ||
        (r.rzp_settlement_db_id && r.rzp_settlement_db_id === record.rzp_settlement_db_id))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-2.5 sm:p-4">
      <div className="bg-[#0f1624] border border-[#3b2314] rounded-lg max-w-xl w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-3 sm:p-3.5 bg-[#1a110a] border-b border-[#3b2314] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-orange-400 shrink-0" />
            <div>
              <h3 className="text-xs font-semibold text-slate-100 font-sans">
                Resolve Multi-Candidate Conflict
              </h3>
              <p className="text-[9px] sm:text-[10px] text-orange-300/80 font-mono truncate max-w-[240px] sm:max-w-md">
                Deterministic Lock: Multiple bank rows contest settlement {record.rzp_settlement_id}
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

        {/* Content */}
        <div className="p-3 sm:p-4 space-y-3 sm:space-y-3.5 text-xs overflow-y-auto font-sans touch-scroll flex-1">
          {/* Contested Razorpay Settlement Breakdown */}
          <div className="bg-[#0b101b] border border-[#1a2b44] rounded p-2.5 sm:p-3 space-y-1.5 font-mono">
            <div className="flex items-center justify-between">
              <span className="text-[9px] sm:text-[10px] uppercase font-semibold text-blue-400">
                Contested Razorpay Settlement
              </span>
              <span className="text-[9px] sm:text-[10px] bg-[#101b2f] text-blue-300 px-1.5 py-0.2 rounded border border-[#1c355e]">
                {record.rzp_settlement_id || "Unlinked"}
              </span>
            </div>
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-baseline gap-1 pt-1">
              <span className="text-slate-400 text-[10px] sm:text-[11px] font-tabular">
                Gross: {formatINR(record.rzp_gross_amount)} | Fee: {formatINR(record.rzp_fees)} | GST: {formatINR(record.rzp_tax)}
              </span>
              <span className="text-emerald-400 font-bold text-xs font-tabular">
                Net Payout: {formatINR(record.rzp_amount)}
              </span>
            </div>
          </div>

          {/* Selected Target Bank Statement Row */}
          <div className="bg-[#121c2e] border border-[#2b4164] rounded p-2.5 sm:p-3 space-y-1.5 ring-1 ring-blue-500/30 font-mono">
            <div className="flex items-center justify-between">
              <span className="text-[9px] sm:text-[10px] uppercase font-semibold text-sky-400">
                Active Bank Statement Row
              </span>
              <span className="text-[9px] sm:text-[10px] text-slate-400">
                Date: {formatDate(record.date)}
              </span>
            </div>
            <div className="flex justify-between items-baseline">
              <span className="text-slate-200 font-semibold text-[10px] sm:text-[11px]">
                {record.bank_utr || "No UTR Detected"}
              </span>
              <span className="text-slate-100 font-bold text-xs font-tabular">
                {formatINR(record.bank_amount)}
              </span>
            </div>
            <p className="text-slate-400 text-[10px] sm:text-[11px] truncate font-sans">{record.bank_description}</p>
          </div>

          {/* Competing Bank Transactions List */}
          {competingRecords.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-slate-300 text-[10px] sm:text-[11px] font-medium">
                <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span>Competing claimants locked by this conflict ({competingRecords.length}):</span>
              </div>
              {competingRecords.map((cr) => (
                <div
                  key={cr.id}
                  className="bg-[#0b101b] border border-[#1c293d] rounded p-2 sm:p-2.5 space-y-1 text-slate-400 font-mono"
                >
                  <div className="flex justify-between items-baseline">
                    <span className="text-slate-300 text-[10px] sm:text-[11px]">
                      {cr.bank_utr || "No UTR"} ({formatDate(cr.date)})
                    </span>
                    <span className="text-slate-200 font-semibold text-[10px] sm:text-[11px] font-tabular">
                      {formatINR(cr.bank_amount)}
                    </span>
                  </div>
                  <p className="text-[9px] sm:text-[10px] truncate text-slate-500 font-sans">{cr.bank_description}</p>
                </div>
              ))}
              <div className="p-2 bg-[#1b140b] border border-[#3d2c13] rounded text-[9px] sm:text-[10px] text-amber-300/90 flex items-start gap-1.5 font-sans">
                <Info className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Automatic Displacement:</strong> Allocating this settlement to the active bank row will automatically unlock competing rows and transition them to <code>EXCEPTION (AUTO_DISPLACED)</code> for separate audit.
                </span>
              </div>
            </div>
          )}

          {/* CA Resolution Note */}
          <div>
            <label className="block text-[10px] sm:text-[11px] font-medium text-slate-300 mb-1 font-sans">
              CA Resolution Audit Note
            </label>
            <input
              type="text"
              placeholder="e.g. Verified against HDFC statement entry #241 & merchant payout ledger"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full px-2.5 sm:px-3 py-1.5 bg-[#0b101b] border border-[#1c2b42] rounded text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-sans"
            />
          </div>
        </div>

        {/* Action Controls */}
        <div className="p-2.5 sm:p-3 bg-[#0a0f19] border-t border-[#182538] flex flex-col-reverse sm:flex-row sm:items-center justify-between gap-2 text-xs font-sans shrink-0">
          <button
            onClick={() => {
              onResolve(record.id, "DISMISS", note);
              onClose();
            }}
            className="w-full sm:w-auto px-2.5 py-1.5 bg-[#251016] hover:bg-[#381520] border border-[#4d1d28] text-rose-300 rounded transition flex items-center justify-center gap-1 text-[11px] sm:text-xs"
            title="Unlink from settlement and mark as unresolved exception"
          >
            <Ban className="w-3.5 h-3.5" />
            <span>Dismiss / Mark Exception</span>
          </button>

          <div className="flex items-center justify-end gap-2 w-full sm:w-auto">
            <button
              onClick={onClose}
              className="flex-1 sm:flex-initial px-3 py-1.5 bg-[#121b2b] hover:bg-[#182338] border border-[#1c2b42] text-slate-300 rounded transition text-center"
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
              className="flex-1 sm:flex-initial px-3.5 py-1.5 bg-orange-600 hover:bg-orange-500 text-white font-medium rounded shadow-sm transition flex items-center justify-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Assign & Resolve</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
