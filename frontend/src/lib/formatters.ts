/**
 * Formats numbers into standard Indian Rupee currency format (e.g. ₹ 1,42,85,900.00)
 */
export function formatINR(val: string | number | null | undefined): string {
  if (val === null || val === undefined || val === "") return "₹ 0.00";
  const num = typeof val === "string" ? parseFloat(val.replace(/,/g, "")) : val;
  if (isNaN(num)) return "₹ 0.00";

  const isNegative = num < 0;
  const absNum = Math.abs(num);
  const fixed = absNum.toFixed(2);
  const [intPart, decPart] = fixed.split(".");

  let formattedInt = "";
  if (intPart.length <= 3) {
    formattedInt = intPart;
  } else {
    const last3 = intPart.slice(-3);
    const other = intPart.slice(0, -3);
    const groups: string[] = [];
    let rem = other;
    while (rem.length > 2) {
      groups.unshift(rem.slice(-2));
      rem = rem.slice(0, -2);
    }
    if (rem.length > 0) groups.unshift(rem);
    formattedInt = groups.join(",") + "," + last3;
  }

  const result = `₹ ${formattedInt}.${decPart}`;
  return isNegative ? `(${result})` : result;
}

/**
 * Formats amount with accounting CR / DR indicators
 */
export function formatDirectionINR(
  val: string | number | null | undefined,
  direction?: "CREDIT" | "DEBIT"
): string {
  const formatted = formatINR(val);
  if (!direction) return formatted;
  return direction === "DEBIT" ? `${formatted} DR` : `${formatted} CR`;
}

/**
 * Formats standard date into compact CA format: '24 Aug 2026'
 */
export function formatDate(isoStr: string | null | undefined): string {
  if (!isoStr) return "--";
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString("en-IN", {
      month: "short",
      day: "2-digit",
      year: "numeric",
    });
  } catch {
    return isoStr;
  }
}

/**
 * Formats standard date into short format: '24 Aug'
 */
export function formatShortDate(isoStr: string | null | undefined): string {
  if (!isoStr) return "--";
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString("en-IN", {
      month: "short",
      day: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

/**
 * Formats time in IST format: '02:30 PM'
 */
export function formatTime(isoStr: string | null | undefined): string {
  if (!isoStr) return "--";
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

/**
 * Formats a delta math equation for audit drawers and popovers
 */
export function formatFeeEquation(
  gross: string | number | null | undefined,
  fee: string | number | null | undefined,
  tax: string | number | null | undefined,
  net: string | number | null | undefined
): string {
  return `Gross ${formatINR(gross)} - Fee ${formatINR(fee)} - GST (18%) ${formatINR(tax)} = Net ${formatINR(net)}`;
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const INDIA_TIME_ZONE = "Asia/Kolkata";

/**
 * The accounting period shown in the header, in the Indian fiscal year (April to March):
 * 'Aug 2026 Close (FY 26-27)'. Uses the given date, or today when it is missing or unreadable.
 *
 * The month and year are read in India's time zone, not the viewer's, so one date gives one label
 * wherever it is viewed (and on the server as well as in the browser).
 */
export function formatFiscalPeriod(date?: string | Date | null): string {
  let d = date ? new Date(date) : new Date();
  if (isNaN(d.getTime())) d = new Date();

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: INDIA_TIME_ZONE,
    year: "numeric",
    month: "numeric",
  }).formatToParts(d);
  const year = Number(parts.find((p) => p.type === "year")?.value);
  const month = Number(parts.find((p) => p.type === "month")?.value) - 1;

  const startYear = month >= 3 ? year : year - 1;
  const twoDigits = (n: number) => String(n % 100).padStart(2, "0");

  return `${MONTH_NAMES[month]} ${year} Close (FY ${twoDigits(startYear)}-${twoDigits(startYear + 1)})`;
}
