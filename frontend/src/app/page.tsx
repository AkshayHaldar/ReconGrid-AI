"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Header } from "@/components/Header";
import { SummaryCards } from "@/components/SummaryCards";
import { FilterBar } from "@/components/FilterBar";
import { ReconciliationTable } from "@/components/ReconciliationTable";
import { UploadModal } from "@/components/UploadModal";
import { DemoSyncModal } from "@/components/DemoSyncModal";
import { ConflictDrawer } from "@/components/ConflictDrawer";
import { ExceptionDrawer } from "@/components/ExceptionDrawer";
import { SettlementQaPanel } from "@/components/SettlementQaPanel";
import { CheckCircle2, RotateCcw, X, AlertTriangle } from "lucide-react";
import {
  ReconciliationRecordItem,
  ReconciliationStatus,
} from "@/lib/types";
import {
  API_BASE,
  fetchStatus,
  collectRecordWindows,
  LedgerSort,
  RecordQuery,
  approveRecord,
  batchApprove,
  denyRecord,
  resolveConflict,
} from "@/lib/api";

import { useLedgerRecords } from "@/lib/useLedgerRecords";

interface ToastAction {
  id: string;
  message: string;
  type: "approve" | "deny" | "info";
  recordId: string;
  previousRecord?: ReconciliationRecordItem;
}

export default function DashboardPage() {
  const [status, setStatus] = useState<ReconciliationStatus | null>(null);
  const [activeTab, setActiveTabState] = useState("ALL");
  const [selectedDiagnostic, setSelectedDiagnosticState] = useState("ALL");
  const [searchQuery, setSearchQueryState] = useState("");
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
  const [scrollRequest, setScrollRequest] = useState<{ id: string; nonce: number } | null>(null);

  const [sort, setSort] = useState<LedgerSort>("date");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [anchorId, setAnchorId] = useState<string>();
  const setActiveTab = (value: string) => { setAnchorId(undefined); setActiveTabState(value); };
  const setSelectedDiagnostic = (value: string) => { setAnchorId(undefined); setSelectedDiagnosticState(value); };
  const setSearchQuery = (value: string) => { setAnchorId(undefined); setSearchQueryState(value); };
  const [actionError, setActionError] = useState<string | null>(null);
  const [conflictRecords, setConflictRecords] = useState<ReconciliationRecordItem[]>([]);
  const [conflictLoading, setConflictLoading] = useState(false);
  const conflictRequest = useRef(0);
  const query = useMemo<RecordQuery>(() => ({
    batchId: "default", status: activeTab, search: searchQuery,
    diagnostic: selectedDiagnostic, sort, direction,
  }), [activeTab, searchQuery, selectedDiagnostic, sort, direction]);
  const ledger = useLedgerRecords(query, anchorId);
  const { records, loading, pager } = ledger;
  const setRecords = pager.setRecords;
  const loadStatus = useCallback(async () => {
    setStatus(await fetchStatus("default"));
  }, []);
  const loadData = useCallback(async () => {
    setActionError(null);
    try {
      await Promise.all([loadStatus(), pager.reload()]);
      return true;
    } catch {
      setActionError("Unable to refresh dashboard status. Please retry.");
      return false;
    }
  }, [pager, loadStatus]);
  useEffect(() => { void loadStatus().catch(() => setActionError("Unable to load dashboard status.")); }, [loadStatus]);

  const openConflict = async (record: ReconciliationRecordItem) => {
    const request = ++conflictRequest.current;
    setConflictLoading(true);
    setActionError(null);
    try {
      const candidates = record.rzp_settlement_db_id ? await collectRecordWindows({
        ...query, status: "CONFLICT", search: "", diagnostic: "ALL",
        settlementId: record.rzp_settlement_db_id,
      }) : [];
      if (request !== conflictRequest.current) return;
      const current = candidates.find(candidate => candidate.id === record.id);
      if (!current) {
        setConflictTarget(null);
        await loadData();
        setActionError("This conflict changed while loading. Refresh and choose an active conflict.");
        return;
      }
      setConflictRecords(candidates);
      setConflictTarget(current);
    } catch {
      if (request === conflictRequest.current) setActionError("Unable to load all conflict candidates. Please retry.");
    } finally {
      if (request === conflictRequest.current) setConflictLoading(false);
    }
  };

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
      await loadData();
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
      await loadData();
    } catch (err) {
      console.error("Deny failed:", err);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? targetRecord : r)));
    }
  };

  // Handle Undo from Toast
  const handleUndo = async () => {
    if (!toast?.previousRecord) return;
    const { previousRecord } = toast;
    setRecords((prev) => prev.map((r) => (r.id === previousRecord.id ? previousRecord : r)));
    setToast(null);
    await loadData();
  };

  // Handle Batch Approve High-Confidence (≥90%)
  const handleBatchApprove = async () => {
    if (activeTab !== "ALL" && activeTab !== "SUGGESTED") return;
    setActionError(null);
    setBatchApproveLoading(true);
    try {
      const result = await batchApprove("default", 0.9);
      const refreshed = await loadData();
      setToast({
        id: `toast-batch-${Date.now()}`,
        message: refreshed
          ? `Approved ${result.approved_count} high-confidence suggestion${result.approved_count === 1 ? "" : "s"}`
          : `Approved ${result.approved_count} suggestion${result.approved_count === 1 ? "" : "s"}, but the ledger did not refresh. Reload to see current results.`,
        type: "info",
        recordId: "batch",
      });
    } catch (err) {
      console.error("Batch approve failed:", err);
      const refreshed = await loadData();
      setToast({
        id: `toast-batch-error-${Date.now()}`,
        message: refreshed
          ? "Approval result could not be confirmed. Ledger refreshed; review current suggestions before retrying."
          : "Approval result could not be confirmed and the ledger could not refresh. Reload before retrying.",
        type: "deny",
        recordId: "batch",
      });
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
    setSearchQuery("");
    setSort("date");
    setDirection("desc");
    setAnchorId(recordId);
    // The table is virtualized, so the row may not be in the DOM; let it scroll by index.
    setScrollRequest({ id: recordId, nonce: Date.now() });
  };

  const handleExportCsv = () => {
    window.open(`${API_BASE}/reconciliation/default/export`, "_blank");
  };

  const handleExportXlsx = () => {
    window.open(`${API_BASE}/reconciliation/default/export-xlsx`, "_blank");
  };

  const handleExportTally = () => {
    window.open(`${API_BASE}/reconciliation/default/export-tally-xml`, "_blank");
  };

  const isEmpty = Boolean(status && status.total_records === 0);
  return (
    <div className="min-h-screen bg-[#090a0f] text-neutral-100 flex flex-col font-sans selection:bg-neutral-800 selection:text-white">
      {/* Header Navigation */}
      <Header
        selectedBank={selectedBank}
        onBankChange={setSelectedBank}
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenSync={() => setIsSyncOpen(true)}
        onToggleQa={() => setIsQaOpen(!isQaOpen)}
        isQaOpen={isQaOpen}
        onExportTally={handleExportTally}
        onExportXlsx={handleExportXlsx}
        periodDate={status?.last_reconciled_at}
      />

      {/* Main Financial Workspace */}
      <main className="flex-1 w-full max-w-[1920px] mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-5 space-y-6">
        {(actionError || conflictLoading) && <div role={actionError ? "alert" : "status"} className="text-sm text-amber-300">
          {actionError || "Loading all conflict candidates..."}
          {actionError && <button onClick={loadData} className="ml-3 underline">Retry refresh</button>}
        </div>}
        {anchorId && <div className="text-xs text-neutral-300">Showing from cited record.
          <button onClick={() => setAnchorId(undefined)} className="ml-3 underline">Return to first records</button>
        </div>}
        <SummaryCards
          status={status}
          records={records}
          activeDiagnostic={selectedDiagnostic}
          activeTab={activeTab}
          onOpenUpload={() => setIsUploadOpen(true)}
          onOpenSync={() => setIsSyncOpen(true)}
          onFilterTab={(tab) => {
            setActiveTab(tab);
            setSelectedDiagnostic("ALL");
          }}
          onSelectDiagnostic={(diag) => setSelectedDiagnostic(diag)}
        />

        {!isEmpty && (
          <>
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

             <ReconciliationTable
                key={ledger.revision}
                records={records}
                totalCount={ledger.totalCount}
                hasMore={ledger.hasMore}
                loadingMore={loading && records.length > 0}
                error={ledger.error}
                onLoadMore={pager.loadMore}
                onRetry={pager.retry}
                serverSort={{ field: sort, order: direction }}
                onSortChange={(field, order) => { setSort(field); setDirection(order); setAnchorId(undefined); }}
                highlightedRecordId={highlightedId}
                scrollRequest={scrollRequest}
                onApprove={handleApprove}
                onDeny={handleDeny}
                onOpenConflict={openConflict}
                onOpenException={(r) => setExceptionTarget(r)}
                loading={loading}
              />
            </>
         )}
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
        allRecords={conflictRecords}
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
        <div className="fixed bottom-5 left-5 sm:left-6 z-50 flex items-center gap-3.5 bg-[#151820] border border-[#282e3d] shadow-2xl rounded-lg px-4 py-3 text-xs text-neutral-200 animate-in fade-in slide-in-from-bottom-3 duration-200">
          <div className="flex items-center gap-2.5">
            {toast.type === "approve" || toast.type === "info" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span className="font-medium text-neutral-200">{toast.message}</span>
          </div>
          <div className="flex items-center gap-2 pl-3 border-l border-[#282e3d]">
            {toast.previousRecord && (
              <button
                onClick={handleUndo}
                className="px-2.5 py-1 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 rounded text-[11px] font-mono flex items-center gap-1.5 transition font-semibold cursor-pointer"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Undo</span>
              </button>
            )}
            <button
              onClick={() => setToast(null)}
              className="p-1 text-neutral-400 hover:text-neutral-200 rounded transition cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
