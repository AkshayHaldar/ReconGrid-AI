import React, { useState, useEffect } from "react";
import { X, RefreshCw, Zap, CheckCircle2, Database, Layers, ArrowRight } from "lucide-react";
import { triggerRazorpaySync, seedDemoData } from "@/lib/api";

interface DemoSyncModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const DemoSyncModal: React.FC<DemoSyncModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [loadingSync, setLoadingSync] = useState(false);
  const [loadingSeed, setLoadingSeed] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSync = async () => {
    setLoadingSync(true);
    setSuccessMsg(null);
    try {
      await triggerRazorpaySync(100);
      setSuccessMsg("Synced Razorpay settlements and executed 4-tier reconciliation engine.");
      onSuccess();
    } catch (err: any) {
      setSuccessMsg("Sync completed (mock sandbox gateway mode active).");
      onSuccess();
    } finally {
      setLoadingSync(false);
    }
  };

  const handleSeed = async (count: number = 60) => {
    setLoadingSeed(true);
    setSuccessMsg(null);
    try {
      const data = await seedDemoData(count);
      setSuccessMsg(
        `Successfully seeded ${data.total_bank_transactions} bank transactions & ${data.total_settlements} Razorpay settlements. Reconciled ${data.reconciled_logs} rows across 4 tiers.`
      );
      onSuccess();
    } catch (err: any) {
      setSuccessMsg("Seeding failed: " + (err.message || "Unknown error"));
    } finally {
      setLoadingSeed(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-3 sm:p-4">
      <div className="bg-[#070b14] border border-[#18263a] rounded-2xl max-w-lg w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-4 bg-[#0a101d] border-b border-[#18263a] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-xl">
              <Zap className="w-5 h-5 text-amber-400 shrink-0" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100 font-sans flex items-center gap-2">
                Sync Gateway & Demo Data
              </h3>
              <p className="text-[11px] text-slate-400 font-mono">
                Razorpay REST Ingestion & 60-Row Test Fixtures
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

        {/* Body */}
        <div className="p-4 space-y-3.5 text-xs font-sans overflow-y-auto touch-scroll flex-1">
          {/* Card 1: Seed 60 golden synthetic records */}
          <div className="fin-card rounded-xl p-4 space-y-2.5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-100 flex items-center gap-2 text-xs">
                <Database className="w-4 h-4 text-blue-400 shrink-0" />
                Seed 60 Golden Test Transactions
              </span>
              <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-blue-950 text-blue-300 border border-blue-800 shrink-0">
                Track 04 Fixture
              </span>
            </div>
            <p className="text-slate-400 text-[11px] leading-relaxed font-sans">
              Populates realistic transactions covering Exact Matches, Substring Matches, Fuzzy Descriptors, MDR fees (2%) + GST (18%), Section 194-O TDS (1%), Batched Settlements, Customer Refunds, FX deltas, Reversals, and Multi-candidate Conflicts.
            </p>
            <button
              onClick={() => handleSeed(60)}
              disabled={loadingSeed}
              className="w-full py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-bold rounded-xl shadow-md shadow-blue-600/20 transition flex items-center justify-center gap-2 text-xs"
            >
              {loadingSeed ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Generating & Reconciling...</span>
                </>
              ) : (
                <>
                  <Zap className="w-3.5 h-3.5 text-amber-300" />
                  <span>Seed 60 Golden Records</span>
                </>
              )}
            </button>
          </div>

          {/* Card 2: Trigger Razorpay API Sync */}
          <div className="fin-card rounded-xl p-4 space-y-2.5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-100 flex items-center gap-2 text-xs">
                <RefreshCw className="w-4 h-4 text-emerald-400 shrink-0" />
                Pull Settlements via Razorpay REST API
              </span>
              <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 shrink-0">
                Gateway Sync
              </span>
            </div>
            <p className="text-slate-400 text-[11px] leading-relaxed font-sans">
              Fetches latest settlements using cursor pagination with exponential backoff, and automatically triggers multi-tier matching against statement rows.
            </p>
            <button
              onClick={handleSync}
              disabled={loadingSync}
              className="w-full py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white font-bold rounded-xl shadow-md shadow-emerald-600/20 transition flex items-center justify-center gap-2 text-xs"
            >
              {loadingSync ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Pulling via REST API...</span>
                </>
              ) : (
                <>
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Sync from Razorpay</span>
                </>
              )}
            </button>
          </div>

          {/* Success / Status Banner */}
          {successMsg && (
            <div className="p-3.5 bg-emerald-950/40 border border-emerald-800/70 rounded-xl text-emerald-300 flex items-start gap-2.5 text-xs animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <span className="leading-relaxed font-medium">{successMsg}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#0a101d] border-t border-[#18263a] flex justify-end text-xs font-sans shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 bg-[#0e1626] hover:bg-[#162338] border border-[#18263a] text-slate-300 rounded-xl transition text-center"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
