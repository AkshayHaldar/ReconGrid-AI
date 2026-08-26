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
import {
  ReconciliationRecordItem,
  ReconciliationStatus,
} from "@/lib/types";
import {
  fetchStatus,
  fetchRecords,
  approveRecord,
  denyRecord,
  resolveConflict,
} from "@/lib/api";

export default function DashboardPage() {
  const [status, setStatus] = useState<ReconciliationStatus | null>(null);
  const [records, setRecords] = useState<ReconciliationRecordItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedBank, setSelectedBank] = useState("ALL");

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

  // Handle single-click Approve
  const handleApprove = async (recordId: string) => {
    try {
      const updated = await approveRecord(recordId);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
      // Refresh status totals
      const newStatus = await fetchStatus("default");
      setStatus(newStatus);
    } catch (err) {
      console.error("Approve failed:", err);
    }
  };

  // Handle single-click Deny
  const handleDeny = async (recordId: string) => {
    try {
      const updated = await denyRecord(recordId);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
      // Refresh status totals
      const newStatus = await fetchStatus("default");
      setStatus(newStatus);
    } catch (err) {
      console.error("Deny failed:", err);
    }
  };

  // Handle Conflict Resolve
  const handleResolveConflict = async (
    recordId: string,
    chosenSettlementId: string,
    note?: string
  ) => {
    try {
      const updated = await resolveConflict(recordId, chosenSettlementId, note);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
      const newStatus = await fetchStatus("default");
      setStatus(newStatus);
    } catch (err) {
      console.error("Resolve conflict failed:", err);
    }
  };

  // Handle source record jump from Q&A
  const handleSelectRecordFromQa = (recordId: string) => {
    setHighlightedId(recordId);
    setActiveTab("ALL"); // Reset filter so record is visible
    setTimeout(() => {
      const el = document.getElementById(`record-${recordId}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 150);
  };

  const handleExportCsv = () => {
    window.open("http://127.0.0.1:8000/api/v1/reconciliation/default/export", "_blank");
  };

  return (
    <div className="min-h-screen bg-[#080c14] text-slate-100 flex flex-col font-sans">
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
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-4 sm:py-6">
        {/* Executive Summary Metric Cards */}
        <SummaryCards
          status={status}
          onOpenUpload={() => setIsUploadOpen(true)}
          onFilterTab={(tab) => setActiveTab(tab)}
        />

        {/* Filter and Action Bar */}
        <FilterBar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          status={status}
          onExportCsv={handleExportCsv}
        />

        {/* High-Density Reconciliation Ledger Table */}
        <ReconciliationTable
          records={records}
          highlightedRecordId={highlightedId}
          onApprove={handleApprove}
          onDeny={handleDeny}
          onOpenConflict={(r) => setConflictTarget(r)}
          onOpenException={(r) => setExceptionTarget(r)}
          loading={loading}
        />
      </main>

      {/* Slide-out Settlement Q&A Panel */}
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
        onClose={() => setConflictTarget(null)}
        onResolve={handleResolveConflict}
      />

      {/* Exception Audit Inspector Drawer */}
      <ExceptionDrawer
        record={exceptionTarget}
        onClose={() => setExceptionTarget(null)}
      />
    </div>
  );
}
