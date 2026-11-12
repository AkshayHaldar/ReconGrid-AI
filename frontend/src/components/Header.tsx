import React, { useState } from "react";
import {
  UploadCloud,
  Building2,
  Calendar,
  Zap,
  HelpCircle,
  FileText,
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
  onExportTally?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  selectedBank,
  onBankChange,
  onOpenUpload,
  onOpenSync,
  onToggleQa,
  isQaOpen,
  onExportTally,
}) => {
  const [showShortcuts, setShowShortcuts] = useState(false);

  return (
    <>
      <header className="border-b border-[#1e222d] bg-[#090a0f]/95 backdrop-blur-md sticky top-0 z-30 px-3 sm:px-6 lg:px-8 py-2.5 transition-all">
        <div className="w-full max-w-[1920px] mx-auto flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          {/* Brand & Workspace Identity */}
          <div className="flex items-center justify-between lg:justify-start gap-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 sm:w-8.5 sm:h-8.5 rounded-md bg-[#161922] border border-[#282e3d] flex items-center justify-center text-neutral-100 font-semibold text-xs sm:text-sm font-mono tracking-tight shadow-xs">
                RG
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-sm sm:text-base font-semibold text-neutral-100 tracking-tight font-sans">
                    ReconGrid
                  </h1>
                  <span className="px-1.5 py-0.5 rounded bg-neutral-900 text-neutral-400 border border-neutral-800 text-[9px] sm:text-[10px] font-mono tracking-tight font-medium">
                    SETTLEMENT CONSOLE
                  </span>
                </div>
                <p className="text-[10px] sm:text-[11px] text-neutral-400 font-sans truncate max-w-[240px] sm:max-w-sm">
                  Automated Settlement Reconciliation & Variance Audit
                </p>
              </div>
            </div>

            {/* Live Gateway Pill (Mobile / Tablet) */}
            <div className="flex sm:hidden items-center gap-1.5 px-2 py-0.5 rounded bg-neutral-900 border border-neutral-800 text-[9px] font-mono text-neutral-300">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span>Live Engine</span>
            </div>
          </div>

          {/* Controls & Action Center */}
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
            {/* Live Gateway & Engine Status Badge (Desktop) */}
            <div className="hidden xl:flex items-center gap-2 px-2.5 py-1 bg-[#111318] border border-[#1e222d] rounded-md text-xs font-mono text-neutral-300">
              <div className="flex items-center gap-1.5 text-emerald-400 text-[10px]">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                <span>Gateway Connected</span>
              </div>
              <span className="text-neutral-700">|</span>
              <div className="flex items-center gap-1 text-[10px] text-neutral-400">
                <ShieldCheck className="w-3 h-3 text-neutral-400" />
                <span>Deterministic Engine v2.1</span>
              </div>
            </div>

            {/* Fiscal Accounting Period */}
            <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 bg-[#111318] border border-[#1e222d] rounded-md text-xs text-neutral-300 font-mono shrink-0">
              <Calendar className="w-3.5 h-3.5 text-neutral-400" />
              <span>Aug 2026 Close (FY 26-27)</span>
            </div>

            {/* Bank Account Selector */}
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#111318] border border-[#1e222d] hover:border-neutral-700 rounded-md text-xs text-neutral-300 w-full sm:w-auto min-w-0 flex-1 sm:flex-initial transition">
              <Building2 className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
              <select
                value={selectedBank}
                onChange={(e) => onBankChange(e.target.value)}
                className="bg-transparent border-none text-[11px] sm:text-xs text-neutral-200 focus:outline-none cursor-pointer font-medium font-sans w-full truncate pr-1"
                aria-label="Select Bank Account Ledger"
              >
                <option value="ALL" className="bg-[#111318] text-neutral-200">
                  All Accounts (Consolidated ₹ Ledger)
                </option>
                <option value="HDFC" className="bg-[#111318] text-neutral-200">
                  HDFC Current A/c **4019 (Primary Payouts)
                </option>
                <option value="ICICI" className="bg-[#111318] text-neutral-200">
                  ICICI Current A/c **9122 (E-Collect)
                </option>
                <option value="SBI" className="bg-[#111318] text-neutral-200">
                  State Bank of India A/c **3301 (Statutory)
                </option>
                <option value="AXIS" className="bg-[#111318] text-neutral-200">
                  Axis Current A/c **7712 (Direct)
                </option>
              </select>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-1.5 w-full sm:w-auto shrink-0">
              {/* Keyboard Shortcuts Trigger */}
              <button
                onClick={() => setShowShortcuts(true)}
                className="p-1.5 bg-[#111318] hover:bg-[#161922] border border-[#1e222d] hover:border-neutral-700 text-neutral-400 hover:text-neutral-200 rounded-md transition"
                title="Keyboard Shortcuts Cheat Sheet"
                aria-label="Keyboard Shortcuts"
              >
                <Keyboard className="w-3.5 h-3.5" />
              </button>

              {/* Tally Prime XML export */}
              {onExportTally && (
                <button
                  onClick={onExportTally}
                  className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 bg-[#111318] hover:bg-[#161922] border border-[#1e222d] hover:border-neutral-700 text-neutral-300 hover:text-white rounded-md text-xs font-medium transition whitespace-nowrap cursor-pointer"
                  title="Download matched settlements as Tally Prime journal vouchers (XML)"
                >
                  <FileText className="w-3.5 h-3.5 text-neutral-400" />
                  <span>Export to Tally (XML)</span>
                </button>
              )}

              {/* Upload Bank Statement */}
              <button
                onClick={onOpenUpload}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 bg-neutral-100 hover:bg-white text-neutral-900 rounded-md text-xs font-semibold shadow-xs transition transform active:scale-98 whitespace-nowrap cursor-pointer"
              >
                <UploadCloud className="w-3.5 h-3.5" />
                <span>Upload Statement</span>
              </button>

              {/* Gateway Sync & Synthetic Seeder */}
              <button
                onClick={onOpenSync}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 bg-[#111318] hover:bg-[#161922] border border-[#1e222d] hover:border-neutral-700 text-neutral-300 hover:text-white rounded-md text-xs font-medium transition whitespace-nowrap cursor-pointer"
                title="Razorpay Gateway API Sync & 60-Transaction Test Seeder"
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>Sync / Seed</span>
              </button>

              {/* Settlement Q&A Copilot Toggle */}
              <button
                onClick={onToggleQa}
                className={`flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition border whitespace-nowrap cursor-pointer ${
                  isQaOpen
                    ? "bg-neutral-800 text-white border-neutral-600 shadow-xs"
                    : "bg-[#111318] hover:bg-[#161922] text-neutral-300 border-[#1e222d] hover:border-neutral-700"
                }`}
              >
                <FileText className="w-3.5 h-3.5 text-neutral-400" />
                <span>Audit Assistant</span>
                <span className="hidden md:inline text-[9px] font-mono text-neutral-400 bg-neutral-900 px-1 py-0.2 rounded border border-neutral-800">
                  ?
                </span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Keyboard Shortcuts Cheat Sheet Modal */}
      {showShortcuts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4">
          <div className="bg-[#111318] border border-[#1e222d] rounded-xl max-w-md w-full p-4 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-[#1e222d] mb-3">
              <div className="flex items-center gap-2">
                <Keyboard className="w-4 h-4 text-neutral-300" />
                <h3 className="text-sm font-semibold text-neutral-100 font-sans">
                  Keyboard Shortcuts & Controls
                </h3>
              </div>
              <button
                onClick={() => setShowShortcuts(false)}
                className="p-1 text-neutral-400 hover:text-neutral-200 rounded-md hover:bg-neutral-800 transition cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#151820] rounded border border-[#1e222d]">
                <span className="text-neutral-300">Focus Ledger Search</span>
                <span className="kbd-chip">/</span>
              </div>
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#151820] rounded border border-[#1e222d]">
                <span className="text-neutral-300">Toggle Audit Assistant</span>
                <span className="kbd-chip">?</span>
              </div>
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#151820] rounded border border-[#1e222d]">
                <span className="text-neutral-300">Switch Filter Tabs</span>
                <div className="flex gap-1">
                  <span className="kbd-chip">1</span>
                  <span className="kbd-chip">2</span>
                  <span className="kbd-chip">3</span>
                  <span className="kbd-chip">4</span>
                  <span className="kbd-chip">5</span>
                </div>
              </div>
              <div className="flex items-center justify-between py-1.5 px-2 bg-[#151820] rounded border border-[#1e222d]">
                <span className="text-neutral-300">Close Drawer / Modal</span>
                <span className="kbd-chip">Esc</span>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-[#1e222d] text-right">
              <button
                onClick={() => setShowShortcuts(false)}
                className="px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 rounded text-xs transition cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
