import React, { useState, useEffect } from "react";
import {
  X,
  AlertTriangle,
  Check,
  Split,
  ShieldAlert,
  Ban,
  Info,
  CheckCircle2,
  Calendar,
  Layers,
} from "lucide-react";
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
  const [selectedRecordId, setSelectedRecordId] = useState<string>("");

  useEffect(() => {
    if (record) {
      setSelectedRecordId(record.id);
      setNote("");
    }
  }, [record]);

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

  const allCandidates = [record, ...competingRecords];
  const activeSelectedCandidate = allCandidates.find((c) => c.id === selectedRecordId) || record;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-xs z-40"
        onClick={onClose}
      />

      {/* Slide-out Drawer */}
      <div className="fixed inset-y-0 right-0 w-full sm:w-[520px] bg-[#070b14] border-l border-[#18263a] shadow-2xl z-50 flex flex-col backdrop-blur-xl animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 bg-[#0a101d] border-b border-[#18263a] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 shrink-0">
              <Split className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100 font-sans">
                Resolve Multi-Candidate Conflict
              </h3>
              <p className="text-[11px] text-amber-400 font-mono truncate max-w-[280px] sm:max-w-xs">
                Contested Settlement: {record.rzp_settlement_id || "Unlinked"}
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
          {/* Contested Razorpay Settlement Breakdown */}
          <div className="fin-card rounded-xl p-3.5 space-y-2 font-mono shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold text-blue-400 tracking-wide">
                Contested Razorpay Settlement
              </span>
              <span className="text-[10px] bg-blue-950 text-blue-300 px-2 py-0.5 rounded-full border border-blue-800">
                {record.rzp_settlement_id || "Unlinked"}
              </span>
            </div>
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-baseline gap-1 pt-1.5 border-t border-[#141f32]">
              <span className="text-slate-400 text-[11px] font-tabular">
                Gross: {formatINR(record.rzp_gross_amount)} | Fee: {formatINR(record.rzp_fees)} | GST: {formatINR(record.rzp_tax)}
              </span>
              <span className="text-emerald-400 font-bold text-sm font-tabular">
                Net Payout: {formatINR(record.rzp_amount)}
              </span>
            </div>
          </div>

          {/* Candidate Selection List */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-slate-300 text-xs font-semibold font-sans">
              <span className="flex items-center gap-1.5">
                <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
                <span>Select Valid Bank Entry ({allCandidates.length} Claimants):</span>
              </span>
            </div>

            <div className="space-y-2">
              {allCandidates.map((cand) => {
                const isSelected = selectedRecordId === cand.id;
                return (
                  <div
                    key={cand.id}
                    onClick={() => setSelectedRecordId(cand.id)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all duration-150 flex flex-col gap-2 ${
                      isSelected
                        ? "bg-[#0b1628] border-blue-500/80 ring-1 ring-blue-500/50 shadow-md"
                        : "bg-[#090e18] border-[#162438] hover:border-slate-500"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono">
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-4 h-4 rounded-full border flex items-center justify-center transition ${
                            isSelected
                              ? "border-blue-400 bg-blue-500 text-white"
                              : "border-slate-600 bg-[#060a12]"
                          }`}
                        >
                          {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                        </div>
                        <span className="font-bold text-slate-100 text-xs">
                          {cand.bank_utr || "No UTR Detected"}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          ({formatDate(cand.date)})
                        </span>
                      </div>
                      <span className="font-bold text-xs font-tabular text-slate-100">
                        {formatINR(cand.bank_amount)}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 truncate pl-6 font-sans">
                      {cand.bank_description}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Automatic Displacement Info Callout */}
          <div className="p-3 bg-amber-950/30 border border-amber-800/50 rounded-xl text-[11px] text-amber-300/90 flex items-start gap-2.5 font-sans leading-relaxed">
            <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <strong className="text-amber-200">Automatic Displacement Rule:</strong>{" "}
              Allocating this settlement will match the chosen bank entry and automatically unbind the other {allCandidates.length - 1} competing row(s), moving them to <code>EXCEPTION (AUTO_DISPLACED)</code> for independent CA audit.
            </div>
          </div>

          {/* CA Resolution Audit Note */}
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-300 font-sans">
              CA Resolution Audit Note (Mandatory Audit Trail)
            </label>
            <input
              type="text"
              placeholder="e.g. Verified against HDFC statement credit & merchant payout log"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full px-3.5 py-2 bg-[#080d16] border border-[#18263a] focus:border-blue-500 rounded-xl text-xs text-slate-200 focus:outline-none font-sans transition shadow-inner"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="p-3.5 sm:p-4 bg-[#0a101d] border-t border-[#18263a] flex flex-col-reverse sm:flex-row sm:items-center justify-between gap-2.5 text-xs font-sans shrink-0">
          <button
            onClick={() => {
              onResolve(record.id, "DISMISS", note || "Dismissed by CA");
              onClose();
            }}
            className="w-full sm:w-auto px-3.5 py-2 bg-rose-950/60 hover:bg-rose-900 border border-rose-800/80 text-rose-300 rounded-xl transition flex items-center justify-center gap-1.5 text-xs font-semibold shadow-xs"
            title="Unlink from settlement and mark as unresolved exception"
          >
            <Ban className="w-3.5 h-3.5" />
            <span>Dismiss All to Exception</span>
          </button>

          <div className="flex items-center justify-end gap-2 w-full sm:w-auto">
            <button
              onClick={onClose}
              className="flex-1 sm:flex-initial px-3.5 py-2 bg-[#0e1626] hover:bg-[#162338] border border-[#18263a] text-slate-300 rounded-xl transition text-center"
            >
              Cancel
            </button>
            <button
              onClick={() => {
                if (record.rzp_settlement_id) {
                  onResolve(activeSelectedCandidate.id, record.rzp_settlement_id, note);
                  onClose();
                }
              }}
              className="flex-1 sm:flex-initial px-4 py-2 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-semibold rounded-xl shadow-md shadow-orange-600/25 transition flex items-center justify-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Assign & Resolve</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
};
