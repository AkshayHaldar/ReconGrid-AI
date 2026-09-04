"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Header } from "@/components/Header";
import { SummaryCards } from "@/components/SummaryCards";
import { FilterBar } from "@/components/FilterBar";
import { ReconciliationTable } from "@/components/ReconciliationTable";
import { UploadModal } from "@/components/UploadModal";
import { DemoSyncModal } from "@/components/DemoSyncModal";
import { ConflictDrawer } from "@/components/ConflictDrawer";
import { ExceptionDrawer } from "@/components/ExceptionDrawer";
import { SettlementQaPanel } from "@/components/SettlementQaPanel";
import { CheckCircle2, RotateCcw, X, AlertTriangle, Sparkles } from "lucide-react";
import {
  ReconciliationRecordItem,
  ReconciliationStatus,
} from "@/lib/types";
import {
  API_BASE,
  fetchStatus,
  fetchRecords,
  approveRecord,
  denyRecord,
  resolveConflict,
} from "@/lib/api";

interface ToastAction {
  id: string;
  message: string;
  type: "approve" | "deny" | "info";
  recordId: string;
  previousRecord: ReconciliationRecordItem;
}

export default function DashboardPage() {
  const [status, setStatus] = useState<ReconciliationStatus | null>(null);
  const [records, setRecords] = useState<ReconciliationRecordItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("ALL");
  const [selectedDiagnostic, setSelectedDiagnostic] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedBank, setSelectedBank] = useState("ALL");
  const [batchApproveLoading, setBatchApproveLoading] = useState(false);
  const [toast, setToast] = useState<ToastAction | null>(null);

  // Modals & Drawers
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isSyncOpen, setIsSyncOpen] = useState(false);
  const [isQaOpen, setIsQaOpen] = useState(false);
  const [conflictTarget, setConflictTarget] = useState<ReconciliationRecordItem | null>(null);
  const [exceptionTarget, setExceptionTarget] = useState<ReconciliationRecordItem | null>(null);

  // Active highlighted record from Q&A citation jump
  const [highlightedId, setHighlightedId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [statusData, recordsData] = await Promise.all([
        fetchStatus("default"),
        fetchRecords("default", activeTab, searchQuery, 1, 100),
      ]);
      setStatus(statusData);
      setRecords(recordsData.records);
    } catch (err) {
      console.error("Error fetching dashboard data:", err);
    } finally {
      setLoading(false);
    }
  }, [activeTab, searchQuery]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Toast Auto-Dismiss
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when typing in inputs/textareas
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT") {
        if (e.key === "Escape") {
          target.blur();
        }
        return;
      }

      if (e.key === "/") {
        e.preventDefault();
        const searchInput = document.getElementById("ledger-search-input");
        searchInput?.focus();
      } else if (e.key === "?") {
        e.preventDefault();
        setIsQaOpen((prev) => !prev);
      } else if (e.key === "1") {
        setActiveTab("ALL");
      } else if (e.key === "2") {
        setActiveTab("MATCHED");
      } else if (e.key === "3") {
        setActiveTab("SUGGESTED");
      } else if (e.key === "4") {
        setActiveTab("CONFLICT");
      } else if (e.key === "5") {
        setActiveTab("EXCEPTION");
      } else if (e.key === "6") {
        setActiveTab("PENDING_SETTLEMENT_DATA");
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Handle single-click Approve with Optimistic UI & Undo Toast
  const handleApprove = async (recordId: string) => {
    const targetRecord = records.find((r) => r.id === recordId);
    if (!targetRecord) return;

    // Optimistic local update
    setRecords((prev) =>
      prev.map((r) =>
        r.id === recordId
          ? {
              ...r,
              match_status: "MATCHED",
              human_action: "APPROVED",
            }
          : r
      )
    );

    setToast({
      id: `toast-${Date.now()}`,
      message: `Approved settlement match for ${targetRecord.bank_utr || "Record #" + targetRecord.id}`,
      type: "approve",
      recordId,
      previousRecord: targetRecord,
    });

    try {
      const updated = await approveRecord(recordId);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
      const newStatus = await fetchStatus("default");
      setStatus(newStatus);
    } catch (err) {
      console.error("Approve failed:", err);
      // Revert on error
      setRecords((prev) => prev.map((r) => (r.id === recordId ? targetRecord : r)));
      setToast({
        id: `toast-err-${Date.now()}`,
        message: "Failed to save approval. Reverted changes.",
        type: "deny",
        recordId,
        previousRecord: targetRecord,
      });
    }
  };

  // Handle single-click Deny with Optimistic UI & Undo Toast
  const handleDeny = async (recordId: string) => {
    const targetRecord = records.find((r) => r.id === recordId);
    if (!targetRecord) return;

    // Optimistic local update
    setRecords((prev) =>
      prev.map((r) =>
        r.id === recordId
          ? {
              ...r,
              match_status: "EXCEPTION",
              human_action: "DENIED",
              diagnostic_type: "UNRESOLVED",
            }
          : r
      )
    );

    setToast({
      id: `toast-${Date.now()}`,
      message: `Moved ${targetRecord.bank_utr || "Record #" + targetRecord.id} to Exceptions`,
      type: "deny",
      recordId,
      previousRecord: targetRecord,
    });

    try {
      const updated = await denyRecord(recordId);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
      const newStatus = await fetchStatus("default");
      setStatus(newStatus);
    } catch (err) {
      console.error("Deny failed:", err);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? targetRecord : r)));
    }
  };

  // Handle Undo from Toast
  const handleUndo = async () => {
    if (!toast) return;
    const { previousRecord } = toast;
    setRecords((prev) => prev.map((r) => (r.id === previousRecord.id ? previousRecord : r)));
    setToast(null);
    await loadData();
  };

  // Handle Batch Approve High-Confidence (≥90%)
  const handleBatchApprove = async () => {
    const candidates = records.filter(
      (r) => r.match_status === "SUGGESTED" && (r.confidence_score || 0) >= 0.9
    );
    if (candidates.length === 0) return;

    try {
      setBatchApproveLoading(true);
      for (const rec of candidates) {
        await approveRecord(rec.id);
      }
      await loadData();
    } catch (err) {
      console.error("Batch approve failed:", err);
    } finally {
      setBatchApproveLoading(false);
    }
  };

  // Handle Conflict Resolve
  const handleResolveConflict = async (
    recordId: string,
    chosenSettlementId: string,
    note?: string
  ) => {
    try {
      await resolveConflict(recordId, chosenSettlementId, note);
      await loadData();
    } catch (err) {
      console.error("Resolve conflict failed:", err);
    }
  };

  // Handle source record jump from Q&A
  const handleSelectRecordFromQa = (recordId: string) => {
    setHighlightedId(recordId);
    setActiveTab("ALL"); // Reset filter so record is visible
    setSelectedDiagnostic("ALL");
    setTimeout(() => {
      const el = document.getElementById(`record-${recordId}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 150);
  };

  const handleExportCsv = () => {
    window.open(`${API_BASE}/reconciliation/default/export`, "_blank");
  };

  // Filter records by diagnostic sub-type if selected
  const displayedRecords = records.filter((r) => {
    if (selectedDiagnostic === "ALL") return true;
    return r.diagnostic_type === selectedDiagnostic;
  });

  return (
    <div className="min-h-screen bg-[#060913] text-slate-100 flex flex-col font-sans selection:bg-blue-600/90 selection:text-white">
      {/* Header Navigation */}
      <Header
        selectedBank={selectedBank}
        onBankChange={setSelectedBank}
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenSync={() => setIsSyncOpen(true)}
        onToggleQa={() => setIsQaOpen(!isQaOpen)}
        isQaOpen={isQaOpen}
      />

      {/* Main Financial Workspace */}
      <main className="flex-1 w-full max-w-[1920px] mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-5">
        {/* Executive Summary Metric Cards & Trial Balance Control */}
        <SummaryCards
          status={status}
          onOpenUpload={() => setIsUploadOpen(true)}
          onFilterTab={(tab) => {
            setActiveTab(tab);
            setSelectedDiagnostic("ALL");
          }}
        />

        {/* Filter and Action Bar */}
        <FilterBar
          activeTab={activeTab}
          onTabChange={(tab) => {
            setActiveTab(tab);
            setSelectedDiagnostic("ALL");
          }}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          status={status}
          onExportCsv={handleExportCsv}
          selectedDiagnostic={selectedDiagnostic}
          onDiagnosticChange={setSelectedDiagnostic}
          onBatchApprove={handleBatchApprove}
          batchApproveLoading={batchApproveLoading}
        />

        {/* High-Density Reconciliation Ledger Table */}
        <ReconciliationTable
          records={displayedRecords}
          highlightedRecordId={highlightedId}
          onApprove={handleApprove}
          onDeny={handleDeny}
          onOpenConflict={(r) => setConflictTarget(r)}
          onOpenException={(r) => setExceptionTarget(r)}
          loading={loading}
        />
      </main>

      {/* Slide-out Settlement Q&A Copilot Panel */}
      <SettlementQaPanel
        isOpen={isQaOpen}
        onClose={() => setIsQaOpen(false)}
        onSelectRecord={handleSelectRecordFromQa}
      />

      {/* Bank Statement Upload Modal */}
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadSuccess={loadData}
      />

      {/* Demo Sync / Synthetic Seeder Modal */}
      <DemoSyncModal
        isOpen={isSyncOpen}
        onClose={() => setIsSyncOpen(false)}
        onSuccess={loadData}
      />

      {/* Conflict Resolution Drawer */}
      <ConflictDrawer
        record={conflictTarget}
        allRecords={records}
        onClose={() => setConflictTarget(null)}
        onResolve={handleResolveConflict}
      />

      {/* Exception Audit Inspector Drawer */}
      <ExceptionDrawer
        record={exceptionTarget}
        onClose={() => setExceptionTarget(null)}
      />

      {/* Optimistic Action Undo Toast Snackbar */}
      {toast && (
        <div className="fixed bottom-5 left-5 sm:left-6 z-50 flex items-center gap-3.5 bg-[#0b1220] border border-[#1e3250] shadow-2xl rounded-xl px-4 py-3 text-xs text-slate-200 animate-in fade-in slide-in-from-bottom-3 duration-200">
          <div className="flex items-center gap-2.5">
            {toast.type === "approve" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span className="font-medium text-slate-200">{toast.message}</span>
          </div>
          <div className="flex items-center gap-2 pl-3 border-l border-[#19273c]">
            <button
              onClick={handleUndo}
              className="px-2.5 py-1 bg-[#121f35] hover:bg-[#1a2d4e] text-blue-300 hover:text-blue-200 rounded-lg text-[11px] font-mono flex items-center gap-1.5 transition font-semibold"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Undo</span>
            </button>
            <button
              onClick={() => setToast(null)}
              className="p-1 text-slate-400 hover:text-slate-200 rounded-lg transition"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
