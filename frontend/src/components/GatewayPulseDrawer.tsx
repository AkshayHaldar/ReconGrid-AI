import React, { useCallback, useEffect, useState } from "react";
import { X, Activity, AlertTriangle, ChevronRight, ChevronDown, RefreshCw, ShieldCheck, ShieldX } from "lucide-react";
import { GatewayHealth, WebhookEventItem } from "@/lib/types";
import { fetchRecentWebhookEvents } from "@/lib/api";
import {
  GATEWAY_POLL_MS,
  formatEventTimestamp,
  formatRelative,
  hasMalformedPayload,
  hasSignatureFailure,
  ingestionLabel,
  rawBodyOf,
  signatureLabel,
} from "@/lib/gatewayPulse";

interface GatewayPulseDrawerProps {
  open: boolean;
  health: GatewayHealth | null;
  onClose: () => void;
}

/** Collapsible JSON viewer. Objects and arrays open to a few levels, leaves are coloured by type. */
const JsonTree: React.FC<{ name?: string; value: unknown; depth?: number }> = ({ name, value, depth = 0 }) => {
  const [open, setOpen] = useState(depth < 2);
  const label = name !== undefined ? <span className="text-sky-300">{name}: </span> : null;

  if (value === null || typeof value !== "object") {
    const color =
      typeof value === "string" ? "text-emerald-300" : typeof value === "number" ? "text-amber-300" : "text-purple-300";
    return (
      <div className="pl-4 break-all">
        {label}
        <span className={color}>{typeof value === "string" ? JSON.stringify(value) : String(value)}</span>
      </div>
    );
  }

  const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v] as const) : Object.entries(value);
  const brackets = Array.isArray(value) ? ["[", "]"] : ["{", "}"];
  if (entries.length === 0) {
    return (
      <div className="pl-4">
        {label}
        <span className="text-neutral-400">{brackets[0] + brackets[1]}</span>
      </div>
    );
  }
  return (
    <div className="pl-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-0.5 text-left cursor-pointer hover:text-white"
        aria-expanded={open}
      >
        {open ? <ChevronDown className="w-3 h-3 text-neutral-400" /> : <ChevronRight className="w-3 h-3 text-neutral-400" />}
        {label}
        <span className="text-neutral-400">{open ? brackets[0] : `${brackets[0]} ${entries.length} ${brackets[1]}`}</span>
      </button>
      {open && (
        <>
          {entries.map(([k, v]) => (
            <JsonTree key={k} name={k} value={v} depth={depth + 1} />
          ))}
          <div className="pl-4 text-neutral-400">{brackets[1]}</div>
        </>
      )}
    </div>
  );
};

const SIGNATURE_STYLE: Record<WebhookEventItem["signature_status"], string> = {
  VALID: "text-emerald-300 bg-emerald-950/50 border-emerald-800/60",
  INVALID: "text-red-300 bg-red-950/50 border-red-800/60",
  MALFORMED: "text-amber-300 bg-amber-950/50 border-amber-800/60",
};

const INGESTION_STYLE: Record<WebhookEventItem["ingestion_status"], string> = {
  RECONCILIATION_TRIGGERED: "text-sky-300 bg-sky-950/50 border-sky-800/60",
  IGNORED: "text-neutral-300 bg-neutral-900 border-neutral-700",
  FAILED: "text-red-300 bg-red-950/50 border-red-800/60",
  REJECTED: "text-red-300 bg-red-950/50 border-red-800/60",
};

const EventRow: React.FC<{ event: WebhookEventItem; expanded: boolean; onToggle: () => void }> = ({
  event,
  expanded,
  onToggle,
}) => {
  const rawBody = rawBodyOf(event.payload);
  return (
    <li className="border border-[#1e222d] rounded-md bg-[#111318]">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full text-left p-3 flex items-start gap-2 cursor-pointer hover:bg-[#151820] rounded-md"
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 mt-0.5 text-neutral-400 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 mt-0.5 text-neutral-400 shrink-0" />
        )}
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-mono font-semibold text-neutral-100 truncate">{event.event_type}</span>
            <span
              className="text-[10px] font-mono text-neutral-400 shrink-0"
              title={formatEventTimestamp(event.received_at)}
              suppressHydrationWarning
            >
              {formatRelative(event.received_at)}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
            <span className={`px-1.5 py-0.5 rounded border ${SIGNATURE_STYLE[event.signature_status]}`}>
              {event.signature_status === "VALID" ? (
                <ShieldCheck className="inline w-3 h-3 mr-1 -mt-0.5" />
              ) : (
                <ShieldX className="inline w-3 h-3 mr-1 -mt-0.5" />
              )}
              {signatureLabel(event.signature_status)}
            </span>
            <span className={`px-1.5 py-0.5 rounded border ${INGESTION_STYLE[event.ingestion_status]}`}>
              {ingestionLabel(event.ingestion_status)}
            </span>
          </div>
          {event.settlement_id && (
            <p className="text-[10px] font-mono text-neutral-400 truncate">{event.settlement_id}</p>
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-[#1e222d] pt-2">
          <dl className="grid grid-cols-[88px_1fr] gap-y-1 text-[11px] font-mono">
            <dt className="text-neutral-400">Received</dt>
            <dd className="text-neutral-200" suppressHydrationWarning>
              {formatEventTimestamp(event.received_at)}
            </dd>
            <dt className="text-neutral-400">Event ID</dt>
            <dd className="text-neutral-200 break-all">{event.event_id}</dd>
            <dt className="text-neutral-400">Settlement ID</dt>
            <dd className="text-neutral-200 break-all">{event.settlement_id ?? "--"}</dd>
            <dt className="text-neutral-400">UTR</dt>
            <dd className="text-neutral-200 break-all">{event.utr ?? "--"}</dd>
          </dl>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-neutral-400 font-mono mb-1">
              {rawBody !== null ? "Raw body (unverified text)" : "Raw payload"}
            </p>
            <div className="max-h-72 overflow-auto rounded bg-[#090a0f] border border-[#1e222d] p-2 text-[11px] font-mono text-neutral-200 -ml-4">
              {rawBody !== null ? (
                <pre className="pl-4 whitespace-pre-wrap break-all">{rawBody}</pre>
              ) : (
                <JsonTree value={event.payload} />
              )}
            </div>
          </div>
        </div>
      )}
    </li>
  );
};

export const GatewayPulseDrawer: React.FC<GatewayPulseDrawerProps> = ({ open, health, onClose }) => {
  const [events, setEvents] = useState<WebhookEventItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const rows = await fetchRecentWebhookEvents(signal);
      setEvents(rows);
      setError(null);
    } catch (e) {
      if (signal?.aborted) return;
      setError("Could not load webhook activity. Retrying automatically.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  // Fetch when opened, then keep it fresh at the same pace as the header pulse.
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    load(controller.signal);
    const timer = setInterval(() => load(controller.signal), GATEWAY_POLL_MS);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const signatureFailed = hasSignatureFailure(events) || (health?.status === "warning" && health.last_rejection_reason === "INVALID_SIGNATURE");
  const malformed = hasMalformedPayload(events);

  return (
    <>
      <div className="fixed inset-0 bg-black/75 backdrop-blur-xs z-40" onClick={onClose} />
      <aside
        role="dialog"
        aria-label="Gateway Activity"
        className="fixed inset-y-0 right-0 w-full sm:w-[520px] bg-[#0c0e12] border-l border-[#1e222d] shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-150"
      >
        <div className="p-4 bg-[#111318] border-b border-[#1e222d] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-md bg-[#161922] border border-[#282e3d] text-neutral-200 shrink-0">
              <Activity className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-neutral-100 font-sans">Gateway Activity</h3>
              <p className="text-[11px] text-neutral-400 font-mono">Last 15 Razorpay webhooks, newest first</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => load()}
              className="text-neutral-400 hover:text-neutral-200 p-1.5 rounded-md hover:bg-neutral-800 transition cursor-pointer"
              aria-label="Refresh gateway activity"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={onClose}
              className="text-neutral-400 hover:text-neutral-200 p-1.5 rounded-md hover:bg-neutral-800 transition cursor-pointer"
              aria-label="Close gateway activity"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {signatureFailed && (
            <div role="alert" className="flex gap-2 p-3 rounded-md bg-red-950/40 border border-red-800/60 text-red-200 text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Webhook Signature Verification Failed</p>
                <p className="text-red-300/90">Verify Secret in Settings. Until it matches, settlements will not sync from webhooks.</p>
              </div>
            </div>
          )}
          {malformed && (
            <div role="alert" className="flex gap-2 p-3 rounded-md bg-amber-950/40 border border-amber-800/60 text-amber-200 text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <p>A signed webhook was rejected because its payload was malformed. Check the raw body below.</p>
            </div>
          )}
          {error && (
            <p role="status" className="text-xs text-amber-300">
              {error}
            </p>
          )}
          {!error && !loading && events.length === 0 && (
            <p className="text-xs text-neutral-400">
              No webhooks received yet. Point Razorpay at /api/v1/webhooks/razorpay to see activity here.
            </p>
          )}
          <ul className="space-y-2">
            {events.map((event) => (
              <EventRow
                key={event.event_id}
                event={event}
                expanded={expandedId === event.event_id}
                onToggle={() => setExpandedId(expandedId === event.event_id ? null : event.event_id)}
              />
            ))}
          </ul>
        </div>
      </aside>
    </>
  );
};
