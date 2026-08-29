import React, { useState, useRef, useEffect } from "react";
import { X, UploadCloud, FileText, Download, CheckCircle2, AlertCircle } from "lucide-react";
import { uploadBankCsv, API_BASE } from "@/lib/api";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadSuccess: () => void;
}

export const UploadModal: React.FC<UploadModalProps> = ({
  isOpen,
  onClose,
  onUploadSuccess,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setError(null);
    }
  };

  const handleSubmit = async () => {
    if (!file) {
      setError("Please select a bank statement CSV file to upload.");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      await uploadBankCsv(file);
      onUploadSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to parse CSV statement.");
    } finally {
      setUploading(false);
    }
  };

  const downloadSample = (bank: string) => {
    window.open(`${API_BASE}/demo/sample-statement?bank=${bank}`, "_blank");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-2.5 sm:p-4">
      <div className="bg-[#0f1624] border border-[#1c2b42] rounded-lg max-w-md w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-3 sm:p-3.5 bg-[#121a2a] border-b border-[#1c2b42] flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <UploadCloud className="w-4 h-4 text-blue-400 shrink-0" />
            <div>
              <h3 className="text-xs font-semibold text-slate-100 font-sans">
                Upload Bank Statement CSV
              </h3>
              <p className="text-[9px] sm:text-[10px] text-slate-400 font-mono">
                Auto-detection: HDFC, ICICI, SBI, Axis & Generic Formats
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1 rounded transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-3 sm:p-4 space-y-3 text-xs font-sans overflow-y-auto touch-scroll flex-1">
          {/* Dropzone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="border border-dashed border-[#233550] hover:border-blue-500/70 bg-[#0b101b] rounded p-4 sm:p-5 text-center cursor-pointer transition group"
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".csv"
              className="hidden"
            />
            <UploadCloud className="w-6 h-6 sm:w-7 sm:h-7 text-blue-500 mx-auto mb-1.5 transition-transform group-hover:scale-105" />
            {file ? (
              <div className="flex items-center justify-center gap-2 text-slate-200 font-mono">
                <FileText className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="font-semibold text-xs truncate max-w-[200px]">{file.name}</span>
                <span className="text-[10px] text-slate-400 font-tabular shrink-0">
                  ({(file.size / 1024).toFixed(1)} KB)
                </span>
              </div>
            ) : (
              <div>
                <p className="text-slate-200 font-medium mb-0.5 text-xs">
                  Click to browse or drag & drop bank statement CSV
                </p>
                <p className="text-[9px] sm:text-[10px] text-slate-400 font-mono">
                  Stream-parsed with SHA-256 deduplication and date normalization
                </p>
              </div>
            )}
          </div>

          {/* Sample Templates */}
          <div className="bg-[#0b101b] p-2 sm:p-2.5 rounded border border-[#1c2b42]">
            <div className="text-[9px] sm:text-[10px] uppercase font-semibold text-slate-400 mb-1.5 flex items-center justify-between font-mono">
              <span>Test Statement Downloads</span>
              <span className="text-[9px] text-slate-400">Track 04 Datasets</span>
            </div>
            <div className="flex flex-wrap gap-1 sm:gap-1.5">
              {["HDFC", "ICICI", "SBI"].map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => downloadSample(b)}
                  className="px-2 py-0.5 bg-[#0f1624] hover:bg-[#142033] border border-[#1c2b42] text-slate-300 hover:text-blue-300 rounded text-[9px] sm:text-[10px] font-mono flex items-center gap-1 transition"
                >
                  <Download className="w-3 h-3" />
                  {b} Statement.csv
                </button>
              ))}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-2.5 bg-rose-950/40 border border-rose-800/60 rounded text-rose-300 flex items-start gap-2 text-[10px] sm:text-[11px]">
              <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-2.5 sm:p-3 bg-[#0a0f19] border-t border-[#182538] flex flex-col-reverse sm:flex-row justify-end gap-2 text-xs font-sans shrink-0">
          <button
            onClick={onClose}
            className="w-full sm:w-auto px-3 py-1.5 bg-[#121b2b] hover:bg-[#182338] border border-[#1c2b42] text-slate-300 rounded transition text-center"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!file || uploading}
            className="w-full sm:w-auto px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium rounded shadow-sm transition flex items-center justify-center gap-1.5 text-center"
          >
            {uploading ? (
              <>
                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Parsing & Reconciling...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Upload & Reconcile</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
