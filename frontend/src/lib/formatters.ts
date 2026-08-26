/**
 * Formats numbers into Indian Rupee currency format (e.g. ₹ 1,42,85,900.00)
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
