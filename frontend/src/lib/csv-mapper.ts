/**
 * CSV parsing, schema detection, and column mapping utilities for custom bank statements.
 */

export interface ColumnMappings {
  date: string;
  narration: string;
  amount: string;
  ref?: string;
  withdrawal?: string;
}

export interface DetectedCsvInfo {
  headers: string[];
  dataRows: Record<string, string>[];
  rawRows: string[][];
  headerIndex: number;
}

/**
 * Lightweight RFC4180-compliant CSV line parser.
 * Handles quoted fields, embedded commas, and escaped quotes without external dependencies.
 */
export function parseCsvLines(text: string, maxLines: number = 50): string[][] {
  const rows: string[][] = [];
  const lines = text.split(/\r?\n/);

  for (const line of lines) {
    if (rows.length >= maxLines) break;
    const cleanLine = line.replace(/^\uFEFF/, "").trim();
    if (!cleanLine) continue;

    const fields: string[] = [];
    let current = "";
    let inQuotes = false;

    for (let i = 0; i < cleanLine.length; i++) {
      const char = cleanLine[i];
      if (char === '"') {
        if (inQuotes && cleanLine[i + 1] === '"') {
          current += '"';
          i++; // skip escaped quote
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === "," && !inQuotes) {
        fields.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    fields.push(current.trim());
    if (fields.length > 0 && fields.some((f) => f.length > 0)) {
      rows.push(fields);
    }
  }

  return rows;
}

/**
 * Scans initial rows to detect table header (skipping preamble) and extracts sample rows.
 */
export function detectCsvHeaderAndRows(rows: string[][]): DetectedCsvInfo | null {
  if (!rows || rows.length === 0) return null;

  const headerKeywords = [
    "date", "txn", "transaction", "tran", "value date",
    "description", "narration", "particulars", "remarks",
    "amount", "deposit", "withdrawal", "credit", "debit", "balance",
    "ref", "utr", "chq", "cheque", "instrument"
  ];

  let bestIdx = -1;
  let bestScore = -1;

  for (let i = 0; i < Math.min(rows.length, 25); i++) {
    const row = rows[i];
    if (row.length < 2) continue;
    let score = 0;
    for (const col of row) {
      const lower = col.toLowerCase().trim();
      if (!lower) continue;
      for (const kw of headerKeywords) {
        if (lower.includes(kw)) {
          score++;
          break;
        }
      }
    }
    const nonEmpty = row.filter((c) => c.trim().length > 0).length;
    if (nonEmpty >= 2 && score > bestScore) {
      bestScore = score;
      bestIdx = i;
    }
  }

  // Fallback to first row with >= 2 columns if no keywords found
  if (bestIdx === -1) {
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].filter((c) => c.trim().length > 0).length >= 2) {
        bestIdx = i;
        break;
      }
    }
  }

  if (bestIdx === -1) return null;

  const rawHeaders = rows[bestIdx];
  const seen: Record<string, number> = {};
  const headers = rawHeaders.map((h, idx) => {
    let name = h.trim();
    if (!name) name = `Column_${idx + 1}`;
    if (seen[name]) {
      seen[name]++;
      return `${name}_${seen[name]}`;
    }
    seen[name] = 1;
    return name;
  });

  const rawData = rows.slice(bestIdx + 1);
  const dataRows: Record<string, string>[] = [];
  for (const r of rawData) {
    if (!r.some((cell) => cell.trim().length > 0)) continue;
    const rowObj: Record<string, string> = {};
    headers.forEach((h, colIdx) => {
      rowObj[h] = r[colIdx] !== undefined ? r[colIdx].trim() : "";
    });
    dataRows.push(rowObj);
  }

  return {
    headers,
    dataRows,
    rawRows: rows,
    headerIndex: bestIdx,
  };
}

/**
 * Returns true if CSV matches standard banking schemas (HDFC, ICICI, SBI, standard generic)
 * with high confidence, allowing automatic bypass of the mapping dialog.
 */
export function isStandardBankStatement(headers: string[]): boolean {
  const lowerHeaders = headers.map((h) => h.toLowerCase().trim());

  // HDFC pattern: Date, Chq/Ref No., Narration, Deposit Amt., Withdrawal Amt.
  const isHdfc =
    lowerHeaders.some((h) => h === "date" || h === "txn date") &&
    lowerHeaders.some((h) => h.includes("deposit")) &&
    lowerHeaders.some((h) => h.includes("narration") || h.includes("description"));

  // ICICI pattern: Transaction Date, Transaction Reference Number, Transaction Remarks, Deposit Amount, Withdrawal Amount
  const isIcici =
    lowerHeaders.some((h) => h.includes("transaction date")) &&
    lowerHeaders.some((h) => h.includes("transaction remarks") || h.includes("remarks")) &&
    lowerHeaders.some((h) => h.includes("deposit amount") || h.includes("withdrawal amount"));

  // SBI pattern: Txn Date, Ref No./Cheque No., Description, Credit, Debit
  const isSbi =
    lowerHeaders.some((h) => h.includes("txn date") || h.includes("txn_date")) &&
    lowerHeaders.some((h) => h.includes("description") || h.includes("narration")) &&
    lowerHeaders.some((h) => h.includes("credit") || h.includes("debit"));

  // Generic standard schema: explicit standard date, narration, and amount
  const hasDate = lowerHeaders.some((h) => h === "date" || h === "txn_date" || h === "transaction_date");
  const hasNarration = lowerHeaders.some((h) => h === "narration" || h === "description" || h === "remarks");
  const hasAmount = lowerHeaders.some(
    (h) => h === "amount" || h === "net_amount" || (lowerHeaders.includes("credit") && lowerHeaders.includes("debit"))
  );

  const isGenericStandard = hasDate && hasNarration && hasAmount;

  return isHdfc || isIcici || isSbi || isGenericStandard;
}

/**
 * Deterministic hash of CSV headers for localStorage caching.
 */
export function computeHeaderSignature(headers: string[]): string {
  const normalized = headers
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean)
    .sort()
    .join("|");

  let hash = 0;
  for (let i = 0; i < normalized.length; i++) {
    hash = (hash << 5) - hash + normalized.charCodeAt(i);
    hash |= 0;
  }
  return `recongrid_csv_mapping_${Math.abs(hash).toString(16)}`;
}

/**
 * Best-effort heuristic to guess canonical column roles from header names.
 */
export function guessColumnMappings(headers: string[]): ColumnMappings {
  const findMatch = (candidates: string[]): string => {
    // 1. exact match
    for (const c of candidates) {
      const match = headers.find((h) => h.toLowerCase().trim() === c.toLowerCase());
      if (match) return match;
    }
    // 2. substring match
    for (const c of candidates) {
      const match = headers.find((h) => h.toLowerCase().includes(c.toLowerCase()));
      if (match) return match;
    }
    return "";
  };

  const date = findMatch([
    "date", "txn date", "transaction date", "tran date", "value date", "booking date", "posting date"
  ]);

  const narration = findMatch([
    "narration", "description", "transaction remarks", "particulars", "remarks", "details", "narrative", "memo"
  ]);

  const deposit = findMatch([
    "deposit amt.", "deposit amt", "deposit amount", "deposit", "credit", "cr", "paid in", "cr amount"
  ]);
  const withdrawal = findMatch([
    "withdrawal amt.", "withdrawal amt", "withdrawal amount", "withdrawal", "debit", "dr", "paid out", "dr amount"
  ]);
  const genericAmount = findMatch([
    "amount", "net amount", "txn amount", "transaction amount", "total amount"
  ]);

  const amount = deposit || genericAmount || withdrawal || (headers.length > 2 ? headers[2] : headers[0] || "");

  const ref = findMatch([
    "chq/ref no.", "ref no", "reference no", "transaction reference number", "utr", "instrument id", "cheque no", "chqno", "ref", "rrn", "txn ref no"
  ]);

  return {
    date: date || (headers.length > 0 ? headers[0] : ""),
    narration: narration || (headers.length > 1 ? headers[1] : ""),
    amount: amount || "",
    ref: ref || "",
    withdrawal: withdrawal || "",
  };
}
