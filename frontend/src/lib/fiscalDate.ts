export const INDIA_TIMEZONE = "Asia/Kolkata";

export interface DatePartsIST {
  year: number;
  month: number; // 1 - 12
  day: number; // 1 - 31
}

export interface FiscalQuarterInfo {
  quarter: "Q1" | "Q2" | "Q3" | "Q4";
  quarterNumber: 1 | 2 | 3 | 4;
  fyStartYear: number;
  fyEndYear: number;
  fyLabel: string; // e.g. "FY 26-27"
  quarterLabel: string; // e.g. "Q1 (Apr–Jun)"
  fullLabel: string; // e.g. "Q1 (Apr–Jun) FY 26-27"
  fromDate: string; // YYYY-MM-DD
  toDate: string; // YYYY-MM-DD
}

export type DatePresetKey = "CURRENT_QUARTER" | "PREVIOUS_QUARTER" | "LAST_30_DAYS" | "CUSTOM";

/**
 * Extracts year, month (1-12), and day (1-31) in Indian Standard Time (Asia/Kolkata).
 */
export function getDatePartsIST(date?: Date | string | null): DatePartsIST {
  let d = date ? (typeof date === "string" ? new Date(date) : date) : new Date();
  if (isNaN(d.getTime())) d = new Date();

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: INDIA_TIMEZONE,
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(d);

  const year = Number(parts.find((p) => p.type === "year")?.value);
  const month = Number(parts.find((p) => p.type === "month")?.value);
  const day = Number(parts.find((p) => p.type === "day")?.value);

  return { year, month, day };
}

export function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function formatISODateString(year: number, month: number, day: number): string {
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

/**
 * Returns today's ISO date string (YYYY-MM-DD) in Indian Standard Time.
 */
export function getTodayIST(refDate?: Date | string | null): string {
  const { year, month, day } = getDatePartsIST(refDate);
  return formatISODateString(year, month, day);
}

const twoDigits = (n: number) => String(n % 100).padStart(2, "0");

/**
 * Computes Indian Fiscal Quarter info for any given quarter number and FY start year.
 * Indian Financial Year:
 * - Q1: April 1 – June 30
 * - Q2: July 1 – September 30
 * - Q3: October 1 – December 31
 * - Q4: January 1 – March 31
 */
function buildQuarterInfo(quarterNum: 1 | 2 | 3 | 4, fyStartYear: number): FiscalQuarterInfo {
  const fyEndYear = fyStartYear + 1;
  const fyLabel = `FY ${twoDigits(fyStartYear)}-${twoDigits(fyEndYear)}`;

  switch (quarterNum) {
    case 1:
      return {
        quarter: "Q1",
        quarterNumber: 1,
        fyStartYear,
        fyEndYear,
        fyLabel,
        quarterLabel: "Q1 (Apr–Jun)",
        fullLabel: `Q1 (Apr–Jun) ${fyLabel}`,
        fromDate: `${fyStartYear}-04-01`,
        toDate: `${fyStartYear}-06-30`,
      };
    case 2:
      return {
        quarter: "Q2",
        quarterNumber: 2,
        fyStartYear,
        fyEndYear,
        fyLabel,
        quarterLabel: "Q2 (Jul–Sep)",
        fullLabel: `Q2 (Jul–Sep) ${fyLabel}`,
        fromDate: `${fyStartYear}-07-01`,
        toDate: `${fyStartYear}-09-30`,
      };
    case 3:
      return {
        quarter: "Q3",
        quarterNumber: 3,
        fyStartYear,
        fyEndYear,
        fyLabel,
        quarterLabel: "Q3 (Oct–Dec)",
        fullLabel: `Q3 (Oct–Dec) ${fyLabel}`,
        fromDate: `${fyStartYear}-10-01`,
        toDate: `${fyStartYear}-12-31`,
      };
    case 4:
      return {
        quarter: "Q4",
        quarterNumber: 4,
        fyStartYear,
        fyEndYear,
        fyLabel,
        quarterLabel: "Q4 (Jan–Mar)",
        fullLabel: `Q4 (Jan–Mar) ${fyLabel}`,
        fromDate: `${fyEndYear}-01-01`,
        toDate: `${fyEndYear}-03-31`,
      };
  }
}

/**
 * Determines the current Indian Financial Year quarter dynamically for a given reference date (defaults to now).
 */
export function getCurrentIndianQuarter(refDate?: Date | string | null): FiscalQuarterInfo {
  const { year, month } = getDatePartsIST(refDate);

  // Month is 1-12
  if (month >= 4 && month <= 6) {
    // April, May, June -> Q1 of (year)-(year+1)
    return buildQuarterInfo(1, year);
  } else if (month >= 7 && month <= 9) {
    // July, August, September -> Q2 of (year)-(year+1)
    return buildQuarterInfo(2, year);
  } else if (month >= 10 && month <= 12) {
    // October, November, December -> Q3 of (year)-(year+1)
    return buildQuarterInfo(3, year);
  } else {
    // January, February, March -> Q4 of (year-1)-(year)
    return buildQuarterInfo(4, year - 1);
  }
}

/**
 * Determines the previous Indian Financial Year quarter dynamically.
 */
export function getPreviousIndianQuarter(refDate?: Date | string | null): FiscalQuarterInfo {
  const current = getCurrentIndianQuarter(refDate);

  if (current.quarterNumber === 1) {
    // Previous is Q4 of the previous fiscal year
    return buildQuarterInfo(4, current.fyStartYear - 1);
  } else {
    // Previous is (quarterNumber - 1) of the same fiscal year
    const prevQuarterNum = (current.quarterNumber - 1) as 1 | 2 | 3;
    return buildQuarterInfo(prevQuarterNum, current.fyStartYear);
  }
}

/**
 * Computes Last 30 Days in IST from the reference date (defaults to now).
 */
export function getLast30Days(refDate?: Date | string | null): {
  fromDate: string;
  toDate: string;
  label: string;
} {
  const { year, month, day } = getDatePartsIST(refDate);
  const toDate = formatISODateString(year, month, day);

  // Use calendar date in UTC to subtract the preceding 29 days (both endpoints are included) without timezone artifacts
  const anchor = new Date(Date.UTC(year, month - 1, day));
  anchor.setUTCDate(anchor.getUTCDate() - 29);

  const fromDate = formatISODateString(
    anchor.getUTCFullYear(),
    anchor.getUTCMonth() + 1,
    anchor.getUTCDate()
  );

  return {
    fromDate,
    toDate,
    label: "Last 30 Days",
  };
}

const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Compact date format: '15 Aug 2026' or '15 Aug' for pill display
 */
export function formatCompactDate(isoDateStr?: string | null): string {
  if (!isoDateStr) return "--";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDateStr);
  if (!match) return isoDateStr;
  const [, y, m, d] = match;
  const monthName = SHORT_MONTHS[Number(m) - 1] || m;
  return `${Number(d)} ${monthName} ${y}`;
}

export function formatCompactDateShort(isoDateStr?: string | null): string {
  if (!isoDateStr) return "--";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDateStr);
  if (!match) return isoDateStr;
  const [, , m, d] = match;
  const monthName = SHORT_MONTHS[Number(m) - 1] || m;
  return `${Number(d)} ${monthName}`;
}
