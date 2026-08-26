import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  XCircle,
  ArrowDownLeft,
  DollarSign,
  Info,
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

  let bgClass = "bg-emerald-950/60 text-emerald-300 border-emerald-800/80";
  let icon = <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0" />;
  let label = "MATCHED";

  if (status === "MATCHED") {
    if (diagnosticType === "FEE_DEDUCTION") {
      bgClass = "bg-amber-950/60 text-amber-300 border-amber-700/80";
      icon = <AlertTriangle className="w-3.5 h-3.5 mr-1 shrink-0 text-amber-400" />;
      label = "FEE DEDUCTION";
    } else if (diagnosticType === "TDS_194O_DEDUCTION") {
      bgClass = "bg-yellow-950/60 text-yellow-300 border-yellow-700/80";
      icon = <DollarSign className="w-3.5 h-3.5 mr-1 shrink-0 text-yellow-400" />;
      label = "1% TDS (194-O)";
    } else if (diagnosticType === "BATCHED_SETTLEMENT") {
      bgClass = "bg-indigo-950/60 text-indigo-300 border-indigo-700/80";
      icon = <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0 text-indigo-400" />;
      label = "BATCHED (2 SETL)";
    } else if (diagnosticType === "REFUND_ADJUSTED") {
      bgClass = "bg-purple-950/60 text-purple-300 border-purple-700/80";
      icon = <ArrowDownLeft className="w-3.5 h-3.5 mr-1 shrink-0 text-purple-400" />;
      label = "REFUND ADJ";
    } else if (diagnosticType === "FX_ADJUSTED") {
      bgClass = "bg-teal-950/60 text-teal-300 border-teal-700/80";
      icon = <DollarSign className="w-3.5 h-3.5 mr-1 shrink-0 text-teal-400" />;
      label = "FX ADJ";
    } else if (diagnosticType === "REVERSAL") {
      bgClass = "bg-rose-950/60 text-rose-300 border-rose-700/80";
      icon = <ArrowDownLeft className="w-3.5 h-3.5 mr-1 shrink-0 text-rose-400" />;
      label = "REVERSAL";
    } else {
      label = "OK MATCHED";
    }
  } else if (status === "SUGGESTED") {
    bgClass = "bg-sky-950/60 text-sky-300 border-sky-700/80";
    icon = <HelpCircle className="w-3.5 h-3.5 mr-1 shrink-0 text-sky-400" />;
    const confPercent = confidence ? `${Math.round(confidence * 100)}% ` : "";
    label = `${confPercent}SUGGESTED`;
  } else if (status === "CONFLICT") {
    bgClass = "bg-orange-950/60 text-orange-300 border-orange-700/80";
    icon = <AlertTriangle className="w-3.5 h-3.5 mr-1 shrink-0 text-orange-400" />;
    label = "⚠ CONFLICT";
  } else {
    bgClass = "bg-rose-950/60 text-rose-300 border-rose-700/80";
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
        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border font-mono tracking-tight transition-all hover:scale-105 ${bgClass} ${
          onClick ? "cursor-pointer" : "cursor-default"
        }`}
      >
        {icon}
        <span>{label}</span>
      </button>

      {/* Discrepancy Explanation Tooltip */}
      {showTooltip && note && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-64 p-2 bg-slate-900 text-slate-200 text-xs rounded border border-slate-700 shadow-xl backdrop-blur pointer-events-none transition-opacity duration-150">
          <div className="flex items-start gap-1.5">
            <Info className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="font-semibold text-slate-100 uppercase tracking-wider text-[10px]">
                {diagnosticType} • {tier}
              </div>
              <p className="text-[11px] leading-tight text-slate-300">{note}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
