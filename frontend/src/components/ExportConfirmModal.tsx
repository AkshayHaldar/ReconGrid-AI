import React, { useEffect, useId, useRef } from "react";
import { X, FileSpreadsheet, Download } from "lucide-react";
import { buildExportSummary } from "@/lib/export-summary";
import { formatFiscalPeriod } from "@/lib/formatters";
import type { ReconciliationStatus } from "@/lib/types";

interface ExportConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Starts the download. The modal closes itself afterwards. */
  onConfirm: () => void;
  batchId: string;
  /** The batch's status. `null` until it has loaded, in which case the counts read "Not loaded yet". */
  status: ReconciliationStatus | null;
  /**
   * The button that opened the dialog, to give focus back to on close. Safari does not focus a
   * button when it is clicked, so `document.activeElement` alone is not a reliable way to find it.
   */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const formatCount = (value: number | null) =>
  value === null ? "Not loaded yet" : value.toLocaleString("en-IN");

export const ExportConfirmModal: React.FC<ExportConfirmModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  batchId,
  status,
  returnFocusRef,
}) => {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  // The parent may pass a new onClose on every render. Reading it through a ref keeps the effect
  // below tied to isOpen only, so focus is not reset (and the opener not re-recorded) on re-render.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!isOpen) return;

    // Remember what had focus so it can be given back on close. The parent's button wins when it
    // passed one, because focus is not always on a button that was just clicked.
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const trigger = returnFocusRef?.current ?? null;
    cancelRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;

      // Keep Tab and Shift+Tab inside the dialog.
      const items = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      } else if (!dialogRef.current?.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      const target = trigger ?? opener;
      if (target && document.contains(target)) target.focus();
    };
  }, [isOpen, returnFocusRef]);

  if (!isOpen) return null;

  const handleConfirm = () => {
    onConfirm();
    onClose();
  };

  const summary = buildExportSummary(status, batchId);
  const rows: Array<{ label: string; value: string; mono?: boolean }> = [
    { label: "Batch ID", value: summary.batchId, mono: true },
    { label: "Fiscal period", value: formatFiscalPeriod(status?.last_reconciled_at) },
    { label: "Matched records", value: formatCount(summary.matchedCount) },
    { label: "Unresolved exceptions & conflicts", value: formatCount(summary.exceptionCount) },
    { label: "File", value: summary.fileName, mono: true },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-3 sm:p-4"
      onMouseDown={(e) => {
        if (e.target !== e.currentTarget) return;
        // Without this the browser moves focus to the page right after we hand it back.
        e.preventDefault();
        onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="bg-[#0c0e12] border border-[#1e222d] rounded-xl max-w-md w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col"
      >
        {/* Header */}
        <div className="p-4 bg-[#111318] border-b border-[#1e222d] flex items-start justify-between gap-3 shrink-0">
          <div className="flex items-start gap-3 min-w-0">
            <div className="p-2 bg-[#151820] border border-[#282e3d] rounded-md text-emerald-400 shrink-0">
              <FileSpreadsheet className="w-4 h-4" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h3 id={titleId} className="text-sm font-semibold text-neutral-100 font-sans">
                Download Reconciliation Audit Workbook
              </h3>
              <p id={descriptionId} className="text-[11px] text-neutral-400 mt-0.5">
                Check what is in the workbook before it downloads.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-neutral-400 hover:text-neutral-200 p-1.5 rounded-md hover:bg-neutral-800 transition cursor-pointer shrink-0"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Summary */}
        <dl className="p-4 space-y-2.5 text-xs font-sans overflow-y-auto touch-scroll">
          {rows.map((row) => (
            <div key={row.label} className="flex items-baseline justify-between gap-4">
              <dt className="text-neutral-400 shrink-0">{row.label}</dt>
              <dd className={`text-neutral-100 text-right break-all ${row.mono ? "font-mono text-[11px]" : "font-medium"}`}>
                {row.value}
              </dd>
            </div>
          ))}
        </dl>

        {/* Actions */}
        <div className="p-4 bg-[#111318] border-t border-[#1e222d] flex flex-col-reverse sm:flex-row sm:justify-end gap-2 text-xs font-sans shrink-0">
          <button
            ref={cancelRef}
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 rounded-md transition text-center cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="px-4 py-2 bg-neutral-100 hover:bg-white text-neutral-900 font-semibold rounded-md shadow-xs transition flex items-center justify-center gap-2 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Download Excel (.xlsx)</span>
          </button>
        </div>
      </div>
    </div>
  );
};
