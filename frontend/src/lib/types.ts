export type MatchStatus =
  | "MATCHED"
  | "SUGGESTED"
  | "CONFLICT"
  | "EXCEPTION"
  | "PENDING_SETTLEMENT_DATA";

export type MatchTier = "TIER_0" | "TIER_1" | "TIER_2" | "TIER_3" | "MANUAL";

export type DiagnosticType =
  | "EXACT_MATCH"
  | "FEE_DEDUCTION"
  | "TDS_194O_DEDUCTION"
  | "BATCHED_SETTLEMENT"
  | "REFUND_ADJUSTED"
  | "FX_ADJUSTED"
  | "REVERSAL"
  | "UNRESOLVED"
  | "PENDING_SETTLEMENT"
  | "DATE_AMOUNT_FALLBACK"
  | "FUZZY_MATCH";

export interface ReconciliationRecordItem {
  id: string;
  batch_id: string;
  bank_tx_id: string;
  date: string;
  bank_utr: string | null;
  bank_description: string;
  bank_amount: string;
  bank_direction: "CREDIT" | "DEBIT";

  rzp_settlement_db_id?: string | null;
  rzp_settlement_id?: string | null;
  rzp_amount?: string | null;
  rzp_gross_amount?: string | null;
  rzp_fees?: string | null;
  rzp_tax?: string | null;
  rzp_utr?: string | null;

  match_status: MatchStatus;
  match_tier: MatchTier;
  confidence_score?: number | null;
  delta_amount: string;
  diagnostic_type: DiagnosticType;
  diagnostic_note: string;
  matched_at: string;
  human_action?: string | null;

  raw_csv_row?: Record<string, any> | null;
  raw_rzp_payload?: Record<string, any> | null;
}

export interface ReconciliationStatus {
  batch_id: string;
  total_records: number;
  matched_count: number;
  suggested_count: number;
  conflict_count: number;
  exception_count: number;
  pending_count?: number;
  match_rate_percentage: number;
  total_ingested_amount: string;
  total_reconciled_amount: string;
  total_exception_amount: string;
  total_pending_amount?: string;
  total_credit_amount?: string;
  total_debit_amount?: string;
  net_ingested_amount?: string;
  total_suggested_amount?: string;
  total_conflict_amount?: string;
  total_unresolved_variance?: string;
  is_in_balance?: boolean;
  last_reconciled_at?: string | null;
}

export interface QaAskResponse {
  query: string;
  answer: string;
  source_record_id: string | null;
  source_settlement_id: string | null;
  source_bank_utr: string | null;
  guardrail_rejected: boolean;
  retrieved_data?: Record<string, any> | null;
  asked_at: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  } | null;
}
