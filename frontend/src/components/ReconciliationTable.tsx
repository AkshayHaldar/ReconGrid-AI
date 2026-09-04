import React, { useState, useMemo } from "react";
import {
  Check,
  X,
  Copy,
  CheckCheck,
  Split,
  Eye,
  ArrowDownRight,
  ArrowUpRight,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  FileText,
  Code2,
  Percent,
  Layers,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { ReconciliationRecordItem } from "@/lib/types";
import { formatDate, formatINR } from "@/lib/formatters";
import { StatusBadge } from "./StatusBadge";

interface ReconciliationTableProps {
  records: ReconciliationRecordItem[];
  highlightedRecordId: string | null;
  onApprove: (recordId: string) => void;
  onDeny: (recordId: string) => void;
  onOpenConflict: (record: ReconciliationRecordItem) => void;
  onOpenException: (record: ReconciliationRecordItem) => void;
  loading: boolean;
}

type SortField = "date" | "bank_amount" | "rzp_amount" | "delta_amount" | "bank_utr";
type SortOrder = "asc" | "desc";

export const ReconciliationTable: React.FC<ReconciliationTableProps> = ({
  records,
  highlightedRecordId,
  onApprove,
  onDeny,
  onOpenConflict,
  onOpenException,
  loading,
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const handleCopy = (text: string, id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const sortedRecords = useMemo(() => {
    return [...records].sort((a, b) => {
      let aVal: any = a[sortField];
      let bVal: any = b[sortField];

      if (sortField === "bank_amount" || sortField === "rzp_amount" || sortField === "delta_amount") {
        aVal = parseFloat(aVal || "0");
        bVal = parseFloat(bVal || "0");
      } else if (sortField === "date") {
        aVal = new Date(aVal || 0).getTime();
        bVal = new Date(bVal || 0).getTime();
      } else {
        aVal = (aVal || "").toString().toLowerCase();
        bVal = (bVal || "").toString().toLowerCase();
      }

      if (aVal < bVal) return sortOrder === "asc" ? -1 : 1;
      if (aVal > bVal) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });
  }, [records, sortField, sortOrder]);

  const totalPages = Math.ceil(sortedRecords.length / pageSize) || 1;
  const paginatedRecords = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedRecords.slice(start, start + pageSize);
  }, [sortedRecords, currentPage, pageSize]);

  if (loading && records.length === 0) {
    return (
      <div className="fin-card rounded-xl p-12 text-center text-slate-400 border border-[#162438]">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent mb-3"></div>
        <p className="text-xs font-mono text-slate-300">Running deterministic 4-tier reconciliation engine...</p>
        <p className="text-[10px] text-slate-500 font-mono mt-1">Cross-referencing UTRs, fee calculations, Section 194-O TDS & batched settlements</p>
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="fin-card rounded-xl p-12 text-center text-slate-400 border border-[#162438]">
        <p className="text-xs font-mono text-slate-300">No reconciliation records match the selected filter criteria.</p>
        <p className="text-[10px] text-slate-500 font-mono mt-1">Try switching tabs, clearing search filters, or uploading a statement.</p>
      </div>
    );
  }

  return (
    <div className="fin-card rounded-xl overflow-hidden shadow-lg border border-[#162438]">
      {/* Table Top Controls & Record Count */}
      <div className="px-4 py-2.5 bg-[#090e18] border-b border-[#162438] flex items-center justify-between text-xs font-mono text-slate-400">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-200">Reconciliation Ledger</span>
          <span className="text-[10px] text-blue-300 bg-blue-950 px-2 py-0.5 rounded-full border border-blue-800">
            {records.length} Records
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] text-slate-500">Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setCurrentPage(1);
            }}
            className="bg-[#0c121e] border border-[#18263a] rounded px-1.5 py-0.5 text-[10px] text-slate-200 focus:outline-none cursor-pointer"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>
      </div>

      <div className="overflow-x-auto max-h-[640px] overflow-y-auto touch-scroll">
        <table className="w-full text-left border-collapse text-xs min-w-[800px] sm:min-w-full">
          <thead className="sticky top-0 bg-[#080d16] z-20 border-b border-[#162438] text-slate-400 font-semibold uppercase tracking-wider text-[9px] sm:text-[10px]">
            <tr>
              <th className="py-2.5 px-3 w-8 text-center"></th>
              <th
                onClick={() => toggleSort("date")}
                className="py-2.5 px-3 w-28 cursor-pointer hover:text-slate-200 select-none transition"
              >
                <div className="flex items-center gap-1">
                  <span>Date</span>
                  <ArrowUpDown className="w-3 h-3 text-slate-500" />
                </div>
              </th>
              <th
                onClick={() => toggleSort("bank_utr")}
                className="py-2.5 px-3 min-w-[220px] cursor-pointer hover:text-slate-200 select-none transition"
              >
                <div className="flex items-center gap-1">
                  <span>Bank UTR / Narrative</span>
                  <ArrowUpDown className="w-3 h-3 text-slate-500" />
                </div>
              </th>
              <th
                onClick={() => toggleSort("bank_amount")}
                className="py-2.5 px-3 text-right w-32 cursor-pointer hover:text-slate-200 select-none transition"
              >
                <div className="flex items-center justify-end gap-1">
                  <span>Bank Amt</span>
                  <ArrowUpDown className="w-3 h-3 text-slate-500" />
                </div>
              </th>
              <th className="py-2.5 px-3 w-40">RZP Settlement ID</th>
              <th
                onClick={() => toggleSort("rzp_amount")}
                className="py-2.5 px-3 text-right w-36 cursor-pointer hover:text-slate-200 select-none transition"
              >
                <div className="flex items-center justify-end gap-1">
                  <span>RZP Net (Gross)</span>
                  <ArrowUpDown className="w-3 h-3 text-slate-500" />
                </div>
              </th>
              <th
                onClick={() => toggleSort("delta_amount")}
                className="py-2.5 px-3 text-right w-28 cursor-pointer hover:text-slate-200 select-none transition"
              >
                <div className="flex items-center justify-end gap-1">
                  <span>Delta</span>
                  <ArrowUpDown className="w-3 h-3 text-slate-500" />
                </div>
              </th>
              <th className="py-2.5 px-3 w-40 text-center">Status & Diagnostic</th>
              <th className="py-2.5 px-3 text-right w-24">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#131d2e] font-sans">
            {paginatedRecords.map((r, idx) => {
              const isHighlighted = highlightedRecordId === r.id;
              const isExpanded = expandedRowId === r.id;
              const isDebit = r.bank_direction === "DEBIT";
              const deltaNum = parseFloat(r.delta_amount || "0");
              const hasNonZeroDelta = deltaNum > 0;

              return (
                <React.Fragment key={r.id}>
                  <tr
                    id={`record-${r.id}`}
                    onClick={() => setExpandedRowId(isExpanded ? null : r.id)}
                    className={`hover:bg-[#111a2c] cursor-pointer transition-colors duration-150 ${
                      idx % 2 === 0 ? "table-row-even" : "table-row-odd"
                    } ${isHighlighted ? "citation-highlight" : ""} ${
                      isDebit ? "bg-rose-950/20 hover:bg-rose-950/30" : ""
                    }`}
                  >
                    {/* Expand/Collapse Chevron */}
                    <td className="py-2.5 px-2 text-center text-slate-500 hover:text-slate-300">
                      {isExpanded ? (
                        <ChevronUp className="w-3.5 h-3.5 mx-auto text-blue-400" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5 mx-auto" />
                      )}
                    </td>

                    {/* Date */}
                    <td className="py-2.5 px-3 text-slate-300 font-mono whitespace-nowrap text-[11px] font-tabular">
                      {formatDate(r.date)}
                    </td>

                    {/* Bank UTR & Narrative */}
                    <td className="py-2.5 px-3">
                      <div className="flex flex-col">
                        {r.bank_utr ? (
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono font-semibold text-slate-100 text-xs tracking-tight">
                              {r.bank_utr}
                            </span>
                            <button
                              onClick={(e) => handleCopy(r.bank_utr || "", `utr-${r.id}`, e)}
                              className="text-slate-500 hover:text-slate-300 transition p-0.5"
                              title="Copy UTR"
                            >
                              {copiedId === `utr-${r.id}` ? (
                                <CheckCheck className="w-3 h-3 text-emerald-400" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-500 text-[10px] font-mono italic">No UTR Detected</span>
                        )}
                        <span
                          className="text-slate-400 text-[11px] truncate max-w-[220px] sm:max-w-sm md:max-w-lg lg:max-w-2xl xl:max-w-4xl"
                          title={r.bank_description}
                        >
                          {r.bank_description}
                        </span>
                      </div>
                    </td>

                    {/* Bank Amount */}
                    <td className="py-2.5 px-3 text-right font-mono whitespace-nowrap font-tabular">
                      {isDebit ? (
                        <div className="text-rose-400 flex items-center justify-end gap-1.5">
                          <span className="text-[9px] font-bold bg-rose-950/80 px-1.5 py-0.2 rounded border border-rose-800">
                            DR
                          </span>
                          <span className="font-semibold text-xs">({formatINR(r.bank_amount)})</span>
                        </div>
                      ) : (
                        <div className="text-slate-100 flex items-center justify-end gap-1.5">
                          <span className="text-[9px] font-bold bg-emerald-950/80 text-emerald-300 px-1.5 py-0.2 rounded border border-emerald-800/80">
                            CR
                          </span>
                          <span className="font-semibold text-xs">{formatINR(r.bank_amount)}</span>
                        </div>
                      )}
                    </td>

                    {/* RZP Settlement ID */}
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      {r.rzp_settlement_id ? (
                        <div className="flex items-center gap-1.5 font-mono text-xs text-blue-400">
                          <span className="truncate max-w-[130px] sm:max-w-[160px] lg:max-w-none" title={r.rzp_settlement_id}>
                            {r.rzp_settlement_id}
                          </span>
                          <button
                            onClick={(e) => handleCopy(r.rzp_settlement_id || "", `setl-${r.id}`, e)}
                            className="text-slate-500 hover:text-slate-300 transition p-0.5"
                            title="Copy Settlement ID"
                          >
                            {copiedId === `setl-${r.id}` ? (
                              <CheckCheck className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-600 text-xs font-mono">--</span>
                      )}
                    </td>

                    {/* RZP Net & Gross Split */}
                    <td className="py-2.5 px-3 text-right font-mono whitespace-nowrap text-xs font-tabular">
                      {r.rzp_amount ? (
                        <div>
                          <div className="font-semibold text-slate-100">{formatINR(r.rzp_amount)}</div>
                          {r.rzp_gross_amount && r.rzp_gross_amount !== r.rzp_amount && (
                            <div className="text-[10px] text-slate-400 font-mono">
                              Gross {formatINR(r.rzp_gross_amount)}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-600">--</span>
                      )}
                    </td>

                    {/* Delta / Discrepancy Amount */}
                    <td className="py-2.5 px-3 text-right font-mono whitespace-nowrap text-xs font-tabular">
                      {hasNonZeroDelta ? (
                        <span
                          className={
                            r.match_status === "MATCHED" && r.diagnostic_type === "FEE_DEDUCTION"
                              ? "text-amber-400 font-semibold"
                              : r.match_status === "MATCHED" && r.diagnostic_type === "TDS_194O_DEDUCTION"
                              ? "text-yellow-400 font-semibold"
                              : "text-rose-400 font-semibold"
                          }
                        >
                          {formatINR(r.delta_amount)}
                        </span>
                      ) : (
                        <span className="text-emerald-500/70 text-[10px]">₹ 0.00</span>
                      )}
                    </td>

                    {/* Status & Diagnostic Badge */}
                    <td className="py-2.5 px-3 text-center whitespace-nowrap">
                      <StatusBadge
                        status={r.match_status}
                        tier={r.match_tier}
                        diagnosticType={r.diagnostic_type}
                        confidence={r.confidence_score}
                        note={r.diagnostic_note}
                        onClick={() => {
                          if (r.match_status === "CONFLICT") onOpenConflict(r);
                          if (r.match_status === "EXCEPTION") onOpenException(r);
                        }}
                      />
                    </td>

                    {/* Actions */}
                    <td className="py-2.5 px-3 text-right whitespace-nowrap">
                      {r.match_status === "SUGGESTED" && (
                        <div className="inline-flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => onApprove(r.id)}
                            className="p-1.5 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700/80 text-emerald-300 rounded-lg transition shadow-xs"
                            title="Approve Settlement Match"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => onDeny(r.id)}
                            className="p-1.5 bg-rose-950/80 hover:bg-rose-900 border border-rose-700/80 text-rose-300 rounded-lg transition shadow-xs"
                            title="Deny / Mark Exception"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}

                      {r.match_status === "CONFLICT" && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenConflict(r);
                          }}
                          className="px-2.5 py-1 bg-amber-950/80 hover:bg-amber-900 border border-amber-700/80 text-amber-300 rounded-lg text-[10px] font-mono transition flex items-center gap-1 ml-auto shadow-xs"
                        >
                          <Split className="w-3 h-3" />
                          Resolve
                        </button>
                      )}

                      {r.match_status === "EXCEPTION" && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenException(r);
                          }}
                          className="px-2.5 py-1 bg-[#121c2e] hover:bg-[#192740] border border-[#1e3458] text-slate-300 rounded-lg text-[10px] font-mono transition flex items-center gap-1 ml-auto shadow-xs"
                        >
                          <Eye className="w-3 h-3" />
                          Audit
                        </button>
                      )}

                      {r.match_status === "MATCHED" && (
                        <span className="text-[10px] font-mono text-emerald-400 font-semibold uppercase tracking-tight">
                          {r.human_action ? `CA ${r.human_action}` : "AUTO OK"}
                        </span>
                      )}
                    </td>
                  </tr>

                  {/* Expandable Inline Detail View */}
                  {isExpanded && (
                    <tr className="bg-[#080d16] border-y border-[#18263a]">
                      <td colSpan={9} className="p-4">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs font-sans">
                          {/* Col 1: Mathematical Breakdown */}
                          <div className="bg-[#0b1220] border border-[#162337] rounded-lg p-3 space-y-2 font-mono">
                            <div className="flex items-center justify-between text-[10px] uppercase font-semibold text-blue-400">
                              <span>Fee & Tax Decomposition</span>
                              <span className="text-slate-500">Tier: {r.match_tier}</span>
                            </div>
                            <div className="space-y-1 text-slate-300 text-[11px] font-tabular">
                              <div className="flex justify-between">
                                <span className="text-slate-400">Gross Settlement:</span>
                                <span>{formatINR(r.rzp_gross_amount || r.rzp_amount)}</span>
                              </div>
                              <div className="flex justify-between text-amber-400">
                                <span>MDR Fee (2%):</span>
                                <span>-{formatINR(r.rzp_fees || "0")}</span>
                              </div>
                              <div className="flex justify-between text-yellow-400">
                                <span>GST on Fee (18%):</span>
                                <span>-{formatINR(r.rzp_tax || "0")}</span>
                              </div>
                              <div className="pt-1 border-t border-[#162337] flex justify-between font-bold text-emerald-400">
                                <span>Net Bank Payout:</span>
                                <span>{formatINR(r.rzp_amount || r.bank_amount)}</span>
                              </div>
                            </div>
                          </div>

                          {/* Col 2: Diagnostic & Reasoning */}
                          <div className="bg-[#0b1220] border border-[#162337] rounded-lg p-3 space-y-1.5">
                            <div className="text-[10px] uppercase font-semibold text-slate-400 font-mono flex items-center justify-between">
                              <span>Deterministic Audit Reason</span>
                              <span className="text-emerald-400">Confidence: {Math.round((r.confidence_score || 1) * 100)}%</span>
                            </div>
                            <p className="text-slate-200 text-xs leading-relaxed font-sans">
                              {r.diagnostic_note || "Deterministic match against gateway ledger without variance."}
                            </p>
                            <div className="text-[10px] text-slate-500 font-mono pt-1">
                              Matched at: {r.matched_at ? new Date(r.matched_at).toLocaleString() : "Real-time"}
                            </div>
                          </div>

                          {/* Col 3: Forensic Details & Actions */}
                          <div className="bg-[#0b1220] border border-[#162337] rounded-lg p-3 flex flex-col justify-between space-y-2 font-mono">
                            <div>
                              <div className="text-[10px] uppercase font-semibold text-slate-400 mb-1">
                                Bank Statement Data
                              </div>
                              <div className="text-[11px] text-slate-300 truncate">
                                <strong>Desc:</strong> {r.bank_description}
                              </div>
                              <div className="text-[11px] text-slate-300">
                                <strong>Direction:</strong> {r.bank_direction}
                              </div>
                            </div>
                            <div className="flex justify-end gap-2 pt-1">
                              {r.match_status === "CONFLICT" && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onOpenConflict(r);
                                  }}
                                  className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded text-xs font-sans font-semibold transition"
                                >
                                  Open Conflict Resolver
                                </button>
                              )}
                              {r.match_status === "EXCEPTION" && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onOpenException(r);
                                  }}
                                  className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-sans font-semibold transition"
                                >
                                  Forensic Exception View
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="px-4 py-2.5 bg-[#080d16] border-t border-[#162438] flex items-center justify-between text-xs font-mono text-slate-400">
        <div>
          Showing {(currentPage - 1) * pageSize + 1} to{" "}
          {Math.min(currentPage * pageSize, sortedRecords.length)} of {sortedRecords.length} records
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
            disabled={currentPage === 1}
            className="p-1 rounded bg-[#0c121e] hover:bg-[#121c2e] border border-[#18263a] disabled:opacity-40 transition"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
            disabled={currentPage === totalPages}
            className="p-1 rounded bg-[#0c121e] hover:bg-[#121c2e] border border-[#18263a] disabled:opacity-40 transition"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
