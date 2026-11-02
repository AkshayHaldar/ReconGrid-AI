import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  XCircle,
  ArrowDownLeft,
  DollarSign,
  Info,
  Layers,
  Copy,
  CheckCheck,
  Split,
  Percent,
} from "lucide-react";
import { DiagnosticType, MatchStatus } from "@/lib/types";

interface StatusBadgeProps {
  status: MatchStatus;
  tier: string;
  diagnosticType: DiagnosticType;
  confidence?: number | null;
  note?: string;
  onClick?: () => void;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  tier,
  diagnosticType,
  confidence,
  note,
  onClick,
}) => {
  const [showTooltip, setShowTooltip] = useState(false);
  const [copied, setCopied] = useState(false);

  let bgClass = "bg-emerald-950/40 text-emerald-300 border-emerald-800/60";
  let icon = <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0 text-emerald-400" />;
  let label = "EXACT MATCH";

  // Map internal tiers and diagnostics to high-trust accounting terms
  let humanTier = "Exact UTR & Amount Match";
  if (tier === "TIER_1") humanTier = "Tier 1: Exact UTR Match";
  else if (tier === "TIER_1_5" || tier === "TIER_1.5") humanTier = "Tier 1.5: Reference Substring Match";
  else if (tier === "TIER_2") humanTier = "Tier 2: Fuzzy Descriptor (≥90%)";
  else if (tier === "TIER_0") humanTier = "Tier 0: Date Window Proximity (±3d)";
  else if (tier === "TIER_3") humanTier = "Tier 3: Diagnostic Delta Math";
  else if (tier === "MANUAL") humanTier = "CA Manual Approval";

  if (status === "MATCHED") {
    if (diagnosticType === "FEE_DEDUCTION") {
      bgClass = "bg-amber-950/40 text-amber-300 border-amber-800/60";
      icon = <AlertTriangle className="w-3.5 h-3.5 mr-1 shrink-0 text-amber-400" />;
      label = "MDR FEE (2%+GST)";
    } else if (diagnosticType === "TDS_194O_DEDUCTION") {
      bgClass = "bg-yellow-950/40 text-yellow-300 border-yellow-800/60";
      icon = <Percent className="w-3.5 h-3.5 mr-1 shrink-0 text-yellow-400" />;
      label = "1% TDS (194-O)";
    } else if (diagnosticType === "BATCHED_SETTLEMENT") {
      bgClass = "bg-indigo-950/40 text-indigo-300 border-indigo-800/60";
      icon = <Layers className="w-3.5 h-3.5 mr-1 shrink-0 text-indigo-400" />;
      label = "BATCHED SETL";
    } else if (diagnosticType === "REFUND_ADJUSTED") {
      bgClass = "bg-purple-950/40 text-purple-300 border-purple-800/60";
      icon = <ArrowDownLeft className="w-3.5 h-3.5 mr-1 shrink-0 text-purple-400" />;
      label = "REFUND ADJ";
    } else if (diagnosticType === "FX_ADJUSTED") {
      bgClass = "bg-teal-950/40 text-teal-300 border-teal-800/60";
      icon = <DollarSign className="w-3.5 h-3.5 mr-1 shrink-0 text-teal-400" />;
      label = "FX DELTA";
    } else if (diagnosticType === "REVERSAL") {
      bgClass = "bg-rose-950/40 text-rose-300 border-rose-800/60";
      icon = <ArrowDownLeft className="w-3.5 h-3.5 mr-1 shrink-0 text-rose-400" />;
      label = "REVERSAL";
    } else {
      label = "EXACT MATCH";
    }
  } else if (status === "SUGGESTED") {
    bgClass = "bg-sky-950/40 text-sky-300 border-sky-800/60";
    icon = <HelpCircle className="w-3.5 h-3.5 mr-1 shrink-0 text-sky-400" />;
    const confPercent = confidence ? `${Math.round(confidence * 100)}% ` : "";
    label = `${confPercent}SUGGESTED`;
  } else if (status === "CONFLICT") {
    bgClass = "bg-orange-950/40 text-orange-300 border-orange-800/60";
    icon = <Split className="w-3.5 h-3.5 mr-1 shrink-0 text-orange-400" />;
    label = "CONFLICT";
  } else {
    bgClass = "bg-rose-950/40 text-rose-300 border-rose-800/60";
    icon = <XCircle className="w-3.5 h-3.5 mr-1 shrink-0 text-rose-400" />;
    label = "EXCEPTION";
  }

  const handleCopyNote = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (note) {
      navigator.clipboard.writeText(note);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div
      className="relative inline-flex items-center"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border font-mono tracking-tight transition-all duration-150 ${bgClass} ${
          onClick ? "cursor-pointer hover:brightness-110 shadow-xs" : "cursor-default"
        }`}
      >
        {icon}
        <span>{label}</span>
      </button>

      {/* Discrepancy & Diagnostic Explanation Popover */}
      {showTooltip && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-3 bg-[#111318] text-neutral-200 text-xs rounded-lg border border-[#1e222d] shadow-2xl transition-all duration-150 tooltip-fade">
          <div className="flex items-start gap-2">
            <Info className="w-4 h-4 text-neutral-400 shrink-0 mt-0.5" />
            <div className="space-y-1.5 w-full">
              <div className="flex items-center justify-between font-mono text-[10px] pb-1 border-b border-[#1e222d]">
                <span className="font-semibold text-neutral-200 uppercase tracking-wide">
                  {diagnosticType.replace(/_/g, " ")}
                </span>
                <span className="text-neutral-300 bg-neutral-900 px-1.5 py-0.5 rounded border border-neutral-800">
                  {humanTier}
                </span>
              </div>

              {note ? (
                <p className="text-[11px] leading-relaxed text-neutral-300 font-sans">{note}</p>
              ) : (
                <p className="text-[11px] text-neutral-400 italic">Deterministic engine matched record with 100% confidence.</p>
              )}

              <div className="flex items-center justify-between text-[10px] font-mono text-neutral-400 pt-1.5 border-t border-[#1e222d]">
                <span>
                  {confidence ? `Confidence: ${Math.round(confidence * 100)}%` : "100% Deterministic"}
                </span>
                {note && (
                  <button
                    onClick={handleCopyNote}
                    className="text-neutral-400 hover:text-neutral-200 flex items-center gap-1 text-[9px] transition-colors cursor-pointer"
                  >
                    {copied ? (
                      <CheckCheck className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                    <span>{copied ? "Copied" : "Copy Note"}</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
