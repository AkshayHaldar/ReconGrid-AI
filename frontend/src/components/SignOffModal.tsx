import React, { useEffect, useState } from "react";
import { X, Lock, CheckCircle2, XCircle, Loader2, ShieldCheck } from "lucide-react";
import { fetchLockStatus, lockBatch } from "@/lib/api";
import { formatINR, formatPeriodLabel } from "@/lib/formatters";
import { PreflightResult } from "@/lib/types";

interface SignOffModalProps {
  isOpen: boolean;
  onClose: () => void;
  batchId: string;
  /** Date of the batch, used for the period name in the title. */
  periodDate?: string | Date | null;
  /** Called after the batch was locked, so the dashboard can reload its status. */
  onLocked: () => void;
}

/**
 * Pre-flight audit checklist plus sign-off form for the month-end close.
 * The checks come from the API (the same ones POST /lock enforces), so the modal never decides
 * on its own that a period can be closed.
 */
export const SignOffModal: React.FC<SignOffModalProps> = ({ isOpen, onClose, batchId, periodDate, onLocked }) => {
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lockedBy, setLockedBy] = useState("");
  const [lockNote, setLockNote] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !submitting) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, submitting]);

  // Re-run the checks every time the modal opens: the ledger may have changed since last time.
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setSubmitError(null);
    setAcknowledged(false);
    setPreflight(null);
    fetchLockStatus(batchId)
      .then((s) => {
        if (cancelled) return;
        if (s.is_locked) {
          // Someone else closed it in the meantime.
          onLocked();
          onClose();
          return;
        }
        setPreflight(s.preflight ?? null);
      })
      .catch(() => !cancelled && setLoadError("Could not run the pre-flight checks. Please retry."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, batchId]);

  if (!isOpen) return null;

  const signerOk = lockedBy.trim().length >= 2;
  const canConfirm = Boolean(preflight?.can_lock) && signerOk && acknowledged && !submitting;

  const handleConfirm = async () => {
    if (!canConfirm) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await lockBatch(batchId, lockedBy.trim(), lockNote.trim());
      onLocked();
      onClose();
    } catch (err: any) {
      setSubmitError(err?.message || "Failed to sign off the period.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="signoff-title"
    >
      <div className="bg-[#0c0e12] border border-[#1e222d] rounded-xl max-w-lg w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e222d] shrink-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-neutral-300" />
            <h3 id="signoff-title" className="text-sm font-semibold text-neutral-100 font-sans">
              Close &amp; Sign Off Period ({formatPeriodLabel(periodDate)})
            </h3>
          </div>
          <button
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
            className="p-1 text-neutral-400 hover:text-neutral-200 rounded-md hover:bg-neutral-800 transition cursor-pointer disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto">
          <p className="text-xs text-neutral-400 leading-relaxed">
            Closing freezes the ledger for this period. Approvals, denials, conflict resolutions and new uploads are
            rejected afterwards. This cannot be undone from the dashboard.
          </p>

          {/* Pre-flight checklist */}
          <div>
            <div className="text-[10px] uppercase font-semibold text-neutral-400 mb-1.5 tracking-wide">
              Pre-flight audit checks
            </div>
            {loading && (
              <div className="flex items-center gap-2 text-xs text-neutral-400 py-2" role="status">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Running checks...
              </div>
            )}
            {loadError && (
              <div role="alert" className="text-xs text-rose-300">
                {loadError}
              </div>
            )}
            {preflight && (
              <ul className="space-y-1.5" data-testid="preflight-checks">
                {preflight.checks.map((c) => (
                  <li
                    key={c.id}
                    className={`flex items-start gap-2 px-2.5 py-2 rounded border text-xs ${
                      c.passed
                        ? "bg-emerald-950/20 border-emerald-900/50 text-emerald-200"
                        : "bg-rose-950/20 border-rose-900/50 text-rose-200"
                    }`}
                  >
                    {c.passed ? (
                      <CheckCircle2 className="w-4 h-4 mt-px shrink-0 text-emerald-400" />
                    ) : (
                      <XCircle className="w-4 h-4 mt-px shrink-0 text-rose-400" />
                    )}
                    <div className="min-w-0">
                      <div className="font-medium">{c.label}</div>
                      <div className="text-[11px] opacity-80">{c.detail}</div>
                    </div>
                  </li>
                ))}
                <li className="text-[11px] font-mono text-neutral-400 px-1">
                  Trial balance difference: {formatINR(preflight.unresolved_variance)}
                </li>
              </ul>
            )}
          </div>

          {/* Sign-off form */}
          <div className="space-y-3">
            <label className="block">
              <span className="text-[11px] text-neutral-300 font-medium">Auditor name and firm (required)</span>
              <input
                value={lockedBy}
                onChange={(e) => setLockedBy(e.target.value)}
                maxLength={255}
                placeholder="CA Ramesh, Partner at ABC & Co."
                className="mt-1 w-full bg-[#111318] border border-[#1e222d] focus:border-neutral-500 rounded-md px-2.5 py-1.5 text-xs text-neutral-100 placeholder:text-neutral-600 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="text-[11px] text-neutral-300 font-medium">Sign-off statement (optional)</span>
              <textarea
                value={lockNote}
                onChange={(e) => setLockNote(e.target.value)}
                maxLength={2000}
                rows={2}
                placeholder="Audited & Approved. GSTR-1 and GSTR-3B filed."
                className="mt-1 w-full bg-[#111318] border border-[#1e222d] focus:border-neutral-500 rounded-md px-2.5 py-1.5 text-xs text-neutral-100 placeholder:text-neutral-600 focus:outline-none resize-none"
              />
            </label>
            <label className="flex items-start gap-2 text-[11px] text-neutral-300 cursor-pointer">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
                className="mt-0.5"
              />
              <span>I confirm this period is audited and the ledger should become read-only.</span>
            </label>
          </div>

          {submitError && (
            <div role="alert" className="text-xs text-rose-300 bg-rose-950/20 border border-rose-900/50 rounded px-2.5 py-2">
              {submitError}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#1e222d] shrink-0">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 rounded text-xs transition cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-100 hover:bg-white text-neutral-900 rounded text-xs font-semibold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />}
            <span>{submitting ? "Signing off..." : "Confirm Close & Lock"}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
