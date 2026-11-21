import type { ReconciliationStatus } from "@/lib/types";

export interface ExportSummaryRow {
  label: string;
  value: string;
}

export interface ExportSummary {
  fileName: string;
  rows: ExportSummaryRow[];
}

/** The name the backend gives the Excel download (see the export-xlsx route). */
export function excelFileName(batchId: string): string {
  return `recongrid_audit_${batchId}.xlsx`;
}

/**
 * What the confirmation dialog shows before the workbook is generated: which batch, which
 * period, and how many records are in it. The counts come from the status the dashboard has
 * already loaded, so opening the dialog costs no extra request.
 */
export function buildExcelExportSummary(
  status: Pick<ReconciliationStatus, "total_records" | "matched_count" | "exception_count"> | null,
  batchId: string,
  periodLabel: string
): ExportSummary {
  const count = (n?: number) => (typeof n === "number" ? n.toLocaleString("en-IN") : "-");
  return {
    fileName: excelFileName(batchId),
    rows: [
      { label: "Batch", value: batchId },
      { label: "Period", value: periodLabel },
      { label: "Matched records", value: count(status?.matched_count) },
      { label: "Unresolved exceptions", value: count(status?.exception_count) },
      { label: "Total records", value: count(status?.total_records) },
    ],
  };
}

/** Escape closes the dialog without downloading; every other key is left alone. */
export function dialogKeyAction(key: string): "cancel" | null {
  return key === "Escape" ? "cancel" : null;
}
