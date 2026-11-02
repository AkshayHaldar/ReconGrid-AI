import React, { useState, useEffect, useRef } from "react";
import {
  X,
  Send,
  FileText,
  ArrowRight,
  ShieldCheck,
  Plus,
  MessageSquare,
  Trash2,
  Layers,
  History,
  Info,
  CheckCircle2,
  CornerDownLeft,
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

interface ChatTab {
  id: string;
  title: string;
  messages: MessageItem[];
  activeRecordId: string | null;
}

const createInitialTab = (tabNum: number): ChatTab => ({
  id: `tab-${Date.now()}-${tabNum}`,
  title: `Session ${tabNum}`,
  messages: [
    {
      id: `welcome-${Date.now()}`,
      sender: "agent",
      text: "Welcome to ReconGrid Audit Assistant. Ask any question regarding UTR matches, 2% MDR fee + 18% GST deductions, Section 194-O TDS calculations, batched settlements, or specific transaction IDs to get an audited explanation narrated directly from deterministic log records.",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ],
  activeRecordId: null,
});

const PROMPT_CATEGORIES = [
  {
    category: "All Inquiries",
    prompts: [
      "What is Ingested Ledger?",
      "What is Auto-Reconciled Net?",
      "How do the 4 tiers of matching work?",
      "How is 2% MDR fee and 18% GST calculated?",
      "Explain Section 194-O TDS deduction",
      "How to claim GST ITC on gateway fees?",
      "Why did order #4521 have a fee deduction?",
      "Explain UTR RTGS983921092812",
      "How are customer refunds handled?",
      "How do batched settlements work?",
      "How does the token guardrail work?",
      "What are bank PDF password formats?",
    ],
  },
  {
    category: "KPIs & Dashboard",
    prompts: [
      "What is Ingested Ledger?",
      "What is Auto-Reconciled Net?",
      "What does CA Review Required mean?",
      "What is Unresolved Variance?",
      "What is ReconGrid AI?",
    ],
  },
  {
    category: "GST & Tax",
    prompts: [
      "How to claim GST ITC on gateway fees?",
      "Explain Section 194-O TDS deduction",
      "How is 2% MDR fee and 18% GST calculated?",
      "What is the difference between 194-O and 194-H?",
    ],
  },
  {
    category: "Recon & Batches",
    prompts: [
      "How do the 4 tiers of matching work?",
      "How do batched settlements work?",
      "How are customer refunds handled?",
      "Why did order #4521 have a fee deduction?",
      "Explain UTR RTGS983921092812",
    ],
  },
  {
    category: "CA & Audits",
    prompts: [
      "How does the token guardrail work?",
      "How do I resolve conflicts?",
      "What are bank PDF password formats?",
      "How does Batch Approval (≥90%) work?",
      "How to export audit CSV for auditors?",
    ],
  },
];

export const SettlementQaPanel: React.FC<SettlementQaPanelProps> = ({
  isOpen,
  onClose,
  onSelectRecord,
}) => {
  const [tabs, setTabs] = useState<ChatTab[]>([createInitialTab(1)]);
  const [activeTabId, setActiveTabId] = useState<string>(tabs[0].id);
  const [selectedCategory, setSelectedCategory] = useState("All Inquiries");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId) || tabs[0];
  const currentCategoryData = PROMPT_CATEGORIES.find((c) => c.category === selectedCategory) || PROMPT_CATEGORIES[0];

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeTab.messages]);

  const handleAddNewTab = () => {
    const newTabNum = tabs.length + 1;
    const newTab = createInitialTab(newTabNum);
    setTabs((prev) => [...prev, newTab]);
    setActiveTabId(newTab.id);
    setQuery("");
  };

  const handleCloseTab = (e: React.MouseEvent, tabIdToClose: string) => {
    e.stopPropagation();
    if (tabs.length <= 1) {
      const freshTab = createInitialTab(1);
      setTabs([freshTab]);
      setActiveTabId(freshTab.id);
      return;
    }

    const filtered = tabs.filter((t) => t.id !== tabIdToClose);
    setTabs(filtered);
    if (activeTabId === tabIdToClose) {
      setActiveTabId(filtered[filtered.length - 1].id);
    }
  };

  const handleClearCurrentChat = () => {
    setTabs((prev) =>
      prev.map((t) =>
        t.id === activeTabId
          ? {
              ...t,
              messages: [
                {
                  id: `welcome-${Date.now()}`,
                  sender: "agent",
                  text: "Chat memory cleared. Ask any question about a specific UTR, Order, or Settlement ID.",
                  timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                },
              ],
              activeRecordId: null,
            }
          : t
      )
    );
  };

  const handleSend = async (textToSend?: string) => {
    const q = (textToSend || query).trim();
    if (!q || loading) return;

    const userMsg: MessageItem = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    // Auto-update tab title if it's the first user question
    const isFirstQuestion = activeTab.messages.filter((m) => m.sender === "user").length === 0;
    let newTitle = activeTab.title;
    if (isFirstQuestion) {
      const tokenMatch = q.match(/(setl_[a-zA-Z0-9_]+|CMS[a-zA-Z0-9]+|#\d+|RTGS[a-zA-Z0-9]+)/i);
      newTitle = tokenMatch ? tokenMatch[0] : q.length > 16 ? q.slice(0, 14) + "..." : q;
    }

    const historyPayload = activeTab.messages.map((m) => ({
      role: m.sender === "user" ? "user" : "assistant",
      content: m.text,
    }));

    setTabs((prev) =>
      prev.map((t) =>
        t.id === activeTabId
          ? {
              ...t,
              title: newTitle,
              messages: [...t.messages, userMsg],
            }
          : t
      )
    );

    setQuery("");
    setLoading(true);

    try {
      const response: QaAskResponse = await askQaAgent(
        q,
        activeTab.activeRecordId,
        historyPayload
      );

      const agentMsg: MessageItem = {
        id: `agent-${Date.now()}`,
        sender: "agent",
        text: response.answer,
        sourceRecordId: response.source_record_id || null,
        guardrailPassed: !response.guardrail_rejected,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setTabs((prev) =>
        prev.map((t) =>
          t.id === activeTabId
            ? {
                ...t,
                messages: [...t.messages, agentMsg],
                activeRecordId: response.source_record_id || t.activeRecordId,
              }
            : t
        )
      );
    } catch (err: any) {
      setTabs((prev) =>
        prev.map((t) =>
          t.id === activeTabId
            ? {
                ...t,
                messages: [
                  ...t.messages,
                  {
                    id: `agent-err-${Date.now()}`,
                    sender: "agent",
                    text: "Unable to consult settlement records right now. Please ensure the backend is active.",
                    timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                  },
                ],
              }
            : t
        )
      );
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-xs z-40"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 w-full sm:w-[500px] bg-[#0c0e12] border-l border-[#1e222d] shadow-2xl z-50 flex flex-col backdrop-blur-xl animate-in slide-in-from-right duration-150">
        {/* Panel Header */}
        <div className="p-3.5 border-b border-[#1e222d] flex items-center justify-between bg-[#111318]">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-md bg-[#151820] border border-[#282e3d] text-neutral-300">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-neutral-100 flex items-center gap-2 font-sans">
                Audit Assistant
                <span className="px-1.5 py-0.5 rounded bg-neutral-900 text-neutral-400 border border-neutral-800 text-[9px] font-mono font-medium">
                  Ledger Grounded
                </span>
              </h3>
              <p className="text-[10px] text-neutral-400 font-mono">
                Verifiable Settlement Explanations
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleClearCurrentChat}
              title="Clear current session memory"
              className="p-1.5 text-neutral-400 hover:text-rose-300 hover:bg-[#151820] rounded-md transition cursor-pointer"
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-neutral-400 hover:text-neutral-200 hover:bg-[#151820] rounded-md transition cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Multi-Tab Bar */}
        <div className="flex items-center gap-1 px-2.5 pt-2 bg-[#0e1015] border-b border-[#1e222d] overflow-x-auto touch-scroll scrollbar-none">
          {tabs.map((t) => {
            const isActive = t.id === activeTabId;
            return (
              <div
                key={t.id}
                onClick={() => setActiveTabId(t.id)}
                className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-t-md text-xs font-mono cursor-pointer transition border-t border-x ${
                  isActive
                    ? "bg-[#151820] border-[#1e222d] text-neutral-200 font-medium shadow-xs"
                    : "bg-[#0c0e12] border-transparent text-neutral-500 hover:text-neutral-300 hover:bg-[#111318]"
                }`}
              >
                <MessageSquare className={`w-3 h-3 ${isActive ? "text-neutral-300" : "text-neutral-600"}`} />
                <span className="truncate max-w-[100px]">{t.title}</span>
                <button
                  type="button"
                  onClick={(e) => handleCloseTab(e, t.id)}
                  className={`p-0.5 rounded hover:bg-neutral-800 transition ${
                    isActive ? "text-neutral-400 hover:text-neutral-200" : "text-neutral-600 hover:text-neutral-400"
                  }`}
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </div>
            );
          })}
          <button
            onClick={handleAddNewTab}
            title="New Chat Session"
            className="flex items-center gap-1 px-2 py-1 mb-1 rounded text-[10px] font-mono bg-[#151820] hover:bg-[#1c202a] border border-[#1e222d] text-neutral-300 hover:text-white transition shrink-0 cursor-pointer"
          >
            <Plus className="w-3 h-3" />
            <span>New</span>
          </button>
        </div>

        {/* Suggested Prompt Categories & Chips */}
        <div className="px-3 py-2 border-b border-[#1e222d] bg-[#0e1015] space-y-1.5">
          {/* Category Selector */}
          <div className="flex items-center gap-1 overflow-x-auto touch-scroll scrollbar-none pb-0.5">
            {PROMPT_CATEGORIES.map((cat) => {
              const isSelected = selectedCategory === cat.category;
              return (
                <button
                  key={cat.category}
                  onClick={() => setSelectedCategory(cat.category)}
                  className={`text-[9px] font-mono px-2 py-0.5 rounded whitespace-nowrap transition shrink-0 cursor-pointer ${
                    isSelected
                      ? "bg-neutral-800 text-neutral-100 font-semibold border border-neutral-700 shadow-xs"
                      : "bg-[#151820] hover:bg-[#1c202a] text-neutral-400 hover:text-neutral-200 border border-[#1e222d]"
                  }`}
                >
                  {cat.category}
                </button>
              );
            })}
          </div>

          {/* Prompt Chips */}
          <div className="flex items-center gap-1.5 overflow-x-auto touch-scroll scrollbar-none pb-0.5">
            {currentCategoryData.prompts.map((p, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(p)}
                disabled={loading}
                className="text-[10px] font-mono px-2.5 py-0.5 bg-[#151820] hover:bg-[#1c202a] border border-[#1e222d] text-neutral-300 hover:text-neutral-100 rounded whitespace-nowrap transition shrink-0 cursor-pointer"
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-3.5 space-y-3 font-sans touch-scroll bg-[#0c0e12]">
          {activeTab.messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[92%] sm:max-w-[88%] rounded-lg p-3 text-xs leading-relaxed ${
                  m.sender === "user"
                    ? "bg-neutral-800 text-neutral-100 border border-neutral-700 rounded-br-xs shadow-xs"
                    : "bg-[#151820] border border-[#1e222d] text-neutral-200 rounded-bl-xs shadow-xs whitespace-pre-line"
                }`}
              >
                <div>{m.text}</div>

                {/* Source Record Jump Link */}
                {m.sourceRecordId && (
                  <div className="mt-2.5 pt-2 border-t border-[#1e222d] flex items-center justify-between text-[11px] font-mono">
                    <button
                      onClick={() => onSelectRecord(m.sourceRecordId!)}
                      className="inline-flex items-center gap-1.5 text-neutral-300 hover:text-white font-medium transition group cursor-pointer"
                    >
                      <span>Highlight in Ledger</span>
                      <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
                    </button>
                    <span className="flex items-center gap-1 text-emerald-400 text-[10px]">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      Audited Grounding
                    </span>
                  </div>
                )}
              </div>
              <span className="text-[10px] text-neutral-500 mt-1 px-1 font-mono">{m.timestamp}</span>
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-neutral-400 text-xs font-mono py-2 px-1">
              <div className="w-2 h-2 rounded-full bg-neutral-400 animate-pulse"></div>
              <span>Consulting deterministic reconciliation audit log...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-3 border-t border-[#1e222d] bg-[#111318]">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-2"
          >
            <input
              ref={inputRef}
              type="text"
              placeholder="Ask about UTR, order #, or fee calculation..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={loading}
              className="flex-1 px-3.5 py-2 bg-[#0c0e12] border border-[#1e222d] focus:border-neutral-500 rounded-md text-xs text-neutral-200 placeholder-neutral-500 focus:outline-none transition font-mono"
            />
            <button
              type="submit"
              disabled={!query.trim() || loading}
              className="p-2 bg-neutral-100 hover:bg-white disabled:opacity-40 text-neutral-900 rounded-md transition shadow-xs shrink-0 cursor-pointer"
              aria-label="Send Query"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </>
  );
};
