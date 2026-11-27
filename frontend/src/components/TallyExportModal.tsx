import React, { useEffect, useRef } from "react";
import type { ReconciliationStatus } from "@/lib/types";
import { buildTallyExportSummary, dialogKeyAction } from "@/lib/tallyExportConfirm";
import { formatFiscalPeriod } from "@/lib/formatters";

interface TallyExportModalProps {
  isOpen: boolean;
  status: ReconciliationStatus | null;
  batchId: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export const TallyExportModal: React.FC<TallyExportModalProps> = ({
  isOpen,
  status,
  batchId,
  onConfirm,
  onCancel,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    confirmRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (dialogKeyAction(e.key) === "cancel") {
        e.preventDefault();
        onCancel();
        return;
      }
      if (e.key !== "Tab" || !dialogRef.current) return;
      // Keep Tab inside the dialog while it is open.
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled])");
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const summary = buildTallyExportSummary(status, batchId, formatFiscalPeriod(status?.last_reconciled_at));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-3 sm:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tally-export-title"
        className="bg-[#0c0e12] border border-[#1e222d] rounded-xl max-w-md w-full overflow-hidden shadow-2xl"
      >
        <div className="p-4 bg-[#111318] border-b border-[#1e222d]">
          <h3 id="tally-export-title" className="text-sm font-semibold text-neutral-100 font-sans">
            Export Tally XML Vouchers
          </h3>
        </div>
        <dl className="p-4 space-y-2 text-xs font-sans">
          {summary.rows.map((row) => (
            <div key={row.label} className="flex items-baseline justify-between gap-4">
              <dt className="text-neutral-400">{row.label}</dt>
              <dd className="text-neutral-100 font-mono text-right">{row.value}</dd>
            </div>
          ))}
          <div className="flex items-baseline justify-between gap-4 pt-2 border-t border-[#1e222d]">
            <dt className="text-neutral-400">File</dt>
            <dd className="text-neutral-100 font-mono text-right break-all">{summary.fileName}</dd>
          </div>
        </dl>
        <div className="p-4 pt-0 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-md text-xs font-medium border border-neutral-700 text-neutral-300 hover:text-white hover:border-neutral-500 transition cursor-pointer"
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className="px-3 py-1.5 rounded-md text-xs font-medium bg-neutral-100 text-neutral-900 hover:bg-white transition cursor-pointer"
          >
            Confirm &amp; Download XML
          </button>
        </div>
      </div>
    </div>
  );
};
