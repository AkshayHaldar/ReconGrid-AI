import React, { useState, useRef, useEffect } from "react";
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
  Sparkles,
  Layers,
  KeyRound,
} from "lucide-react";
import { uploadBankStatement, fetchBankPasswordHints, API_BASE } from "@/lib/api";

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

  if (!isOpen) return null;

  const isPdf = file?.name.toLowerCase().endsWith(".pdf");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      setFile(selected);
      setError(null);
      setValidationErrors([]);
      setIsPasswordError(false);
      if (selected.name.toLowerCase().endsWith(".pdf")) {
        setTimeout(() => passwordInputRef.current?.focus(), 100);
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const selected = e.dataTransfer.files[0];
      setFile(selected);
      setError(null);
      setValidationErrors([]);
      setIsPasswordError(false);
      if (selected.name.toLowerCase().endsWith(".pdf")) {
        setTimeout(() => passwordInputRef.current?.focus(), 100);
      }
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
      await uploadBankStatement(file, "default", password);
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-3 sm:p-4">
      <div className="bg-[#070b14] border border-[#18263a] rounded-2xl max-w-lg w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="p-4 bg-[#0a101d] border-b border-[#18263a] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-500/10 border border-blue-500/20 rounded-xl">
              <UploadCloud className="w-5 h-5 text-blue-400 shrink-0" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100 font-sans flex items-center gap-2">
                Upload Bank Statement
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-950 text-blue-300 border border-blue-800">
                  PDF & CSV
                </span>
              </h3>
              <p className="text-[11px] text-slate-400 font-mono">
                Multi-page statement parsing, auto-decryption & OCR enabled
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-800/50 transition"
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
                <div className="flex items-center justify-center gap-2 text-[10px] text-slate-400">
                  <span className="inline-flex items-center gap-1 text-blue-400">
                    <Sparkles className="w-3 h-3" /> {isPdf ? "Multi-Page PDF Engine" : "Streaming CSV Parser"}
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
                  Supports password-protected PDFs & multi-page statements (HDFC, ICICI, SBI, Axis, etc.)
                </p>
              </div>
            )}
          </div>

          {/* Password Protection Section */}
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
                  className="px-3 py-1.5 bg-[#060a12] hover:bg-[#0c1424] border border-[#18263a] text-slate-300 hover:text-blue-300 rounded-lg text-[10px] font-mono flex items-center gap-1.5 transition shadow-2xs"
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
        <div className="p-4 bg-[#0a101d] border-t border-[#18263a] flex flex-col-reverse sm:flex-row justify-end gap-2 text-xs font-sans shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 bg-[#0e1626] hover:bg-[#162338] border border-[#18263a] text-slate-300 rounded-xl transition text-center"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!file || uploading}
            className="w-full sm:w-auto px-5 py-2 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 disabled:opacity-50 text-white font-bold rounded-xl shadow-md shadow-blue-600/25 transition flex items-center justify-center gap-2 text-center"
          >
            {uploading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Parsing & Reconciling...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4" />
                <span>Upload & Reconcile</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
