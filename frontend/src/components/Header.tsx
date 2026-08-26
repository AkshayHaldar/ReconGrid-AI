import React from "react";
import {
  Sparkles,
  UploadCloud,
  RefreshCw,
  Building2,
  Calendar,
  Layers,
  Zap,
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
    <header className="border-b border-[#1b263b] bg-[#0a101d]/90 backdrop-blur sticky top-0 z-30 px-4 py-3">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        {/* Brand Logo & Title */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white font-bold text-base font-mono">
            RG
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-slate-100 tracking-tight">
                ReconGrid AI
              </h1>
              <span className="px-1.5 py-0.2 rounded bg-blue-950 text-blue-300 border border-blue-800 text-[10px] font-mono">
                Track 04 • Razorpay
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Autonomous Settlement Reconciliation & Discrepancy Diagnostics
            </p>
          </div>
        </div>

        {/* Global Controls & Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Date Range Badge */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 bg-[#0e1626] border border-[#1e2a3f] rounded-lg text-xs text-slate-300 font-mono">
            <Calendar className="w-3.5 h-3.5 text-blue-400" />
            <span>01 Aug – 26 Aug 2026</span>
          </div>

          {/* Bank Selector */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[#0e1626] border border-[#1e2a3f] rounded-lg text-xs text-slate-300">
            <Building2 className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={selectedBank}
              onChange={(e) => onBankChange(e.target.value)}
              className="bg-transparent border-none text-xs text-slate-200 focus:outline-none cursor-pointer font-medium"
            >
              <option value="ALL" className="bg-slate-900 text-slate-200">All Accounts (Consolidated)</option>
              <option value="HDFC" className="bg-slate-900 text-slate-200">HDFC Bank (Primary)</option>
              <option value="ICICI" className="bg-slate-900 text-slate-200">ICICI Bank</option>
              <option value="SBI" className="bg-slate-900 text-slate-200">State Bank of India</option>
              <option value="AXIS" className="bg-slate-900 text-slate-200">Axis Bank</option>
            </select>
          </div>

          {/* Action: Upload Statement CSV */}
          <button
            onClick={onOpenUpload}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium shadow-sm transition"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Upload CSV</span>
          </button>

          {/* Action: Sync / Demo Seeder */}
          <button
            onClick={onOpenSync}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#0e1626] hover:bg-slate-800 border border-[#1e2a3f] text-slate-300 hover:text-white rounded-lg text-xs font-medium transition"
            title="Razorpay API Sync & Synthetic Data Seeder"
          >
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span className="hidden sm:inline">Sync / Seed</span>
          </button>

          {/* Action: Toggle Settlement Q&A */}
          <button
            onClick={onToggleQa}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition border ${
              isQaOpen
                ? "bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-500/20"
                : "bg-indigo-950/60 hover:bg-indigo-900 text-indigo-300 border-indigo-700/80"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Ask ReconGrid</span>
          </button>
        </div>
      </div>
    </header>
  );
};
