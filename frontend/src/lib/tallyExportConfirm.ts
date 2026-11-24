import type { ReconciliationStatus } from "@/lib/types";

export interface ExportSummaryRow {
  label: string;
  value: string;
}

export interface TallyExportSummary {
  fileName: string;
  rows: ExportSummaryRow[];
}

/** The name the backend gives the Tally download (see the export-tally-xml route). */
export const TALLY_FILE_NAME = "reconciliation_tally_vouchers.xml";

/** The accounting period an Indian fiscal-year label covers, e.g. "FY 26-27". */
export function fiscalYearOf(periodLabel: string): string {
  const match = periodLabel.match(/FY \d{2}-\d{2}/);
  return match ? match[0] : periodLabel;
}

/**
 * What the confirmation dialog shows before the Tally file is generated. The export only posts
 * MATCHED settlements, one journal voucher each, so the matched count is the voucher estimate
 * (a record that cannot be balanced is skipped by the server, hence "up to").
 */
export function buildTallyExportSummary(
  status: Pick<ReconciliationStatus, "matched_count"> | null,
  batchId: string,
  periodLabel: string
): TallyExportSummary {
  const matched = status?.matched_count;
  return {
    fileName: TALLY_FILE_NAME,
    rows: [
      { label: "Batch", value: batchId },
      { label: "Accounting period", value: fiscalYearOf(periodLabel) },
      {
        label: "Journal vouchers (up to)",
        value: typeof matched === "number" ? matched.toLocaleString("en-IN") : "-",
      },
    ],
  };
}

/** Escape closes the dialog without downloading; every other key is left alone. */
export function dialogKeyAction(key: string): "cancel" | null {
  return key === "Escape" ? "cancel" : null;
}
