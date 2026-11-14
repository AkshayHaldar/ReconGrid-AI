import React, { useState } from "react";
import { formatFiscalPeriod } from "@/lib/formatters";
import {
  UploadCloud,
  Building2,
  Calendar,
  Zap,
  HelpCircle,
  FileText,
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
  /** The active batch's date. The fiscal period follows it, or today when it is missing. */
  periodDate?: string | Date | null;
}

export const Header: React.FC<HeaderProps> = ({
  selectedBank,
  onBankChange,
  onOpenUpload,
  onOpenSync,
  onToggleQa,
  isQaOpen,
  onExportTally,
  periodDate,
}) => {
  const [showShortcuts, setShowShortcuts] = useState(false);

  return (
    <>
      <header className="border-b border-[#1e222d] bg-[#090a0f]/95 backdrop-blur-md sticky top-0 z-30 px-3 sm:px-6 lg:px-8 py-2 transition-all">
        <div className="w-full max-w-[1920px] mx-auto flex flex-wrap xl:flex-nowrap items-center justify-between gap-x-3 gap-y-2">
          {/* Brand & Workspace Identity */}
          <div className="flex items-center justify-between xl:justify-start gap-3 w-full xl:w-auto min-w-0">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 shrink-0 rounded-md bg-[#161922] border border-[#282e3d] flex items-center justify-center text-neutral-100 font-semibold text-xs sm:text-sm font-mono tracking-tight shadow-xs">
                RG
              </div>

              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="text-sm sm:text-base leading-tight font-semibold text-neutral-100 tracking-tight font-sans">
                    ReconGrid
                  </h1>
                  <span className="px-1.5 py-0.5 rounded bg-neutral-900 text-neutral-400 border border-neutral-800 text-[9px] sm:text-[10px] font-mono tracking-tight font-medium">
                    SETTLEMENT CONSOLE
                  </span>
                </div>
                <p className="hidden sm:block text-[11px] leading-tight text-neutral-400 font-sans truncate max-w-[240px] sm:max-w-sm">
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
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2 w-full xl:w-auto min-w-0">
            {/* Live Gateway Status Badge (wide desktop) */}
            <div className="hidden 2xl:flex items-center gap-1.5 px-2.5 py-1.5 bg-[#111318] border border-[#1e222d] rounded-md text-[10px] font-mono text-emerald-400 shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span>Gateway Connected</span>
            </div>

            {/* Fiscal Accounting Period (follows the active batch date) */}
            <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 bg-[#111318] border border-[#1e222d] rounded-md text-xs text-neutral-300 font-mono shrink-0">
              <Calendar className="w-3.5 h-3.5 text-neutral-400" />
              <span suppressHydrationWarning>{formatFiscalPeriod(periodDate)}</span>
            </div>

            {/* Bank Account Selector */}
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#111318] border border-[#1e222d] hover:border-neutral-700 rounded-md text-xs text-neutral-300 w-full sm:w-[190px] 2xl:w-[260px] min-w-0 flex-1 sm:flex-initial transition">
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

            {/* Action Buttons: quiet helpers first, the main action (Upload) last */}
            <div className="flex items-center gap-1.5 w-full sm:w-auto shrink-0 sm:ml-auto xl:ml-0">
              {/* Keyboard Shortcuts Trigger */}
              <button
                onClick={() => setShowShortcuts(true)}
                className="p-1.5 bg-[#111318] hover:bg-[#161922] border border-[#1e222d] hover:border-neutral-700 text-neutral-400 hover:text-neutral-200 rounded-md transition cursor-pointer"
                title="Keyboard Shortcuts Cheat Sheet"
                aria-label="Keyboard Shortcuts"
              >
                <Keyboard className="w-3.5 h-3.5" />
              </button>

              {/* Settlement Q&A Copilot Toggle */}
              <button
                onClick={onToggleQa}
                className={`flex items-center justify-center gap-1.5 px-2.5 2xl:px-3 py-1.5 rounded-md text-xs font-medium transition border whitespace-nowrap cursor-pointer ${
                  isQaOpen
                    ? "bg-neutral-800 text-white border-neutral-600 shadow-xs"
                    : "bg-[#111318] hover:bg-[#161922] text-neutral-300 border-[#1e222d] hover:border-neutral-700"
                }`}
                title="Audit Assistant (press ?)"
                aria-label="Audit Assistant"
                aria-pressed={isQaOpen}
              >
                <HelpCircle className="w-3.5 h-3.5 text-neutral-400" />
                <span className="hidden 2xl:inline">Audit Assistant</span>
                <span className="hidden 2xl:inline text-[9px] font-mono text-neutral-400 bg-neutral-900 px-1 py-0.2 rounded border border-neutral-800">
                  ?
                </span>
              </button>

              {/* Gateway Sync & Synthetic Seeder (ghost, icon only) */}
              <button
                onClick={onOpenSync}
                className="p-1.5 bg-transparent hover:bg-[#161922] border border-transparent hover:border-[#1e222d] text-amber-400 rounded-md transition cursor-pointer"
                title="Razorpay Gateway API Sync & 60-Transaction Test Seeder"
                aria-label="Sync / Seed"
              >
                <Zap className="w-3.5 h-3.5" />
              </button>

              {/* Tally Prime XML export (outline) */}
              {onExportTally && (
                <button
                  onClick={onExportTally}
                  className="flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1.5 bg-transparent hover:bg-[#161922] border border-neutral-700 hover:border-neutral-500 text-neutral-200 hover:text-white rounded-md text-xs font-medium transition whitespace-nowrap cursor-pointer"
                  title="Download matched settlements as Tally Prime journal vouchers (XML)"
                  aria-label="Export to Tally (XML)"
                >
                  <FileText className="w-3.5 h-3.5 text-neutral-400" />
                  <span className="hidden sm:inline">Export to Tally (XML)</span>
                </button>
              )}

              {/* Upload Bank Statement (primary) */}
              <button
                onClick={onOpenUpload}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3 py-1.5 bg-neutral-100 hover:bg-white text-neutral-900 rounded-md text-xs font-semibold shadow-xs transition transform active:scale-98 whitespace-nowrap cursor-pointer"
              >
                <UploadCloud className="w-3.5 h-3.5" />
                <span>Upload Statement</span>
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
