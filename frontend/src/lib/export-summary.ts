import type { ReconciliationStatus } from "@/lib/types";

/** What the export confirmation dialog shows about the workbook that is about to download. */
export interface ExportSummary {
  batchId: string;
  /** Matches the file the backend sends in `Content-Disposition`. */
  fileName: string;
  /** Rows the Excel "Reconciled Ledger" sheet will hold. `null` until the batch status has loaded. */
  matchedCount: number | null;
  /** Rows on the "Exceptions & Discrepancies" sheet: the workbook counts exceptions and conflicts together. */
  exceptionCount: number | null;
}

/** The backend names the workbook `recongrid_audit_{batch_id}.xlsx`. */
export function exportFileName(batchId: string): string {
  return `recongrid_audit_${batchId}.xlsx`;
}

export function buildExportSummary(
  status: Pick<ReconciliationStatus, "matched_count" | "exception_count" | "conflict_count"> | null | undefined,
  batchId: string
): ExportSummary {
  return {
    batchId,
    fileName: exportFileName(batchId),
    matchedCount: status ? status.matched_count : null,
    exceptionCount: status ? status.exception_count + status.conflict_count : null,
  };
}
