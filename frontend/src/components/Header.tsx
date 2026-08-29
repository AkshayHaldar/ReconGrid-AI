import React from "react";
import {
  Sparkles,
  UploadCloud,
  Building2,
  Calendar,
  Zap,
  HelpCircle,
  Search,
  Command,
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
  return (
    <header className="border-b border-[#1c2b42] bg-[#090e18]/95 backdrop-blur sticky top-0 z-30 px-3 sm:px-4 py-2 sm:py-2.5">
      <div className="max-w-7xl mx-auto flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-2.5 sm:gap-3">
        {/* Brand & Workspace Identity */}
        <div className="flex items-center justify-between lg:justify-start gap-2.5 sm:gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 sm:w-8 sm:h-8 rounded bg-[#10192a] border border-[#233552] flex items-center justify-center text-blue-400 font-bold text-xs sm:text-sm font-mono tracking-tight shadow-inner shrink-0">
              RG
            </div>
            <div>
              <div className="flex items-center gap-1.5 sm:gap-2">
                <h1 className="text-xs sm:text-sm font-bold text-slate-100 tracking-tight font-sans">
                  ReconGrid AI
                </h1>
                <span className="px-1.5 py-0.2 rounded bg-[#101d33] text-blue-300 border border-[#203960] text-[9px] sm:text-[10px] font-mono tracking-tight whitespace-nowrap">
                  Track 04 • Razorpay
                </span>
              </div>
              <p className="text-[10px] sm:text-[11px] text-slate-400 font-sans truncate max-w-[260px] sm:max-w-md">
                Autonomous Settlement Reconciliation & Discrepancy Diagnostics
              </p>
            </div>
          </div>

          {/* Fiscal Period (Visible on medium screens & above) */}
          <div className="hidden sm:flex lg:hidden items-center gap-1.5 px-2 py-0.5 bg-[#0f1726] border border-[#1c2b42] rounded text-[11px] text-slate-300 font-mono">
            <Calendar className="w-3 h-3 text-blue-400" />
            <span>Aug 2026 (FY 26-27)</span>
          </div>
        </div>

        {/* Indian Accounting Context & Controls */}
        <div className="flex flex-wrap sm:flex-nowrap items-center gap-1.5 sm:gap-2">
          {/* Fiscal Accounting Period (Desktop) */}
          <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 bg-[#0f1726] border border-[#1c2b42] rounded text-xs text-slate-300 font-mono shrink-0">
            <Calendar className="w-3.5 h-3.5 text-blue-400" />
            <span>Aug 2026 Close (FY 26-27)</span>
          </div>

          {/* Indian Bank Account Switcher */}
          <div className="flex items-center gap-1.5 px-2 py-1 bg-[#0f1726] border border-[#1c2b42] rounded text-xs text-slate-300 w-full sm:w-auto min-w-0 flex-1 sm:flex-initial">
            <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <select
              value={selectedBank}
              onChange={(e) => onBankChange(e.target.value)}
              className="bg-transparent border-none text-[11px] sm:text-xs text-slate-200 focus:outline-none cursor-pointer font-medium font-sans w-full truncate"
            >
              <option value="ALL" className="bg-[#0f1624] text-slate-200">
                All Bank Accounts (Consolidated ₹ Ledger)
              </option>
              <option value="HDFC" className="bg-[#0f1624] text-slate-200">
                HDFC Bank Current A/c **4019 (Primary Payouts)
              </option>
              <option value="ICICI" className="bg-[#0f1624] text-slate-200">
                ICICI Bank Current A/c **9122 (E-Collect)
              </option>
              <option value="SBI" className="bg-[#0f1624] text-slate-200">
                State Bank of India A/c **3301 (Statutory)
              </option>
              <option value="AXIS" className="bg-[#0f1624] text-slate-200">
                Axis Bank Current A/c **7712 (Direct)
              </option>
            </select>
          </div>

          {/* Action Buttons Group */}
          <div className="flex items-center gap-1.5 w-full sm:w-auto shrink-0">
            {/* Action: Upload Statement CSV */}
            <button
              onClick={onOpenUpload}
              className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-medium transition shadow-sm whitespace-nowrap"
            >
              <UploadCloud className="w-3.5 h-3.5" />
              <span>Upload CSV</span>
            </button>

            {/* Action: Sync / Seed */}
            <button
              onClick={onOpenSync}
              className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-2.5 py-1 bg-[#0f1726] hover:bg-[#142035] border border-[#1c2b42] text-slate-300 hover:text-white rounded text-xs font-medium transition whitespace-nowrap"
              title="Razorpay API Sync & Synthetic 60-Transaction Seeder"
            >
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span>Sync / Seed</span>
            </button>

            {/* Action: Toggle Settlement Q&A */}
            <button
              onClick={onToggleQa}
              className={`flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1 rounded text-xs font-medium transition border whitespace-nowrap ${
                isQaOpen
                  ? "bg-indigo-600 text-white border-indigo-500 shadow-sm"
                  : "bg-[#14172e] hover:bg-[#1c2040] text-indigo-300 border-[#2b3164]"
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Ask AI</span>
              <span className="hidden md:inline text-[10px] opacity-70 font-mono bg-indigo-950/80 px-1 py-0.2 rounded border border-indigo-700/60">
                ?
              </span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
