import React, { useState, useEffect, useRef } from "react";
import {
  X,
  Send,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Plus,
  MessageSquare,
  Trash2,
  Layers,
  History,
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
  title: `Chat ${tabNum}`,
  messages: [
    {
      id: `welcome-${Date.now()}`,
      sender: "agent",
      text: "Welcome to ReconGrid Settlement Q&A. Ask any question about a specific UTR, Order, or Settlement ID to get an audited explanation narrated directly from deterministic log records.",
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
      "How do the 3 tiers of matching work?",
      "How is 2% MDR fee and 18% GST calculated?",
      "Explain Section 194-O TDS deduction",
      "How to claim GST ITC on gateway fees?",
      "Why did order #4521 have a fee deduction?",
      "Explain UTR RTGS983921092812",
      "How are customer refunds handled?",
      "How do batched / split settlements work?",
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
      "How do the 3 tiers of matching work?",
      "How do batched / split settlements work?",
      "How are customer refunds handled?",
      "Why did order #4521 have a fee deduction?",
      "Explain UTR RTGS983921092812",
      "What is the status of settlement setl_Kjs9283jkd906?",
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
      // If closing the only tab, reset it to clean state
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

    // Auto-update tab title if it's the first question
    const isFirstQuestion = activeTab.messages.filter((m) => m.sender === "user").length === 0;
    let newTitle = activeTab.title;
    if (isFirstQuestion) {
      // Pick settlement token or shorten prompt
      const tokenMatch = q.match(/(setl_[a-zA-Z0-9_]+|CMS[a-zA-Z0-9]+|#\d+|RTGS[a-zA-Z0-9]+)/i);
      newTitle = tokenMatch ? tokenMatch[0] : q.length > 18 ? q.slice(0, 16) + "…" : q;
    }

    // Format conversation history for memory
    const historyPayload = activeTab.messages.map((m) => ({
      role: m.sender === "user" ? "user" : "assistant",
      content: m.text,
    }));

    // Update active tab state with user message
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
        sourceRecordId: response.source_record_id || activeTab.activeRecordId,
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
      {/* Mobile Backdrop Overlay */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40 sm:hidden"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 w-full sm:w-[460px] bg-[#0c121e] border-l border-[#1c2b42] shadow-2xl z-50 flex flex-col backdrop-blur-xl animate-in slide-in-from-right duration-200">
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
                  Context Memory Active
                </span>
              </h3>
              <p className="text-[9px] sm:text-[10px] text-slate-400 font-mono">
                Multi-Tab Sessions • Verifiable Settlement Explanations
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleClearCurrentChat}
              title="Clear current tab memory"
              className="p-1 text-slate-400 hover:text-rose-300 hover:bg-[#182438] rounded transition"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onClose}
              className="p-1 text-slate-400 hover:text-slate-200 hover:bg-[#182438] rounded transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Bar for Multi-Chat Memory */}
        <div className="flex items-center gap-1 px-2 pt-2 bg-[#090e18] border-b border-[#182337] overflow-x-auto touch-scroll scrollbar-none">
          {tabs.map((t) => {
            const isActive = t.id === activeTabId;
            return (
              <div
                key={t.id}
                onClick={() => setActiveTabId(t.id)}
                className={`group flex items-center gap-1.5 px-2.5 py-1.5 rounded-t-lg text-[11px] font-mono cursor-pointer transition border-t border-x ${
                  isActive
                    ? "bg-[#0f1728] border-[#1c2b42] text-blue-300 font-semibold shadow-sm"
                    : "bg-[#070b13] border-transparent text-slate-400 hover:text-slate-200 hover:bg-[#0c1322]"
                }`}
              >
                <MessageSquare className={`w-3 h-3 ${isActive ? "text-blue-400" : "text-slate-500"}`} />
                <span className="truncate max-w-[90px]">{t.title}</span>
                <button
                  type="button"
                  onClick={(e) => handleCloseTab(e, t.id)}
                  className={`p-0.5 rounded hover:bg-slate-700/50 transition ${
                    isActive ? "text-slate-400 hover:text-slate-200" : "text-slate-500 hover:text-slate-300"
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
            className="flex items-center gap-1 px-2 py-1 mb-1 rounded text-[10px] font-mono bg-[#111a2c] hover:bg-[#18253d] border border-[#1e2d46] text-blue-300 hover:text-blue-200 transition shrink-0"
          >
            <Plus className="w-3 h-3" />
            <span>New Tab</span>
          </button>
        </div>

        {/* Suggested Prompt Categories & Chips */}
        <div className="px-2.5 sm:px-3 py-1.5 border-b border-[#182337] bg-[#090e18] space-y-1.5">
          {/* Category Tabs */}
          <div className="flex items-center gap-1 overflow-x-auto touch-scroll scrollbar-none pb-0.5">
            {PROMPT_CATEGORIES.map((cat) => {
              const isSelected = selectedCategory === cat.category;
              return (
                <button
                  key={cat.category}
                  onClick={() => setSelectedCategory(cat.category)}
                  className={`text-[9px] font-mono px-2 py-0.5 rounded whitespace-nowrap transition shrink-0 ${
                    isSelected
                      ? "bg-blue-600 text-white font-semibold shadow-xs"
                      : "bg-[#111a2c] hover:bg-[#18253d] text-slate-400 hover:text-slate-200 border border-[#1a2940]"
                  }`}
                >
                  {cat.category}
                </button>
              );
            })}
          </div>

          {/* Categorized Inquiries */}
          <div className="flex items-center gap-1.5 overflow-x-auto touch-scroll scrollbar-none pb-0.5">
            {currentCategoryData.prompts.map((p, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(p)}
                disabled={loading}
                className="text-[10px] font-mono px-2 py-0.5 bg-[#0f1624] hover:bg-[#152033] border border-[#1c2b42] text-slate-300 hover:text-blue-300 rounded whitespace-nowrap transition shrink-0"
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Message List */}
        <div className="flex-1 overflow-y-auto p-2.5 sm:p-3 space-y-2.5 sm:space-y-3 font-sans touch-scroll">
          {activeTab.messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${m.sender === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[92%] sm:max-w-[90%] rounded p-2 sm:p-2.5 text-xs leading-relaxed ${
                  m.sender === "user"
                    ? "bg-blue-600 text-white rounded-br-none shadow-sm font-sans"
                    : "bg-[#0f1624] border border-[#1c2b42] text-slate-200 rounded-bl-none shadow-sm whitespace-pre-line"
                }`}
              >
                <div>{m.text}</div>

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
              <span>Consulting deterministic reconciliation audit log...</span>
            </div>
          )}
          <div ref={messagesEndRef} />
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
              ref={inputRef}
              type="text"
              placeholder="Ask about UTR, order, or follow-up on this settlement..."
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
