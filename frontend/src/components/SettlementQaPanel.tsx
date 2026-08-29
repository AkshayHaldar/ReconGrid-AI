import React, { useState, useEffect } from "react";
import {
  X,
  Send,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  Clock,
  CheckCircle2,
} from "lucide-react";
import { QaAskResponse } from "@/lib/types";
import { askQaAgent } from "@/lib/api";

interface SettlementQaPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectRecord: (recordId: string) => void;
}

interface MessageItem {
  id: string;
  sender: "user" | "agent";
  text: string;
  sourceRecordId?: string | null;
  guardrailPassed?: boolean;
  timestamp: string;
}

export const SettlementQaPanel: React.FC<SettlementQaPanelProps> = ({
  isOpen,
  onClose,
  onSelectRecord,
}) => {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "welcome-msg",
      sender: "agent",
      text: "Welcome to ReconGrid Settlement Q&A. Ask any question about a specific UTR, Order, or Settlement ID to get a verifiable, audited explanation narrated directly from deterministic log records.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const samplePrompts = [
    "Why did order #4521 have a fee deduction?",
    "Explain UTR RTGS983921092812",
    "What is the status of settlement setl_Kjs9283jkd906?",
    "Show Section 194-O TDS deduction breakdown",
  ];

  const handleSend = async (textToSend?: string) => {
    const q = (textToSend || query).trim();
    if (!q || loading) return;

    const userMsg: MessageItem = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuery("");
    setLoading(true);

    try {
      const response: QaAskResponse = await askQaAgent(q);
      const agentMsg: MessageItem = {
        id: `agent-${Date.now()}`,
        sender: "agent",
        text: response.answer,
        sourceRecordId: response.source_record_id,
        guardrailPassed: !response.guardrail_rejected,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, agentMsg]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `agent-err-${Date.now()}`,
          sender: "agent",
          text: "Unable to consult settlement records right now. Please ensure the backend is active.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40 sm:hidden"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 w-full sm:w-[420px] bg-[#0c121e] border-l border-[#1c2b42] shadow-2xl z-50 flex flex-col backdrop-blur-xl animate-in slide-in-from-right duration-200">
        {/* Panel Header */}
        <div className="p-2.5 sm:p-3 border-b border-[#1c2b42] flex items-center justify-between bg-[#0f1728]">
          <div className="flex items-center gap-2">
            <div className="p-1 rounded bg-[#162138] border border-[#233555] text-indigo-400">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div>
              <h3 className="text-xs font-semibold text-slate-100 flex items-center gap-1.5 font-sans">
                Ask ReconGrid AI
                <span className="px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[9px] font-mono">
                  Audit Verified
                </span>
              </h3>
              <p className="text-[9px] sm:text-[10px] text-slate-400 font-mono">
                Deterministic Retrieval • Token Guardrail Active
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-200 hover:bg-[#131d2e] rounded transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Suggested Prompt Chips for Ramesh / CA */}
        <div className="px-2.5 sm:px-3 py-1.5 sm:py-2 border-b border-[#182337] bg-[#090e18] overflow-x-auto touch-scroll scrollbar-none">
          <div className="text-[9px] sm:text-[10px] uppercase font-semibold text-slate-500 mb-1 font-mono">
            CA Inquiries:
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-0.5">
            {samplePrompts.map((p, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(p)}
                disabled={loading}
                className="text-[10px] sm:text-[11px] font-mono px-2 py-0.5 bg-[#0f1624] hover:bg-[#152033] border border-[#1c2b42] text-slate-300 hover:text-blue-300 rounded whitespace-nowrap transition shrink-0"
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Message List */}
        <div className="flex-1 overflow-y-auto p-2.5 sm:p-3 space-y-2.5 sm:space-y-3 font-sans touch-scroll">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[92%] sm:max-w-[90%] rounded p-2 sm:p-2.5 text-xs leading-relaxed ${
                  m.sender === "user"
                    ? "bg-blue-600 text-white rounded-br-none shadow-sm"
                    : "bg-[#0f1624] border border-[#1c2b42] text-slate-200 rounded-bl-none shadow-sm"
                }`}
              >
                <p>{m.text}</p>

                {/* Source Record Jump Link */}
                {m.sourceRecordId && (
                  <div className="mt-2 pt-1.5 border-t border-[#1a283e] flex items-center justify-between text-[10px] sm:text-[11px] font-mono">
                    <button
                      onClick={() => onSelectRecord(m.sourceRecordId!)}
                      className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 font-medium transition group"
                    >
                      <span>View source record</span>
                      <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
                    </button>
                    <span className="flex items-center gap-1 text-emerald-400 text-[9px] sm:text-[10px]">
                      <ShieldCheck className="w-3 h-3" />
                      Guardrail OK
                    </span>
                  </div>
                )}
              </div>
              <span className="text-[9px] sm:text-[10px] text-slate-500 mt-0.5 px-1 font-mono">{m.timestamp}</span>
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-slate-400 text-xs font-mono py-1.5">
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></div>
              <span>Retrieving audit facts from ReconciliationLog...</span>
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-2 sm:p-2.5 border-t border-[#1c2b42] bg-[#0f1728]">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-1.5 sm:gap-2"
          >
            <input
              type="text"
              placeholder="Ask about UTR, order, or delta..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={loading}
              className="flex-1 px-2.5 py-1.5 bg-[#090e18] border border-[#1c2b42] rounded text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition font-mono"
            />
            <button
              type="submit"
              disabled={!query.trim() || loading}
              className="p-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded transition shrink-0"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>
      </div>
    </>
  );
};
