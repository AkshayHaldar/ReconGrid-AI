import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  X,
  UploadCloud,
  FileText,
  Download,
  CheckCircle2,
  AlertCircle,
  Lock,
  Eye,
  EyeOff,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Layers,
  KeyRound,
  Sliders,
  Sparkles,
  RotateCcw,
  Table,
} from "lucide-react";
import { uploadBankStatement, fetchBankPasswordHints, API_BASE } from "@/lib/api";
import {
  parseCsvLines,
  detectCsvHeaderAndRows,
  isStandardBankStatement,
  computeHeaderSignature,
  guessColumnMappings,
  ColumnMappings,
  DetectedCsvInfo,
} from "@/lib/csv-mapper";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadSuccess: () => void;
}

const DEFAULT_BANK_HINTS = [
  {
    bank: "HDFC Bank",
    pattern: "Customer ID (or DOB in DDMMYYYY format, or first 4 letters of name in lowercase + DDMM)",
    example: "12345678 or 15081995 or aksh1508",
  },
  {
    bank: "ICICI Bank",
    pattern: "First 4 letters of name in LOWERCASE + DDMM of Birth",
    example: "aksh1508 (for Akshay, DOB 15-Aug)",
  },
  {
    bank: "State Bank of India (SBI)",
    pattern: "Last 5 digits of registered Mobile No + DDMM of DOB (or 11-digit Account Number)",
    example: "987651508 or 0000012345678",
  },
  {
    bank: "Axis Bank",
    pattern: "First 4 letters of Name (CAPITAL) + Last 4 digits of Customer ID / Mobile",
    example: "AKSH1234",
  },
  {
    bank: "Kotak Mahindra Bank",
    pattern: "CRN Number (Customer Relationship Number) or DOB (DDMMYYYY)",
    example: "98765432 or 15081995",
  },
  {
    bank: "Punjab National Bank (PNB)",
    pattern: "Account Number or Customer ID",
    example: "1234000100123456",
  },
  {
    bank: "Bank of Baroda (BOB)",
    pattern: "Registered Mobile Number or First 4 letters of Name + DDMM",
    example: "9876543210 or AKSH1508",
  },
  {
    bank: "Canara Bank",
    pattern: "Customer ID or 13-digit Account Number",
    example: "123456789",
  },
];

export const UploadModal: React.FC<UploadModalProps> = ({
  isOpen,
  onClose,
  onUploadSuccess,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showHints, setShowHints] = useState(false);
  const [hints, setHints] = useState(DEFAULT_BANK_HINTS);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isPasswordError, setIsPasswordError] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const passwordInputRef = useRef<HTMLInputElement>(null);

  // CSV column mapping state
  const [isCsv, setIsCsv] = useState(false);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvSampleRows, setCsvSampleRows] = useState<Record<string, string>[]>([]);
  const [headerHash, setHeaderHash] = useState<string>("");
  const [isStandardCsv, setIsStandardCsv] = useState(false);
  const [showMapper, setShowMapper] = useState(false);
  const [savedMappingLoaded, setSavedMappingLoaded] = useState(false);

  // Active mappings
  const [selectedDateCol, setSelectedDateCol] = useState<string>("");
  const [selectedNarrationCol, setSelectedNarrationCol] = useState<string>("");
  const [selectedAmountCol, setSelectedAmountCol] = useState<string>("");
  const [selectedRefCol, setSelectedRefCol] = useState<string>("");
  const [selectedWithdrawalCol, setSelectedWithdrawalCol] = useState<string>("");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      fetchBankPasswordHints().then((res) => {
        if (res && res.length > 0) setHints(res);
      });
    }
  }, [isOpen]);

  const resetFileState = () => {
    setFile(null);
    setPassword("");
    setError(null);
    setValidationErrors([]);
    setIsPasswordError(false);
    setIsCsv(false);
    setCsvHeaders([]);
    setCsvSampleRows([]);
    setHeaderHash("");
    setIsStandardCsv(false);
    setShowMapper(false);
    setSavedMappingLoaded(false);
    setSelectedDateCol("");
    setSelectedNarrationCol("");
    setSelectedAmountCol("");
    setSelectedRefCol("");
    setSelectedWithdrawalCol("");
  };

  const processSelectedFile = async (selected: File) => {
    setFile(selected);
    setError(null);
    setValidationErrors([]);
    setIsPasswordError(false);
    setSavedMappingLoaded(false);

    const isPdfFile = selected.name.toLowerCase().endsWith(".pdf");
    const isCsvFile =
      selected.name.toLowerCase().endsWith(".csv") ||
      selected.name.toLowerCase().endsWith(".txt") ||
      selected.type.includes("csv");

    setIsCsv(isCsvFile);

    if (isPdfFile) {
      setIsStandardCsv(false);
      setShowMapper(false);
      setCsvHeaders([]);
      setCsvSampleRows([]);
      setTimeout(() => passwordInputRef.current?.focus(), 100);
      return;
    }

    if (isCsvFile) {
      try {
        const slice = selected.slice(0, 65536);
        const text = await slice.text();
        const parsedRows = parseCsvLines(text, 30);
        const detected: DetectedCsvInfo | null = detectCsvHeaderAndRows(parsedRows);

        if (detected && detected.headers.length > 0) {
          setCsvHeaders(detected.headers);
          setCsvSampleRows(detected.dataRows.slice(0, 5));

          const signature = computeHeaderSignature(detected.headers);
          setHeaderHash(signature);

          const isStandard = isStandardBankStatement(detected.headers);
          setIsStandardCsv(isStandard);

          // Check localStorage cache
          let cached: ColumnMappings | null = null;
          try {
            const rawStored = localStorage.getItem(`recongrid_csv_mapping_${signature}`);
            if (rawStored) {
              cached = JSON.parse(rawStored);
            }
          } catch {
            // Ignore localStorage retrieval issues
          }

          if (cached) {
            setSelectedDateCol(cached.date || "");
            setSelectedNarrationCol(cached.narration || "");
            setSelectedAmountCol(cached.amount || "");
            setSelectedRefCol(cached.ref || "");
            setSelectedWithdrawalCol(cached.withdrawal || "");
            setSavedMappingLoaded(true);

            // If non-standard, show mapper pre-filled
            setShowMapper(!isStandard);
          } else {
            // Auto-guess initial selections
            const guessed = guessColumnMappings(detected.headers);
            setSelectedDateCol(guessed.date || "");
            setSelectedNarrationCol(guessed.narration || "");
            setSelectedAmountCol(guessed.amount || "");
            setSelectedRefCol(guessed.ref || "");
            setSelectedWithdrawalCol(guessed.withdrawal || "");
            setSavedMappingLoaded(false);

            // Non-standard CSV transitions into interactive mapper; standard CSV automatically bypasses
            setShowMapper(!isStandard);
          }
        }
      } catch (err) {
        // If client-side parse fails, fallback to server upload
        setShowMapper(false);
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processSelectedFile(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleResetToAutoDetect = () => {
    if (csvHeaders.length > 0) {
      const guessed = guessColumnMappings(csvHeaders);
      setSelectedDateCol(guessed.date || "");
      setSelectedNarrationCol(guessed.narration || "");
      setSelectedAmountCol(guessed.amount || "");
      setSelectedRefCol(guessed.ref || "");
      setSelectedWithdrawalCol(guessed.withdrawal || "");
      setSavedMappingLoaded(false);
    }
  };

  const handleSubmit = async () => {
    if (!file) {
      setError("Please select a bank statement file (PDF or CSV) to upload.");
      return;
    }

    setUploading(true);
    setError(null);
    setValidationErrors([]);
    setIsPasswordError(false);

    try {
      let customMappings: Record<string, string> | undefined = undefined;

      // Attach custom mappings if mapping was configured or file is non-standard CSV
      if (
        isCsv &&
        (showMapper || !isStandardCsv) &&
        (selectedDateCol || selectedAmountCol || selectedNarrationCol)
      ) {
        customMappings = {
          date: selectedDateCol,
          narration: selectedNarrationCol,
          amount: selectedAmountCol,
        };
        if (selectedRefCol && selectedRefCol !== "__none__") {
          customMappings.ref = selectedRefCol;
        }
        if (selectedWithdrawalCol && selectedWithdrawalCol !== "__none__") {
          customMappings.withdrawal = selectedWithdrawalCol;
        }

        // Cache in localStorage
        if (headerHash) {
          try {
            localStorage.setItem(
              `recongrid_csv_mapping_${headerHash}`,
              JSON.stringify(customMappings)
            );
          } catch {
            // Ignore localStorage save failures
          }
        }
      }

      await uploadBankStatement(file, "default", password, customMappings);
      onUploadSuccess();
      onClose();
    } catch (err: any) {
      const isPwdReq =
        err.code === "PASSWORD_REQUIRED" ||
        err.code === "INVALID_PASSWORD" ||
        err.message?.toLowerCase().includes("password");
      setIsPasswordError(isPwdReq);
      if (isPwdReq) {
        setShowHints(true);
        setTimeout(() => passwordInputRef.current?.focus(), 100);
      }
      if (err.hints && Array.isArray(err.hints) && err.hints.length > 0 && typeof err.hints[0] === "object") {
        setHints(err.hints);
      }
      if (err.validationErrors && Array.isArray(err.validationErrors)) {
        setValidationErrors(err.validationErrors);
      }
      setError(err.message || "Failed to parse bank statement.");
    } finally {
      setUploading(false);
    }
  };

  const downloadSample = (bank: string) => {
    window.open(`${API_BASE}/demo/sample-statement?bank=${bank}`, "_blank");
  };

  // Compute live 3-row data preview
  const livePreviewRows = useMemo(() => {
    if (!csvSampleRows || csvSampleRows.length === 0) return [];
    return csvSampleRows.slice(0, 3).map((row) => ({
      date: selectedDateCol ? row[selectedDateCol] || "" : "",
      narration: selectedNarrationCol ? row[selectedNarrationCol] || "" : "",
      amount: selectedAmountCol ? row[selectedAmountCol] || "" : "",
      ref:
        selectedRefCol && selectedRefCol !== "__none__"
          ? row[selectedRefCol] || ""
          : "(Auto-detect)",
      withdrawal:
        selectedWithdrawalCol && selectedWithdrawalCol !== "__none__"
          ? row[selectedWithdrawalCol] || ""
          : "",
    }));
  }, [
    csvSampleRows,
    selectedDateCol,
    selectedNarrationCol,
    selectedAmountCol,
    selectedRefCol,
    selectedWithdrawalCol,
  ]);

  if (!isOpen) return null;

  const isPdf = file?.name.toLowerCase().endsWith(".pdf");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-3 sm:p-4">
      <div
        className={`bg-[#0c0e12] border border-[#1e222d] rounded-xl ${
          showMapper ? "max-w-2xl" : "max-w-lg"
        } w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 max-h-[92vh] flex flex-col`}
      >
        {/* Header */}
        <div className="p-4 bg-[#111318] border-b border-[#1e222d] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#151820] border border-[#282e3d] rounded-md text-neutral-300">
              <UploadCloud className="w-4 h-4 shrink-0" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-neutral-100 font-sans flex items-center gap-2">
                Upload Bank Statement
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-neutral-900 text-neutral-300 border border-neutral-800">
                  PDF & CSV
                </span>
              </h3>
              <p className="text-[11px] text-neutral-400 font-mono">
                Multi-page statement parsing, auto-decryption & custom column mapping
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-200 p-1.5 rounded-md hover:bg-neutral-800 transition cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-3.5 text-xs font-sans overflow-y-auto touch-scroll flex-1">
          {/* Dropzone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed ${
              file ? "border-blue-500/60 bg-blue-950/15" : "border-[#1c2c44] hover:border-blue-500/70 bg-[#090e18]"
            } rounded-xl p-5 text-center cursor-pointer transition-all duration-150 group`}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".csv,.pdf,application/pdf,text/csv"
              className="hidden"
            />
            <UploadCloud className="w-8 h-8 text-blue-500 mx-auto mb-2 transition-transform group-hover:scale-110" />
            {file ? (
              <div className="space-y-1">
                <div className="flex items-center justify-center gap-2 text-slate-200 font-mono">
                  <FileText className={`w-4 h-4 ${isPdf ? "text-red-400" : "text-emerald-400"} shrink-0`} />
                  <span className="font-semibold text-xs truncate max-w-[240px]">{file.name}</span>
                  <span className="text-[10px] text-slate-400 font-tabular shrink-0">
                    ({(file.size / 1024).toFixed(1)} KB)
                  </span>
                </div>
                <div className="flex items-center justify-center gap-2 text-[10px] text-neutral-400">
                  <span className="inline-flex items-center gap-1 text-neutral-300">
                    <Layers className="w-3 h-3 text-neutral-400" />{" "}
                    {isPdf ? "Multi-Page PDF Engine" : isStandardCsv ? "Standard Bank CSV Parser" : "Custom CSV Mapper"}
                  </span>
                  <span>•</span>
                  <span>Click or drag to replace file</span>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-slate-200 font-semibold mb-1 text-xs sm:text-sm">
                  Click to browse or drag & drop bank statement
                </p>
                <p className="text-[10px] text-slate-400 font-mono">
                  Supports corporate portals (Axis, IndusInd, Federal, Yes Bank) & standard formats (HDFC, ICICI, SBI)
                </p>
              </div>
            )}
          </div>

          {/* Standard CSV Detected Banner (when mapping is hidden) */}
          {file && isCsv && isStandardCsv && !showMapper && (
            <div className="p-3 bg-emerald-950/20 border border-emerald-800/40 rounded-xl flex items-center justify-between text-xs animate-in fade-in">
              <div className="flex items-center gap-2 text-emerald-300">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="font-medium">Standard bank statement format recognized</span>
                <span className="text-[10px] text-emerald-400/80 font-mono bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/60">
                  Autodetected
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowMapper(true)}
                className="text-[11px] text-blue-400 hover:text-blue-300 font-mono underline cursor-pointer"
              >
                Configure Mappings
              </button>
            </div>
          )}

          {/* Interactive Column Mapping Dialog */}
          {file && isCsv && showMapper && (
            <div className="p-3.5 bg-[#090e18] border border-[#18263a] rounded-xl space-y-3.5 animate-in fade-in">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-[#18263a]">
                <div className="flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-blue-400 shrink-0" />
                  <div>
                    <h4 className="text-xs font-semibold text-slate-200">Interactive Column Mapper</h4>
                    <p className="text-[10px] text-slate-400 font-mono">
                      Map CSV columns to canonical transaction fields for ingestion
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {savedMappingLoaded && (
                    <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-mono bg-emerald-950/40 border border-emerald-800/60 px-2 py-0.5 rounded">
                      <Sparkles className="w-3 h-3" /> Auto-loaded saved mapping
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={handleResetToAutoDetect}
                    className="inline-flex items-center gap-1 text-[10px] text-slate-400 hover:text-blue-300 font-mono px-2 py-1 rounded bg-[#0c121e] border border-[#18263a] transition cursor-pointer"
                    title="Reset to heuristic column match"
                  >
                    <RotateCcw className="w-2.5 h-2.5" />
                    Reset
                  </button>
                </div>
              </div>

              {/* 4 Mapping Dropdowns */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* 1. Date Column */}
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                    <span>Date Column <span className="text-rose-400">*</span></span>
                    {selectedDateCol && (
                      <span className="text-[9px] font-mono text-emerald-400">Mapped</span>
                    )}
                  </label>
                  <select
                    value={selectedDateCol}
                    onChange={(e) => setSelectedDateCol(e.target.value)}
                    className="w-full px-2.5 py-1.5 bg-[#060a12] border border-[#18263a] focus:border-blue-500 rounded-lg text-xs text-slate-100 font-mono focus:outline-none"
                  >
                    <option value="">-- Select Date Header --</option>
                    {csvHeaders.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 2. Narration / Description */}
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                    <span>Narration / Description <span className="text-rose-400">*</span></span>
                    {selectedNarrationCol && (
                      <span className="text-[9px] font-mono text-emerald-400">Mapped</span>
                    )}
                  </label>
                  <select
                    value={selectedNarrationCol}
                    onChange={(e) => setSelectedNarrationCol(e.target.value)}
                    className="w-full px-2.5 py-1.5 bg-[#060a12] border border-[#18263a] focus:border-blue-500 rounded-lg text-xs text-slate-100 font-mono focus:outline-none"
                  >
                    <option value="">-- Select Narration Header --</option>
                    {csvHeaders.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 3. Amount / Credit Column */}
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                    <span>Amount / Credit Column <span className="text-rose-400">*</span></span>
                    {selectedAmountCol && (
                      <span className="text-[9px] font-mono text-emerald-400">Mapped</span>
                    )}
                  </label>
                  <select
                    value={selectedAmountCol}
                    onChange={(e) => setSelectedAmountCol(e.target.value)}
                    className="w-full px-2.5 py-1.5 bg-[#060a12] border border-[#18263a] focus:border-blue-500 rounded-lg text-xs text-slate-100 font-mono focus:outline-none"
                  >
                    <option value="">-- Select Amount / Credit Header --</option>
                    {csvHeaders.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 4. Reference / UTR Column */}
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                    <span>Reference / UTR Column</span>
                    <span className="text-[9px] font-mono text-slate-400">Optional</span>
                  </label>
                  <select
                    value={selectedRefCol}
                    onChange={(e) => setSelectedRefCol(e.target.value)}
                    className="w-full px-2.5 py-1.5 bg-[#060a12] border border-[#18263a] focus:border-blue-500 rounded-lg text-xs text-slate-100 font-mono focus:outline-none"
                  >
                    <option value="__none__">-- (Auto-extract UTR from narration) --</option>
                    {csvHeaders.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Live 3-Row Data Preview Table */}
              <div className="space-y-1.5 pt-2">
                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                  <div className="flex items-center gap-1.5 text-slate-300">
                    <Table className="w-3.5 h-3.5 text-blue-400" />
                    <span className="font-semibold">Live Data Preview</span>
                    <span className="text-[10px] text-slate-400">(First 3 rows)</span>
                  </div>
                  <span className="text-[10px] text-slate-400">
                    {csvSampleRows.length} rows previewed
                  </span>
                </div>

                <div className="overflow-x-auto border border-[#18263a] rounded-lg bg-[#060a12]">
                  <table className="w-full text-[11px] text-left">
                    <thead className="bg-[#0c121e] text-slate-400 font-mono text-[10px] border-b border-[#18263a]">
                      <tr>
                        <th className="px-2.5 py-1.5 font-medium w-8 text-center">#</th>
                        <th className="px-2.5 py-1.5 font-medium">Date</th>
                        <th className="px-2.5 py-1.5 font-medium">Narration / Description</th>
                        <th className="px-2.5 py-1.5 font-medium">Amount (₹)</th>
                        <th className="px-2.5 py-1.5 font-medium">Reference / UTR</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#18263a]/60 font-mono">
                      {livePreviewRows.length > 0 ? (
                        livePreviewRows.map((r, idx) => (
                          <tr key={idx} className="hover:bg-[#0c1424]">
                            <td className="px-2.5 py-1.5 text-slate-400 text-center">{idx + 1}</td>
                            <td className="px-2.5 py-1.5 text-slate-200">
                              {r.date || <span className="text-slate-400 italic">Not mapped</span>}
                            </td>
                            <td className="px-2.5 py-1.5 text-slate-300 truncate max-w-[160px]">
                              {r.narration || <span className="text-slate-400 italic">Not mapped</span>}
                            </td>
                            <td className="px-2.5 py-1.5 text-emerald-400 font-medium">
                              {r.amount || <span className="text-slate-400 italic">Not mapped</span>}
                            </td>
                            <td className="px-2.5 py-1.5 text-slate-300">
                              {r.ref || <span className="text-slate-400 italic">—</span>}
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={5} className="px-3 py-3 text-center text-slate-400 italic">
                            No data rows detected in preview chunk
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Password Protection Section (for PDF files) */}
          {(!file || isPdf) && (
            <div
              className={`p-3.5 rounded-xl border transition-colors ${
                isPasswordError ? "bg-rose-950/20 border-rose-700/80" : "bg-[#090e18] border-[#162438]"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5 text-amber-400" />
                  <span>PDF Password (if protected)</span>
                </label>
                <button
                  type="button"
                  onClick={() => setShowHints(!showHints)}
                  className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-1 font-mono transition"
                >
                  <HelpCircle className="w-3 h-3" />
                  <span>Password Formulas Guide</span>
                  {showHints ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
              </div>

              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                  <Lock className="w-3.5 h-3.5" />
                </div>
                <input
                  ref={passwordInputRef}
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password (e.g. DOB, CustID, PAN, Name+DDMM)"
                  className="w-full pl-9 pr-10 py-2 bg-[#060a12] border border-[#18263a] focus:border-blue-500 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none transition shadow-inner font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-200 transition"
                >
                  {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </div>

              {/* Bank Password Logic Cheat Sheet */}
              {showHints && (
                <div className="mt-3 pt-3 border-t border-[#18263a] space-y-2 animate-in fade-in duration-200">
                  <div className="text-[10px] font-bold text-slate-300 uppercase tracking-wider font-mono">
                    <span>Common Bank Password Formulas</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-40 overflow-y-auto pr-1">
                    {hints.map((h, i) => (
                      <div
                        key={i}
                        className="p-2 bg-[#0c121e] border border-[#18263a] rounded-lg text-[10px]"
                      >
                        <div className="font-semibold text-blue-300 flex items-center justify-between">
                          <span>{h.bank}</span>
                        </div>
                        <div className="text-slate-300 text-[9px] mt-0.5 line-clamp-2">
                          {h.pattern}
                        </div>
                        <div className="text-slate-500 text-[8px] font-mono mt-0.5">
                          e.g. <span className="text-slate-400 font-semibold">{h.example}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Sample Templates */}
          <div className="bg-[#090e18] p-3 rounded-xl border border-[#162438] space-y-2">
            <div className="text-[10px] uppercase font-bold text-slate-400 flex items-center justify-between font-mono">
              <span>Test Statement Downloads</span>
              <span className="text-[9px] text-blue-400 flex items-center gap-1">
                <Layers className="w-3 h-3" /> Multi-Page Statements
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {["HDFC", "ICICI", "SBI"].map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => downloadSample(b)}
                  className="px-3 py-1.5 bg-[#060a12] hover:bg-[#0c1424] border border-[#18263a] text-slate-300 hover:text-blue-300 rounded-lg text-[10px] font-mono flex items-center gap-1.5 transition shadow-2xs cursor-pointer"
                >
                  <Download className="w-3 h-3 text-blue-400" />
                  {b} Statement.csv
                </button>
              ))}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-xl text-rose-200 flex items-start gap-2.5 text-xs animate-in fade-in">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div className="space-y-1 flex-1">
                <p className="font-bold text-rose-300">
                  {isPasswordError ? "Password Required / Invalid" : "Upload Failed"}
                </p>
                <p className="text-rose-200/90 leading-tight">{error}</p>
                {validationErrors && validationErrors.length > 0 && (
                  <ul className="mt-1.5 list-disc list-inside space-y-0.5 text-[10px] text-rose-300/90 max-h-28 overflow-y-auto bg-rose-950/80 p-2 rounded-lg border border-rose-900/60 font-mono">
                    {validationErrors.map((e, idx) => (
                      <li key={idx}>{e}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#111318] border-t border-[#1e222d] flex flex-col-reverse sm:flex-row justify-end gap-2 text-xs font-sans shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-300 rounded-md transition text-center cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={
              !file ||
              uploading ||
              (isCsv && showMapper && (!selectedDateCol || !selectedAmountCol || !selectedNarrationCol))
            }
            className="w-full sm:w-auto px-5 py-2 bg-neutral-100 hover:bg-white disabled:opacity-40 text-neutral-900 font-semibold rounded-md shadow-xs transition flex items-center justify-center gap-2 text-center cursor-pointer"
          >
            {uploading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin"></div>
                <span>Parsing & Reconciling...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Upload & Reconcile</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
