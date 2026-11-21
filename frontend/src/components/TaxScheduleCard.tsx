import React, { useEffect, useState } from "react";
import { Download, FileText, ShieldAlert } from "lucide-react";
import { fetchTaxSchedule, taxScheduleExportUrl } from "@/lib/api";
import { formatINR } from "@/lib/formatters";
import { TaxSchedule } from "@/lib/types";

interface TaxScheduleCardProps {
  batchId?: string;
  /** Changes whenever the ledger changes, so the schedule is re-fetched. */
  refreshKey?: number | string;
}

export const TaxScheduleCard: React.FC<TaxScheduleCardProps> = ({ batchId = "default", refreshKey }) => {
  const [schedule, setSchedule] = useState<TaxSchedule | null>(null);
  const [error, setError] = useState(false);
  const [intraState, setIntraState] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    fetchTaxSchedule(batchId, intraState)
      .then((data) => {
        if (!cancelled) setSchedule(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [batchId, intraState, refreshKey]);

  const deviations = schedule?.tds_deviations ?? [];

  return (
    <div className="fin-card rounded-lg p-3 shadow-xs space-y-2" aria-label="Tax and Statutory Summary">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-neutral-400">
        <div className="flex items-center gap-2">
          <FileText className="w-3.5 h-3.5 text-neutral-400" />
          <span className="font-medium text-neutral-200">Tax &amp; Statutory Summary</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={!intraState}
              onChange={(e) => setIntraState(!e.target.checked)}
            />
            <span>Inter-state (IGST)</span>
          </label>
          <a
            href={taxScheduleExportUrl(batchId, intraState)}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 px-2 py-0.5 rounded border border-[#282e3d] bg-[#151820] hover:bg-[#1c202b] text-neutral-300"
          >
            <Download className="w-3 h-3" />
            <span>CA Schedule CSV</span>
          </a>
        </div>
      </div>

      {error && <div className="text-[11px] text-rose-400 font-mono">Could not load the tax schedule.</div>}

      {schedule && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] font-mono font-tabular">
            <Stat label="Gross volume" value={formatINR(schedule.gross_volume)} />
            <Stat
              label="TDS 194-O (actual / expected)"
              value={`${formatINR(schedule.actual_tds)} / ${formatINR(schedule.expected_tds)}`}
            />
            <Stat label="MDR fees" value={formatINR(schedule.mdr_fees)} />
            <Stat
              label={intraState ? "GST ITC (CGST + SGST)" : "GST ITC (IGST)"}
              value={
                intraState
                  ? `${formatINR(schedule.cgst)} + ${formatINR(schedule.sgst)}`
                  : formatINR(schedule.igst)
              }
            />
          </div>

          {deviations.length > 0 && (
            <div className="text-[11px] font-mono text-amber-300 bg-amber-950/50 border border-amber-800/60 rounded px-2 py-1.5 space-y-1">
              <div className="flex items-center gap-1.5 font-medium">
                <ShieldAlert className="w-3 h-3 text-amber-400" />
                <span>{deviations.length} settlement(s) with TDS deviation</span>
              </div>
              {deviations.slice(0, 5).map((d) => (
                <div key={d.settlement_id} className="text-neutral-300">
                  {d.settlement_id}: expected {formatINR(d.expected_tds)}, deducted {formatINR(d.actual_tds)}
                </div>
              ))}
              {deviations.length > 5 && <div className="text-neutral-400">and {deviations.length - 5} more in the CSV</div>}
            </div>
          )}
          {schedule.tds_unverifiable > 0 && (
            <div className="text-[10px] font-mono text-neutral-500">
              TDS could not be verified for {schedule.tds_unverifiable} settlement(s) with no gross or TDS reported.
            </div>
          )}
        </>
      )}
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-[#0c0e12] border border-[#1e222d] rounded px-2 py-1.5">
    <div className="text-[10px] text-neutral-500">{label}</div>
    <div className="text-neutral-100">{value}</div>
  </div>
);
