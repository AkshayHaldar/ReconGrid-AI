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
  Sparkles,
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

  let bgClass = "bg-[#0c281e] text-emerald-300 border-[#15533d]";
  let icon = <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0 text-emerald-400" />;
  let label = "MATCHED";

  if (status === "MATCHED") {
    if (diagnosticType === "FEE_DEDUCTION") {
      bgClass = "bg-[#291b0c] text-amber-300 border-[#523310]";
      icon = <AlertTriangle className="w-3.5 h-3.5 mr-1 shrink-0 text-amber-400" />;
      label = "FEE DEDUCTED";
    } else if (diagnosticType === "TDS_194O_DEDUCTION") {
      bgClass = "bg-[#28220c] text-yellow-300 border-[#534311]";
      icon = <DollarSign className="w-3.5 h-3.5 mr-1 shrink-0 text-yellow-400" />;
      label = "1% TDS (194-O)";
    } else if (diagnosticType === "BATCHED_SETTLEMENT") {
      bgClass = "bg-[#181938] text-indigo-300 border-[#323670]";
      icon = <Layers className="w-3.5 h-3.5 mr-1 shrink-0 text-indigo-400" />;
      label = "BATCHED SETL";
    } else if (diagnosticType === "REFUND_ADJUSTED") {
      bgClass = "bg-[#231533] text-purple-300 border-[#47226a]";
      icon = <ArrowDownLeft className="w-3.5 h-3.5 mr-1 shrink-0 text-purple-400" />;
      label = "REFUND ADJ";
    } else if (diagnosticType === "FX_ADJUSTED") {
      bgClass = "bg-[#0d2625] text-teal-300 border-[#185350]";
      icon = <DollarSign className="w-3.5 h-3.5 mr-1 shrink-0 text-teal-400" />;
      label = "FX ADJ";
    } else if (diagnosticType === "REVERSAL") {
      bgClass = "bg-[#2c131a] text-rose-300 border-[#5a1e2a]";
      icon = <ArrowDownLeft className="w-3.5 h-3.5 mr-1 shrink-0 text-rose-400" />;
      label = "REVERSAL";
    } else {
      label = "OK MATCHED";
    }
  } else if (status === "SUGGESTED") {
    bgClass = "bg-[#0e2136] text-sky-300 border-[#1a426e]";
    icon = <HelpCircle className="w-3.5 h-3.5 mr-1 shrink-0 text-sky-400" />;
    const confPercent = confidence ? `${Math.round(confidence * 100)}% ` : "";
    label = `${confPercent}SUGGESTED`;
  } else if (status === "CONFLICT") {
    bgClass = "bg-[#2c1a0e] text-orange-300 border-[#583014]";
    icon = <AlertTriangle className="w-3.5 h-3.5 mr-1 shrink-0 text-orange-400" />;
    label = "⚠ CONFLICT";
  } else {
    bgClass = "bg-[#2b1219] text-rose-300 border-[#581e2b]";
    icon = <XCircle className="w-3.5 h-3.5 mr-1 shrink-0 text-rose-400" />;
    label = "EXCEPTION";
  }

  return (
    <div
      className="relative inline-flex items-center"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border font-mono tracking-tight transition-colors ${bgClass} ${
          onClick ? "cursor-pointer hover:brightness-125" : "cursor-default"
        }`}
      >
        {icon}
        <span>{label}</span>
      </button>

      {/* Discrepancy & Diagnostic Explanation Popover */}
      {showTooltip && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-64 p-2.5 bg-[#0a0f19] text-slate-200 text-xs rounded border border-[#233550] shadow-2xl pointer-events-none transition-opacity duration-150">
          <div className="flex items-start gap-2">
            <Info className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="font-semibold text-slate-200 uppercase tracking-wider text-[10px] flex items-center justify-between font-mono">
                <span>{diagnosticType.replace(/_/g, " ")}</span>
                <span className="text-slate-400">[{tier}]</span>
              </div>
              {note ? (
                <p className="text-[11px] leading-relaxed text-slate-300 font-sans">{note}</p>
              ) : (
                <p className="text-[11px] text-slate-400 italic">No additional note recorded.</p>
              )}
              {confidence && (
                <div className="text-[10px] font-mono text-slate-400 pt-0.5 border-t border-[#172236]">
                  Match Confidence: {Math.round(confidence * 100)}%
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
