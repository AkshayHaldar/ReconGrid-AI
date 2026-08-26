import React, { useState } from "react";
import {
  X,
  Send,
  Sparkles,
  ArrowRight,
  ShieldCheck,
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

  const samplePrompts = [
    "Why did order #4521 have a fee deduction?",
    "Explain UTR RTGS983921092812",
    "What is the status of settlement setl_Kjs9283jkd906?",
    "Why was settlement setl_Kjs9283jkd908 reversed?",
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
    <div className="fixed inset-y-0 right-0 w-full sm:w-[420px] bg-[#0c1322] border-l border-[#1f2c44] shadow-2xl z-50 flex flex-col backdrop-blur-xl animate-in slide-in-from-right duration-200">
      {/* Panel Header */}
      <div className="p-3.5 border-b border-[#1f2c44] flex items-center justify-between bg-[#10192b]">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-blue-600/20 border border-blue-500/40 text-blue-400">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-slate-100 flex items-center gap-1.5">
              Ask ReconGrid
              <span className="px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-mono">
                Audit Verified
              </span>
            </h3>
            <p className="text-[10px] text-slate-400">
              Deterministic Q&A • Token Guardrail Protected
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Suggested Prompt Chips */}
      <div className="px-3.5 py-2 border-b border-[#182337] bg-[#0a101d] overflow-x-auto">
        <div className="text-[10px] uppercase font-semibold text-slate-500 mb-1.5">
          Suggested Queries for CA:
        </div>
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {samplePrompts.map((p, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(p)}
              disabled={loading}
              className="text-[11px] font-mono px-2 py-1 bg-slate-900 hover:bg-slate-800 border border-slate-700/70 text-slate-300 hover:text-blue-300 rounded whitespace-nowrap transition shrink-0"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Message List */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[90%] rounded-lg p-3 text-xs leading-relaxed ${
                m.sender === "user"
                  ? "bg-blue-600 text-white rounded-br-none shadow-md font-sans"
                  : "bg-[#141e33] border border-[#21304b] text-slate-200 rounded-bl-none shadow-sm font-sans"
              }`}
            >
              <p>{m.text}</p>

              {/* Source Record Jump Link (Mandatory UX Element per UX-CONTEXT §7.3) */}
              {m.sourceRecordId && (
                <div className="mt-2.5 pt-2 border-t border-slate-700/60 flex items-center justify-between text-[11px]">
                  <button
                    onClick={() => onSelectRecord(m.sourceRecordId!)}
                    className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 font-semibold transition group"
                  >
                    <span>View source record</span>
                    <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
                  </button>
                  <span className="flex items-center gap-1 text-emerald-400 text-[10px] font-mono">
                    <ShieldCheck className="w-3 h-3" />
                    Guardrail OK
                  </span>
                </div>
              )}
            </div>
            <span className="text-[10px] text-slate-500 mt-1 px-1">{m.timestamp}</span>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-slate-400 text-xs font-mono py-2">
            <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></div>
            <span>Retrieving audit facts from ReconciliationLog...</span>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="p-3 border-t border-[#1f2c44] bg-[#10192b]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            placeholder="Ask about UTR, order, or delta..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
            className="flex-1 px-3 py-2 bg-[#090e18] border border-[#21304b] rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition font-mono"
          />
          <button
            type="submit"
            disabled={!query.trim() || loading}
            className="p-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
