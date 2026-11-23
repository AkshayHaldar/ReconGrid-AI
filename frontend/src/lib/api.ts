import {
  ApiResponse,
  BatchLockStatus,
  GatewayHealth,
  QaAskResponse,
  ReconciliationRecordItem,
  ReconciliationStatus,
  TaxSchedule,
  WebhookEventItem,
} from "./types";

/**
 * Resolves the API base URL depending on execution environment:
 * - Server functions/SSR: Reads BACKEND_URL injected by Vercel service binding.
 * - Browser / Client: Defaults to relative path "/api/v1" to route through Vercel's rewrites on the same domain without CORS.
 * - Local fallback: http://127.0.0.1:8000/api/v1
 */
export function getApiBase(): string {
  if (typeof window === "undefined") {
    const backendUrl = process.env.BACKEND_URL;
    if (backendUrl) {
      return `${backendUrl.replace(/\/$/, "")}/api/v1`;
    }
    return process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000/api/v1";
  }
  return process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "/api/v1";
}

export const API_BASE = getApiBase();

export type LedgerSort = "date" | "bank_amount" | "rzp_amount" | "delta_amount" | "bank_utr";
export interface RecordQuery {
  batchId: string;
  status: string;
  search: string;
  diagnostic: string;
  sort: LedgerSort;
  direction: "asc" | "desc";
  settlementId?: string;
  fromDate?: string;
  toDate?: string;
  from_date?: string;
  to_date?: string;
}
export interface RecordWindow {
  records: ReconciliationRecordItem[];
  total_count: number | null;
  next_cursor: string | null;
  has_more: boolean;
}

export async function fetchRecordWindow(
  query: RecordQuery, cursor: string | null = null,
  signal?: AbortSignal, anchorId?: string,
): Promise<RecordWindow> {
  const params = new URLSearchParams({
    limit: "200", status: query.status, q: query.search,
    diagnostic: query.diagnostic, sort: query.sort, direction: query.direction,
  });
  if (cursor) params.set("cursor", cursor);
  if (anchorId) params.set("anchor_id", anchorId);
  if (query.settlementId) params.set("settlement_id", query.settlementId);
  const fromDate = query.fromDate || query.from_date;
  const toDate = query.toDate || query.to_date;
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  const response = await fetch(`${getApiBase()}/reconciliation/${encodeURIComponent(query.batchId)}/records?${params}`, {
    cache: "no-store", signal,
  });
  if (!response.ok) throw new Error("Unable to load ledger records. Please retry.");
  return (await response.json()).data;
}

// Only used for explicit whole-selection actions, never the initial ledger load.
export async function collectRecordWindows(query: RecordQuery): Promise<ReconciliationRecordItem[]> {
  const records: ReconciliationRecordItem[] = [];
  const visited = new Set<string>();
  let cursor: string | null = null;
  do {
    const page = await fetchRecordWindow(query, cursor);
    records.push(...page.records);
    if (!page.has_more) return records;
    if (!page.next_cursor || visited.has(page.next_cursor)) throw new Error("Ledger cursor did not advance");
    cursor = page.next_cursor;
    visited.add(cursor);
  } while (true);
}

export async function fetchStatus(batchId: string = "default"): Promise<ReconciliationStatus> {
  const base = getApiBase();
  const res = await fetch(`${base}/reconciliation/${batchId}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch reconciliation status");
  const json: ApiResponse<ReconciliationStatus> = await res.json();
  return json.data;
}

/** The batch was signed off: the API answers 423 Locked to any write. */
export class BatchLockedError extends Error {
  code = "BATCH_LOCKED";
  constructor(message = "This period is locked and signed off. The ledger is read-only.") {
    super(message);
    this.name = "BatchLockedError";
  }
}

/** Throws BatchLockedError for HTTP 423, otherwise the given generic message. */
function failedWrite(res: Response, fallback: string): Error {
  return res.status === 423 ? new BatchLockedError() : new Error(fallback);
}

export async function fetchLockStatus(batchId: string = "default"): Promise<BatchLockStatus> {
  const res = await fetch(`${getApiBase()}/reconciliation/${encodeURIComponent(batchId)}/lock`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load period close checks");
  const json: ApiResponse<BatchLockStatus> = await res.json();
  return json.data;
}

/** Close and sign off the period. Rejects with the server's message when pre-flight fails. */
export async function lockBatch(
  batchId: string,
  lockedBy: string,
  lockNote?: string
): Promise<BatchLockStatus> {
  const res = await fetch(`${getApiBase()}/reconciliation/${encodeURIComponent(batchId)}/lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ locked_by: lockedBy, lock_note: lockNote || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const error = new Error(err.error?.message || "Failed to sign off the period");
    (error as any).code = err.error?.code;
    throw error;
  }
  const json: ApiResponse<BatchLockStatus> = await res.json();
  return json.data;
}

export async function fetchTaxSchedule(batchId: string = "default", intraState: boolean = true): Promise<TaxSchedule> {
  const base = getApiBase();
  const res = await fetch(`${base}/reconciliation/${batchId}/tax-schedule?intra_state=${intraState}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch tax schedule");
  const json: ApiResponse<TaxSchedule> = await res.json();
  return json.data;
}

export function taxScheduleExportUrl(batchId: string = "default", intraState: boolean = true): string {
  return `${getApiBase()}/reconciliation/${batchId}/tax-schedule/export?intra_state=${intraState}`;
}

export async function fetchRecords(
  batchId: string = "default",
  status: string = "ALL",
  search: string = "",
  page: number = 1,
  pageSize: number = 100,
  fromDate?: string,
  toDate?: string
): Promise<{ records: ReconciliationRecordItem[]; total_count: number }> {
  const params = new URLSearchParams({
    status,
    q: search,
    page: page.toString(),
    page_size: pageSize.toString(),
  });
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  const res = await fetch(`${getApiBase()}/reconciliation/${batchId}/records?${params}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch reconciliation records");
  const json = await res.json();
  return json.data;
}

export interface FetchReconciliationRecordsOptions {
  batchId?: string;
  status?: string;
  search?: string;
  page?: number;
  pageSize?: number;
  fromDate?: string;
  toDate?: string;
  from_date?: string;
  to_date?: string;
}

export async function fetchReconciliationRecords(
  batchIdOrOptions: string | FetchReconciliationRecordsOptions = "default",
  status: string = "ALL",
  search: string = "",
  page: number = 1,
  pageSize: number = 100,
  fromDate?: string,
  toDate?: string
): Promise<{ records: ReconciliationRecordItem[]; total_count: number }> {
  if (typeof batchIdOrOptions === "object" && batchIdOrOptions !== null) {
    const opts = batchIdOrOptions;
    return fetchRecords(
      opts.batchId || "default",
      opts.status || "ALL",
      opts.search || "",
      opts.page || 1,
      opts.pageSize || 100,
      opts.fromDate || opts.from_date,
      opts.toDate || opts.to_date
    );
  }
  return fetchRecords(batchIdOrOptions, status, search, page, pageSize, fromDate, toDate);
}

// The API caps page_size at 200. Walk every page so the (virtualized) ledger
// can show the full batch instead of only the first page.
const RECORDS_PAGE_SIZE = 200;

export async function fetchAllRecords(
  batchId: string = "default",
  status: string = "ALL",
  search: string = ""
): Promise<{ records: ReconciliationRecordItem[]; total_count: number }> {
  const first = await fetchRecords(batchId, status, search, 1, RECORDS_PAGE_SIZE);
  const pages = Math.ceil(first.total_count / RECORDS_PAGE_SIZE);
  if (pages <= 1) return first;
  const rest = await Promise.all(
    Array.from({ length: pages - 1 }, (_, i) =>
      fetchRecords(batchId, status, search, i + 2, RECORDS_PAGE_SIZE)
    )
  );
  return {
    records: first.records.concat(...rest.map((r) => r.records)),
    total_count: first.total_count,
  };
}

export async function approveRecord(recordId: string, note?: string): Promise<ReconciliationRecordItem> {
  const res = await fetch(`${getApiBase()}/reconciliation/records/${recordId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw failedWrite(res, "Failed to approve record");
  const json = await res.json();
  return json.data;
}

export async function batchApprove(
  batchId: string,
  minConfidence: number = 0.90
): Promise<{ approved_count: number; batch_id: string }> {
  const res = await fetch(`${getApiBase()}/reconciliation/${encodeURIComponent(batchId)}/batch-approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ min_confidence: minConfidence }),
  });
  if (!res.ok) throw failedWrite(res, "Failed to batch approve suggestions");
  const json: ApiResponse<{ approved_count: number; batch_id: string }> = await res.json();
  return json.data;
}

export async function denyRecord(recordId: string, note?: string): Promise<ReconciliationRecordItem> {
  const res = await fetch(`${getApiBase()}/reconciliation/records/${recordId}/deny`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw failedWrite(res, "Failed to deny record");
  const json = await res.json();
  return json.data;
}

export async function revertRecord(recordId: string, note?: string): Promise<ReconciliationRecordItem> {
  const res = await fetch(`${getApiBase()}/reconciliation/records/${recordId}/revert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw failedWrite(res, "Failed to revert action");
  const json = await res.json();
  return json.data;
}

export async function resolveConflict(
  recordId: string,
  chosenSettlementId: string,
  note?: string
): Promise<ReconciliationRecordItem> {
  const res = await fetch(`${getApiBase()}/reconciliation/records/${recordId}/resolve-conflict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chosen_settlement_id: chosenSettlementId, note }),
  });
  if (!res.ok) throw failedWrite(res, "Failed to resolve conflict");
  const json = await res.json();
  return json.data;
}

export async function uploadBankStatement(
  file: File,
  batchId: string = "default",
  password?: string,
  columnMappings?: Record<string, string> | string
): Promise<any> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("batch_id", batchId);
  if (password) {
    formData.append("password", password);
  }
  if (columnMappings) {
    formData.append(
      "column_mappings",
      typeof columnMappings === "string" ? columnMappings : JSON.stringify(columnMappings)
    );
  }

  const res = await fetch(`${getApiBase()}/bank/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const errorObj = new Error(err.error?.message || "Failed to upload and parse bank statement");
    (errorObj as any).code = err.error?.code;
    (errorObj as any).hints = err.error?.details;
    (errorObj as any).details = err.error?.details;
    (errorObj as any).validationErrors = Array.isArray(err.error?.details) ? err.error.details : [];
    throw errorObj;
  }
  const json = await res.json();
  return json.data;
}

export const uploadBankCsv = uploadBankStatement;

export async function fetchBankPasswordHints(): Promise<Array<{ bank: string; pattern: string; example: string }>> {
  try {
    const res = await fetch(`${getApiBase()}/bank/password-hints`, { cache: "no-store" });
    if (!res.ok) return [];
    const json = await res.json();
    return json.data || [];
  } catch {
    return [];
  }
}

export async function triggerRazorpaySync(count: number = 100, batchId: string = "default"): Promise<any> {
  const res = await fetch(`${getApiBase()}/razorpay/sync?batch_id=${batchId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ count }),
  });
  if (!res.ok) throw new Error("Failed to sync Razorpay settlements");
  const json = await res.json();
  return json.data;
}

export async function seedDemoData(count: number = 60, batchId: string = "default"): Promise<any> {
  const res = await fetch(`${getApiBase()}/demo/seed?count=${count}&batch_id=${batchId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to seed demo data");
  const json = await res.json();
  return json.data;
}

export async function resetDemoData(batchId: string = "default"): Promise<any> {
  const res = await fetch(`${getApiBase()}/demo/reset?batch_id=${batchId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to reset demo data");
  const json = await res.json();
  return json.data;
}


export async function askQaAgent(
  query: string,
  contextRecordId?: string | null,
  history?: Array<{ role: string; content: string }>
): Promise<QaAskResponse> {
  const res = await fetch(`${getApiBase()}/qa/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      context_record_id: contextRecordId,
      history: history || [],
    }),
  });
  if (!res.ok) throw new Error("Failed to consult Settlement Q&A Agent");
  const json: ApiResponse<QaAskResponse> = await res.json();
  return json.data;
}

export async function fetchGatewayHealth(signal?: AbortSignal): Promise<GatewayHealth> {
  const res = await fetch(`${getApiBase()}/webhooks/health`, { cache: "no-store", signal });
  if (!res.ok) throw new Error("Failed to fetch gateway health");
  const json: ApiResponse<GatewayHealth> = await res.json();
  return json.data;
}

export async function fetchRecentWebhookEvents(signal?: AbortSignal): Promise<WebhookEventItem[]> {
  const res = await fetch(`${getApiBase()}/webhooks/recent`, { cache: "no-store", signal });
  if (!res.ok) throw new Error("Failed to fetch recent webhook events");
  const json: ApiResponse<WebhookEventItem[]> = await res.json();
  return json.data;
}
