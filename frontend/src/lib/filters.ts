import { ReconciliationRecordItem } from "./types";

export const VALID_STATUS_TABS = [
  "ALL",
  "MATCHED",
  "SUGGESTED",
  "CONFLICT",
  "EXCEPTION",
  "PENDING_SETTLEMENT_DATA",
] as const;

export type StatusTab = (typeof VALID_STATUS_TABS)[number];

export type DatePresetId =
  | "ALL"
  | "THIS_MONTH"
  | "LAST_MONTH"
  | "LAST_7_DAYS"
  | "LAST_30_DAYS"
  | "CUSTOM";

export interface RecordFilterCriteria {
  diagnostic?: string;
  startDate?: string;
  endDate?: string;
  minAmount?: string;
  maxAmount?: string;
}

export interface UrlFilterState {
  status: string;
  q: string;
  diagnostic: string;
  startDate: string;
  endDate: string;
  minAmount: string;
  maxAmount: string;
}

const ISO_DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Validates that a string is a real YYYY-MM-DD calendar date.
 */
export function isValidIsoDate(val: string | null | undefined): boolean {
  if (!val) return false;
  const trimmed = val.trim();
  if (!ISO_DATE_REGEX.test(trimmed)) return false;

  const [yStr, mStr, dStr] = trimmed.split("-");
  const year = Number(yStr);
  const month = Number(mStr);
  const day = Number(dStr);
  const dt = new Date(Date.UTC(year, month - 1, day));

  return (
    dt.getUTCFullYear() === year &&
    dt.getUTCMonth() === month - 1 &&
    dt.getUTCDate() === day
  );
}

/**
 * Formats a Date in local calendar YYYY-MM-DD for HTML date inputs and date keys.
 */
export function formatLocalIsoDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Normalizes a record timestamp / ISO string into a comparable YYYY-MM-DD date key.
 * Calendar-only YYYY-MM-DD dates are preserved as-is.
 * Strings with time/timezone (e.g. 2026-08-10T22:30:00Z) are resolved using
 * formatLocalIsoDate(new Date(trimmed)) so the filter key matches the browser-local
 * date displayed to the user in formatDate().
 */
export function toDateKey(val: string | Date | null | undefined): string | null {
  if (!val) return null;
  if (val instanceof Date) {
    return Number.isNaN(val.getTime()) ? null : formatLocalIsoDate(val);
  }
  const trimmed = typeof val === "string" ? val.trim() : "";
  if (!trimmed) return null;
  if (isValidIsoDate(trimmed)) {
    return trimmed;
  }

  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return null;
  return formatLocalIsoDate(parsed);
}

/**
 * Sanitizes numeric amount inputs, allowing only digits, commas, and at most
 * a single decimal point so invalid patterns like "10.5.0" strip extra dots.
 */
export function sanitizeAmountInput(raw: string): string {
  const cleaned = raw.replace(/[^\d.,]/g, "");
  const dotIndex = cleaned.indexOf(".");
  if (dotIndex === -1) return cleaned;
  return (
    cleaned.slice(0, dotIndex + 1) +
    cleaned.slice(dotIndex + 1).replace(/\./g, "")
  );
}

/**
 * Parses a numeric/INR amount string (handling commas, spaces, and ₹ prefix).
 */
export function parseAmountInput(
  raw: string | number | null | undefined
): number | null {
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number") {
    return Number.isFinite(raw) ? raw : null;
  }
  const cleaned = raw.replace(/[₹,\s]/g, "").trim();
  if (!cleaned) return null;
  const num = Number(cleaned);
  return Number.isFinite(num) ? num : null;
}

/**
 * Returns { startDate, endDate } in YYYY-MM-DD for a quick date preset.
 */
export function getDatePresetRange(
  preset: DatePresetId,
  referenceDate: Date = new Date()
): { startDate: string; endDate: string } {
  if (preset === "ALL" || preset === "CUSTOM") {
    return { startDate: "", endDate: "" };
  }

  const year = referenceDate.getFullYear();
  const month = referenceDate.getMonth();
  const day = referenceDate.getDate();

  if (preset === "THIS_MONTH") {
    const start = new Date(year, month, 1);
    const end = new Date(year, month + 1, 0);
    return {
      startDate: formatLocalIsoDate(start),
      endDate: formatLocalIsoDate(end),
    };
  }

  if (preset === "LAST_MONTH") {
    const start = new Date(year, month - 1, 1);
    const end = new Date(year, month, 0);
    return {
      startDate: formatLocalIsoDate(start),
      endDate: formatLocalIsoDate(end),
    };
  }

  if (preset === "LAST_7_DAYS") {
    const end = new Date(year, month, day);
    const start = new Date(year, month, day - 6);
    return {
      startDate: formatLocalIsoDate(start),
      endDate: formatLocalIsoDate(end),
    };
  }

  // LAST_30_DAYS
  const end = new Date(year, month, day);
  const start = new Date(year, month, day - 29);
  return {
    startDate: formatLocalIsoDate(start),
    endDate: formatLocalIsoDate(end),
  };
}

/**
 * Infers which preset corresponds to a given startDate/endDate pair.
 */
export function detectDatePreset(
  startDate: string,
  endDate: string,
  referenceDate: Date = new Date()
): DatePresetId {
  if (!startDate && !endDate) return "ALL";

  const presets: Exclude<DatePresetId, "ALL" | "CUSTOM">[] = [
    "THIS_MONTH",
    "LAST_MONTH",
    "LAST_7_DAYS",
    "LAST_30_DAYS",
  ];

  for (const preset of presets) {
    const range = getDatePresetRange(preset, referenceDate);
    if (range.startDate === startDate && range.endDate === endDate) {
      return preset;
    }
  }

  return "CUSTOM";
}

/**
 * Reactively filters reconciliation records by diagnostic, date range (r.date),
 * and transaction amount range (r.bank_amount).
 */
export function filterReconciliationRecords(
  records: ReconciliationRecordItem[],
  criteria: RecordFilterCriteria
): ReconciliationRecordItem[] {
  const diagnostic = criteria.diagnostic || "ALL";
  const start = isValidIsoDate(criteria.startDate)
    ? criteria.startDate!.trim()
    : "";
  const end = isValidIsoDate(criteria.endDate) ? criteria.endDate!.trim() : "";
  const minVal = parseAmountInput(criteria.minAmount);
  const maxVal = parseAmountInput(criteria.maxAmount);

  return records.filter((r) => {
    if (diagnostic !== "ALL" && r.diagnostic_type !== diagnostic) {
      return false;
    }

    if (start || end) {
      const recordDateKey = toDateKey(r.date);
      if (!recordDateKey) return false;
      if (start && recordDateKey < start) return false;
      if (end && recordDateKey > end) return false;
    }

    if (minVal !== null || maxVal !== null) {
      const bankAmount = parseAmountInput(r.bank_amount);
      if (bankAmount === null) return false;
      if (minVal !== null && bankAmount < minVal) return false;
      if (maxVal !== null && bankAmount > maxVal) return false;
    }

    return true;
  });
}

/**
 * Parses URL search parameters into validated initial filter state.
 */
export function parseFilterSearchParams(
  searchParams: { get(name: string): string | null }
): UrlFilterState {
  const rawStatus = (searchParams.get("status") || "ALL").toUpperCase();
  const status = (VALID_STATUS_TABS as readonly string[]).includes(rawStatus)
    ? rawStatus
    : "ALL";

  const q = searchParams.get("q") || "";
  const diagnostic = searchParams.get("diagnostic") || "ALL";

  const rawStart = searchParams.get("startDate");
  const startDate = isValidIsoDate(rawStart) ? rawStart!.trim() : "";

  const rawEnd = searchParams.get("endDate");
  const endDate = isValidIsoDate(rawEnd) ? rawEnd!.trim() : "";

  const rawMin = searchParams.get("minAmount") || "";
  const minAmount = parseAmountInput(rawMin) !== null ? rawMin.trim() : "";

  const rawMax = searchParams.get("maxAmount") || "";
  const maxAmount = parseAmountInput(rawMax) !== null ? rawMax.trim() : "";

  return {
    status,
    q,
    diagnostic,
    startDate,
    endDate,
    minAmount,
    maxAmount,
  };
}

/**
 * Serializes active filter state into clean URL search params.
 */
export function buildFilterSearchParams(state: UrlFilterState): URLSearchParams {
  const params = new URLSearchParams();

  const cleanQ = state.q.trim();
  const hasStart = isValidIsoDate(state.startDate);
  const hasEnd = isValidIsoDate(state.endDate);
  const hasMin = parseAmountInput(state.minAmount) !== null;
  const hasMax = parseAmountInput(state.maxAmount) !== null;
  const hasDiagnostic = Boolean(state.diagnostic && state.diagnostic !== "ALL");

  const hasAnyFilter =
    state.status !== "ALL" ||
    Boolean(cleanQ) ||
    hasDiagnostic ||
    hasStart ||
    hasEnd ||
    hasMin ||
    hasMax;

  if (!hasAnyFilter) {
    return params;
  }

  params.set("status", state.status || "ALL");

  if (cleanQ) {
    params.set("q", cleanQ);
  }
  if (hasDiagnostic) {
    params.set("diagnostic", state.diagnostic);
  }
  if (hasStart) {
    params.set("startDate", state.startDate.trim());
  }
  if (hasEnd) {
    params.set("endDate", state.endDate.trim());
  }
  if (hasMin) {
    params.set("minAmount", state.minAmount.replace(/[₹,\s]/g, "").trim());
  }
  if (hasMax) {
    params.set("maxAmount", state.maxAmount.replace(/[₹,\s]/g, "").trim());
  }

  return params;
}
