import React, { useState } from "react";
import {
  Sparkles,
  UploadCloud,
  Building2,
  Calendar,
  Zap,
  HelpCircle,
  ShieldCheck,
  Activity,
  CheckCircle2,
  X,
  Keyboard,
} from "lucide-react";

interface HeaderProps {
  selectedBank: string;
  onBankChange: (b: string) => void;
  onOpenUpload: () => void;
  onOpenSync: () => void;
  onToggleQa: () => void;
  isQaOpen: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  selectedBank,
  onBankChange,
  onOpenUpload,
  onOpenSync,
  onToggleQa,
  isQaOpen,
}) => {
  const [showShortcuts, setShowShortcuts] = useState(false);

  return (
    <>
      <header className="border-b border-[#162438] bg-[#070b14]/95 backdrop-blur-md sticky top-0 z-30 px-3 sm:px-5 py-2.5 transition-all">
        <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          {/* Brand & Workspace Identity */}
          <div className="flex items-center justify-between lg:justify-start gap-3">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-lg bg-gradient-to-br from-blue-600 via-indigo-600 to-cyan-500 p-[1px] shadow-lg shadow-blue-500/20">
                  <div className="w-full h-full bg-[#090e18] rounded-lg flex items-center justify-center text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-300 font-extrabold text-xs sm:text-sm font-mono tracking-tighter">
                    RG
                  </div>
                </div>
                <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-[#070b14] animate-pulse"></div>
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-sm sm:text-base font-extrabold text-slate-100 tracking-tight font-sans">
                    ReconGrid <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-400">AI</span>
                  </h1>
                  <span className="px-2 py-0.5 rounded-full bg-blue-950/80 text-blue-300 border border-blue-800/60 text-[9px] sm:text-[10px] font-mono tracking-tight font-medium shadow-xs">
                    Track 04 • Razorpay
                  </span>
                </div>
                <p className="text-[10px] sm:text-[11px] text-slate-400 font-sans truncate max-w-[240px] sm:max-w-sm">
                  Autonomous Settlement Reconciliation & Discrepancy Diagnostics
                </p>
              </div>
            </div>

            {/* Live Gateway Pill (Mobile / Tablet) */}
            <div className="flex sm:hidden items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-950/50 border border-emerald-800/50 text-[9px] font-mono text-emerald-300">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Live Engine</span>
            </div>
          </div>

          {/* Controls & Action Center */}
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
            {/* Live Gateway & Engine Status Badge (Desktop) */}
            <div className="hidden xl:flex items-center gap-2 px-2.5 py-1 bg-[#0a101d] border border-[#162337] rounded-lg text-xs font-mono text-slate-300">
              <div className="flex items-center gap-1.5 text-emerald-400 text-[10px]">
                <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50 animate-pulse"></span>
                <span>Gateway Connected</span>
              </div>
              <span className="text-slate-600">|</span>
              <div className="flex items-center gap-1 text-[10px] text-blue-300">
                <ShieldCheck className="w-3 h-3 text-blue-400" />
                <span>4-Tier Engine v2.1</span>
              </div>
            </div>

            {/* Fiscal Accounting Period */}
            <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 bg-[#0a101d] border border-[#162337] rounded-lg text-xs text-slate-300 font-mono shrink-0">
              <Calendar className="w-3.5 h-3.5 text-blue-400" />
              <span>Aug 2026 Close (FY 26-27)</span>
            </div>

            {/* Bank Account Selector */}
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#0a101d] border border-[#162337] hover:border-[#223550] rounded-lg text-xs text-slate-300 w-full sm:w-auto min-w-0 flex-1 sm:flex-initial transition">
              <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <select
                value={selectedBank}
                onChange={(e) => onBankChange(e.target.value)}
                className="bg-transparent border-none text-[11px] sm:text-xs text-slate-200 focus:outline-none cursor-pointer font-medium font-sans w-full truncate pr-1"
                aria-label="Select Bank Account Ledger"
              >
                <option value="ALL" className="bg-[#0c121e] text-slate-200">
                  All Accounts (Consolidated ₹ Ledger)
                </option>
                <option value="HDFC" className="bg-[#0c121e] text-slate-200">
                  HDFC Current A/c **4019 (Primary Payouts)
                </option>
                <option value="ICICI" className="bg-[#0c121e] text-slate-200">
                  ICICI Current A/c **9122 (E-Collect)
                </option>
                <option value="SBI" className="bg-[#0c121e] text-slate-200">
                  State Bank of India A/c **3301 (Statutory)
                </option>
                <option value="AXIS" className="bg-[#0c121e] text-slate-200">
                  Axis Current A/c **7712 (Direct)
                </option>
              </select>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-1.5 w-full sm:w-auto shrink-0">
              {/* Keyboard Shortcuts Trigger */}
              <button
                onClick={() => setShowShortcuts(true)}
                className="p-1.5 bg-[#0a101d] hover:bg-[#121d30] border border-[#162337] text-slate-400 hover:text-slate-200 rounded-lg transition"
                title="Keyboard Shortcuts Cheat Sheet"
                aria-label="Keyboard Shortcuts"
              >
                <Keyboard className="w-3.5 h-3.5" />
              </button>

              {/* Upload Bank Statement */}
              <button
                onClick={onOpenUpload}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white rounded-lg text-xs font-semibold shadow-md shadow-blue-600/20 transition transform active:scale-98 whitespace-nowrap"
              >
                <UploadCloud className="w-3.5 h-3.5" />
                <span>Upload Statement</span>
              </button>

              {/* Gateway Sync & Synthetic Seeder */}
              <button
                onClick={onOpenSync}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 bg-[#0a101d] hover:bg-[#142034] border border-[#1a2b42] hover:border-amber-500/40 text-slate-300 hover:text-white rounded-lg text-xs font-medium transition shadow-xs whitespace-nowrap"
                title="Razorpay Gateway API Sync & 60-Transaction Test Seeder"
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Sync / Seed</span>
              </button>

              {/* Settlement Q&A Copilot Toggle */}
              <button
                onClick={onToggleQa}
                className={`flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition border whitespace-nowrap ${
                  isQaOpen
                    ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white border-indigo-500 shadow-md shadow-indigo-500/25"
                    : "bg-[#111326] hover:bg-[#191d38] text-indigo-300 border-[#242b58] hover:border-indigo-500/50"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5 text-indigo-300 animate-pulse" />
                <span>Ask AI</span>
                <span className="hidden md:inline text-[9px] font-mono opacity-90 bg-indigo-950 px-1 py-0.2 rounded border border-indigo-800">
                  ?
                </span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Keyboard Shortcuts Cheat Sheet Modal */}
      {showShortcuts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4">
          <div className="bg-[#090e18] border border-[#18263a] rounded-xl max-w-md w-full p-4 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-[#162337] mb-3">
              <div className="flex items-center gap-2">
                <Keyboard className="w-4 h-4 text-blue-400" />
                <h3 className="text-sm font-semibold text-slate-100 font-sans">
                  Keyboard Shortcuts & Controls
                </h3>
              </div>
              <button
                onClick={() => setShowShortcuts(false)}
                className="p-1 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#0c121e] rounded border border-[#162337]">
                <span className="text-slate-300">Focus Ledger Search</span>
                <span className="kbd-chip">/</span>
              </div>
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#0c121e] rounded border border-[#162337]">
                <span className="text-slate-300">Toggle Settlement AI Copilot</span>
                <span className="kbd-chip">?</span>
              </div>
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#0c121e] rounded border border-[#162337]">
                <span className="text-slate-300">Switch Filter Tabs</span>
                <div className="flex gap-1">
                  <span className="kbd-chip">1</span>
                  <span className="kbd-chip">2</span>
                  <span className="kbd-chip">3</span>
                  <span className="kbd-chip">4</span>
                  <span className="kbd-chip">5</span>
                </div>
              </div>
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#0c121e] rounded border border-[#162337]">
                <span className="text-slate-300">Close Drawer / Modal</span>
                <span className="kbd-chip">Esc</span>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-[#162337] text-right">
              <button
                onClick={() => setShowShortcuts(false)}
                className="px-3 py-1.5 bg-[#101928] hover:bg-[#18263a] text-slate-200 rounded text-xs transition"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
