import { ApiResponse, QaAskResponse, ReconciliationRecordItem, ReconciliationStatus } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

export async function fetchStatus(batchId: string = "default"): Promise<ReconciliationStatus> {
  const res = await fetch(`${API_BASE}/reconciliation/${batchId}/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch reconciliation status");
  const json: ApiResponse<ReconciliationStatus> = await res.json();
  return json.data;
}

export async function fetchRecords(
  batchId: string = "default",
  status: string = "ALL",
  search: string = "",
  page: number = 1,
  pageSize: number = 100
): Promise<{ records: ReconciliationRecordItem[]; total_count: number }> {
  const params = new URLSearchParams({
    status,
    q: search,
    page: page.toString(),
    page_size: pageSize.toString(),
  });
  const res = await fetch(`${API_BASE}/reconciliation/${batchId}/records?${params}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch reconciliation records");
  const json = await res.json();
  return json.data;
}

export async function approveRecord(recordId: string, note?: string): Promise<ReconciliationRecordItem> {
  const res = await fetch(`${API_BASE}/reconciliation/records/${recordId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error("Failed to approve record");
  const json = await res.json();
  return json.data;
}

export async function denyRecord(recordId: string, note?: string): Promise<ReconciliationRecordItem> {
  const res = await fetch(`${API_BASE}/reconciliation/records/${recordId}/deny`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error("Failed to deny record");
  const json = await res.json();
  return json.data;
}

export async function resolveConflict(
  recordId: string,
  chosenSettlementId: string,
  note?: string
): Promise<ReconciliationRecordItem> {
  const res = await fetch(`${API_BASE}/reconciliation/records/${recordId}/resolve-conflict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chosen_settlement_id: chosenSettlementId, note }),
  });
  if (!res.ok) throw new Error("Failed to resolve conflict");
  const json = await res.json();
  return json.data;
}

export async function uploadBankStatement(
  file: File,
  batchId: string = "default",
  password?: string
): Promise<any> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("batch_id", batchId);
  if (password && password.trim()) {
    formData.append("password", password.trim());
  }

  const res = await fetch(`${API_BASE}/bank/upload`, {
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
    const res = await fetch(`${API_BASE}/bank/password-hints`, { cache: "no-store" });
    if (!res.ok) return [];
    const json = await res.json();
    return json.data || [];
  } catch {
    return [];
  }
}

export async function triggerRazorpaySync(count: number = 100, batchId: string = "default"): Promise<any> {
  const res = await fetch(`${API_BASE}/razorpay/sync?batch_id=${batchId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ count }),
  });
  if (!res.ok) throw new Error("Failed to sync Razorpay settlements");
  const json = await res.json();
  return json.data;
}

export async function seedDemoData(count: number = 60, batchId: string = "default"): Promise<any> {
  const res = await fetch(`${API_BASE}/demo/seed?count=${count}&batch_id=${batchId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to seed demo data");
  const json = await res.json();
  return json.data;
}

export async function resetDemoData(batchId: string = "default"): Promise<any> {
  const res = await fetch(`${API_BASE}/demo/reset?batch_id=${batchId}`, {
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
  const res = await fetch(`${API_BASE}/qa/ask`, {
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
