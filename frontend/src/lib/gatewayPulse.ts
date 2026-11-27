import { GatewayHealth, WebhookEventItem, WebhookIngestionStatus, WebhookSignatureStatus } from "./types";

export const GATEWAY_POLL_MS = 30_000;

export type PulseView = {
  key: "live" | "idle" | "warning" | "checking" | "unknown";
  label: string;
  dotClass: string;
  textClass: string;
};

const PULSE_VIEWS: Record<PulseView["key"], PulseView> = {
  live: { key: "live", label: "Live", dotClass: "bg-emerald-400", textClass: "text-emerald-400" },
  idle: { key: "idle", label: "Idle", dotClass: "bg-amber-400", textClass: "text-amber-400" },
  warning: { key: "warning", label: "Warning", dotClass: "bg-red-500", textClass: "text-red-400" },
  checking: { key: "checking", label: "Checking", dotClass: "bg-neutral-500", textClass: "text-neutral-400" },
  unknown: { key: "unknown", label: "Unknown", dotClass: "bg-neutral-500", textClass: "text-neutral-400" },
};

/** Badge look for the header. A failed poll is "unknown", not "idle", so an outage is not read as quiet. */
export function pulseView(health: GatewayHealth | null, failed: boolean): PulseView {
  if (health) return PULSE_VIEWS[health.status] ?? PULSE_VIEWS.unknown;
  return failed ? PULSE_VIEWS.unknown : PULSE_VIEWS.checking;
}

export function signatureLabel(status: WebhookSignatureStatus): string {
  if (status === "VALID") return "Valid HMAC";
  if (status === "MALFORMED") return "Malformed payload";
  return "Failed";
}

export function ingestionLabel(status: WebhookIngestionStatus): string {
  switch (status) {
    case "RECONCILIATION_TRIGGERED":
      return "Reconciliation Triggered";
    case "FAILED":
      return "Reconciliation Failed";
    case "REJECTED":
      return "Rejected";
    default:
      return "Ignored";
  }
}

/** "just now", "5 min ago", "3 h ago", "2 d ago". A time slightly in the future (clock skew) reads as "just now"; missing or unreadable times give "--". */
export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "--";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "--";
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

/** Absolute timestamp in India's time zone, e.g. "24 Aug 2026, 02:30:15 pm". */
export function formatEventTimestamp(iso: string | null | undefined): string {
  if (!iso) return "--";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "--";
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

/** Events arrive newest first. A refusal only counts until a verified delivery has come in after it. */
function refusedSinceLastVerified(events: WebhookEventItem[], status: WebhookSignatureStatus): boolean {
  for (const e of events) {
    if (e.signature_status === "VALID") return false;
    if (e.signature_status === status) return true;
  }
  return false;
}

/** True when the drawer should show the signature failure banner. */
export function hasSignatureFailure(events: WebhookEventItem[]): boolean {
  return refusedSinceLastVerified(events, "INVALID");
}

export function hasMalformedPayload(events: WebhookEventItem[]): boolean {
  return refusedSinceLastVerified(events, "MALFORMED");
}

/** Rejected deliveries store the body as text because it could not be trusted or parsed. */
export function rawBodyOf(payload: Record<string, unknown>): string | null {
  return typeof payload.raw_body === "string" ? payload.raw_body : null;
}
