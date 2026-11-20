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

export interface CsvColumn {
  index: number;
  name: string;        // original header label from CSV (e.g. "Amount")
  key: string;         // unique index-based identifier (e.g. "0", "1", "2")
  label: string;       // display label (e.g. "Amount (Col 3)" if duplicate, or "Amount")
}

export interface DetectedCsvInfo {
  headers: string[];   // labels for display and backward compatibility
  columns: CsvColumn[]; // column descriptors with index-based identities
  dataRows: Record<string, string>[];
  rawRows: string[][];
  headerIndex: number;
}

/**
 * Robust RFC4180-compliant CSV record parser.
 * Correctly parses multi-line quoted fields with embedded newlines,
 * commas inside quotes, escaped quotes (""), and CRLF/LF line endings.
 */
export function parseCsvLines(text: string, maxRecords: number = 60): string[][] {
  const records: string[][] = [];
  const cleanText = text.replace(/^\uFEFF/, "");
  if (!cleanText.trim()) return [];

  const len = cleanText.length;
  let currentRecord: string[] = [];
  let currentField = "";
  let inQuotes = false;
  let i = 0;

  while (i < len && records.length < maxRecords) {
    const char = cleanText[i];

    if (char === '"') {
      if (inQuotes && i + 1 < len && cleanText[i + 1] === '"') {
        currentField += '"';
        i += 2;
        continue;
      } else {
        inQuotes = !inQuotes;
        i++;
        continue;
      }
    }

    if (char === "," && !inQuotes) {
      currentRecord.push(currentField.trim());
      currentField = "";
      i++;
      continue;
    }

    if ((char === "\r" || char === "\n") && !inQuotes) {
      if (char === "\r" && i + 1 < len && cleanText[i + 1] === "\n") {
        i++;
      }
      currentRecord.push(currentField.trim());
      currentField = "";
      if (currentRecord.some((f) => f.length > 0)) {
        records.push(currentRecord);
      }
      currentRecord = [];
      i++;
      continue;
    }

    currentField += char;
    i++;
  }

  // Handle trailing record
  if (currentField.length > 0 || currentRecord.length > 0) {
    currentRecord.push(currentField.trim());
    if (currentRecord.some((f) => f.length > 0) && records.length < maxRecords) {
      records.push(currentRecord);
    }
  }

  return records;
}

/**
 * Scans initial rows (up to 30 lines, aligning with backend limit)
 * to detect table header (skipping preamble) and extracts sample rows.
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

  // Scan up to line 30 to align with backend preamble scanning limit
  for (let i = 0; i < Math.min(rows.length, 30); i++) {
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
    for (let i = 0; i < Math.min(rows.length, 30); i++) {
      if (rows[i].filter((c) => c.trim().length > 0).length >= 2) {
        bestIdx = i;
        break;
      }
    }
  }

  if (bestIdx === -1) return null;

  const rawHeaders = rows[bestIdx];

  // Count occurrences of each name to detect duplicates
  const nameCounts: Record<string, number> = {};
  rawHeaders.forEach((h) => {
    const norm = (h.trim() || "Column").toLowerCase();
    nameCounts[norm] = (nameCounts[norm] || 0) + 1;
  });

  const seenCounts: Record<string, number> = {};
  const columns: CsvColumn[] = rawHeaders.map((h, idx) => {
    let name = h.trim();
    if (!name) name = `Column_${idx + 1}`;
    const norm = name.toLowerCase();
    seenCounts[norm] = (seenCounts[norm] || 0) + 1;
    const isDuplicate = (nameCounts[norm] || 0) > 1;
    const label = isDuplicate ? `${name} (Col ${idx + 1})` : name;
    return {
      index: idx,
      name,
      key: String(idx),
      label,
    };
  });

  const headers = columns.map((c) => c.label);

  const rawData = rows.slice(bestIdx + 1);
  const dataRows: Record<string, string>[] = [];
  for (const r of rawData) {
    if (!r.some((cell) => cell.trim().length > 0)) continue;
    const rowObj: Record<string, string> = {};
    columns.forEach((col) => {
      const val = r[col.index] !== undefined ? r[col.index].trim() : "";
      rowObj[col.key] = val;    // accessible by unique key "0", "1", "2"
      rowObj[col.name] = val;   // accessible by name
      rowObj[col.label] = val;  // accessible by label
    });
    dataRows.push(rowObj);
  }

  return {
    headers,
    columns,
    dataRows,
    rawRows: rows,
    headerIndex: bestIdx,
  };
}

/**
 * Returns true if CSV matches standard banking schemas (HDFC, ICICI, SBI, standard generic)
 * with high confidence, allowing automatic bypass of the mapping dialog.
 */
export function isStandardBankStatement(headersOrCols: (string | CsvColumn)[]): boolean {
  const lowerHeaders = headersOrCols.map((h) =>
    (typeof h === "string" ? h : h.name).toLowerCase().trim()
  );

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
 * Sorts column names to remain stable across column order while preserving duplicate headers.
 */
export function computeHeaderSignature(headersOrCols: (string | CsvColumn)[]): string {
  const normalized = headersOrCols
    .map((h) => (typeof h === "string" ? h : h.name).trim().toLowerCase())
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
 * Uses word-boundary matching for short tokens (cr, dr, ref, utr) so that
 * headers like "Description" are NEVER erroneously matched to credit/amount.
 */
export function guessColumnMappings(headersOrCols: (string | CsvColumn)[]): ColumnMappings {
  const isStringArray = headersOrCols.length > 0 && typeof headersOrCols[0] === "string";
  const columns: CsvColumn[] = headersOrCols.map((item, idx) => {
    if (typeof item === "string") {
      return { index: idx, name: item, key: String(idx), label: item };
    }
    return item;
  });

  const findMatch = (candidates: string[]): CsvColumn | undefined => {
    // 1. Exact match (case-insensitive)
    for (const c of candidates) {
      const match = columns.find((col) => col.name.trim().toLowerCase() === c.toLowerCase());
      if (match) return match;
    }
    // 2. Token / word boundary match (prevents "cr" matching inside "Description")
    for (const c of candidates) {
      const escaped = c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const regex = new RegExp(`(^|[^a-zA-Z0-9])${escaped}([^a-zA-Z0-9]|$)`, "i");
      const match = columns.find((col) => regex.test(col.name));
      if (match) return match;
    }
    // 3. Substring match only for longer candidates (length > 3 and not short tokens)
    for (const c of candidates) {
      if (c.length > 3 && !["ref", "utr", "chq", "cr", "dr"].includes(c.toLowerCase())) {
        const match = columns.find((col) => col.name.toLowerCase().includes(c.toLowerCase()));
        if (match) return match;
      }
    }
    return undefined;
  };

  const dateCol = findMatch([
    "date", "txn date", "transaction date", "tran date", "value date", "booking date", "posting date"
  ]);

  const narrationCol = findMatch([
    "narration", "description", "transaction remarks", "particulars", "remarks", "details", "narrative", "memo"
  ]);

  const depositCol = findMatch([
    "deposit amt.", "deposit amt", "deposit amount", "deposit", "credit", "cr amount", "paid in", "cr"
  ]);

  const withdrawalCol = findMatch([
    "withdrawal amt.", "withdrawal amt", "withdrawal amount", "withdrawal", "debit", "dr amount", "paid out", "dr"
  ]);

  const genericAmountCol = findMatch([
    "amount", "net amount", "txn amount", "transaction amount", "total amount"
  ]);

  const amountCol = depositCol || genericAmountCol || withdrawalCol || (columns.length > 2 ? columns[2] : columns[0]);

  const refCol = findMatch([
    "chq/ref no.", "ref no", "reference no", "transaction reference number", "utr", "instrument id", "instrument no", "instrument", "cheque no", "chqno", "ref", "rrn", "txn ref no"
  ]);

  const getKeyOrName = (col: CsvColumn | undefined, fallback: CsvColumn | undefined): string => {
    const chosen = col || fallback;
    if (!chosen) return "";
    return isStringArray ? chosen.name : chosen.key;
  };

  return {
    date: getKeyOrName(dateCol, columns[0]),
    narration: getKeyOrName(narrationCol, columns[1]),
    amount: amountCol ? (isStringArray ? amountCol.name : amountCol.key) : "",
    ref: refCol ? (isStringArray ? refCol.name : refCol.key) : "",
    withdrawal: withdrawalCol ? (isStringArray ? withdrawalCol.name : withdrawalCol.key) : "",
  };
}
