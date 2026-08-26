import React, { useState, useRef } from "react";
import { X, UploadCloud, FileText, Download, CheckCircle2, AlertCircle } from "lucide-react";
import { uploadBankCsv } from "@/lib/api";

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
  const [bankFormat, setBankFormat] = useState("AUTO");
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    window.open(`http://127.0.0.1:8000/api/v1/demo/sample-statement?bank=${bank}`, "_blank");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="bg-[#0e1626] border border-[#21314d] rounded-xl max-w-lg w-full overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="p-4 bg-[#121c2e] border-b border-[#21314d] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-blue-400" />
            <div>
              <h3 className="text-sm font-semibold text-slate-100">
                Upload Bank Statement CSV
              </h3>
              <p className="text-[11px] text-slate-400">
                Supports HDFC, ICICI, SBI, Axis, and Generic formats
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1 rounded-md transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4 text-xs">
          {/* Dropzone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-[#293c5c] hover:border-blue-500/80 bg-[#090f1a] rounded-xl p-6 text-center cursor-pointer transition group"
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".csv"
              className="hidden"
            />
            <UploadCloud className="w-8 h-8 text-blue-500 mx-auto mb-2 transition-transform group-hover:scale-110" />
            {file ? (
              <div className="flex items-center justify-center gap-2 text-slate-200 font-mono">
                <FileText className="w-4 h-4 text-emerald-400" />
                <span className="font-semibold">{file.name}</span>
                <span className="text-[10px] text-slate-500">
                  ({(file.size / 1024).toFixed(1)} KB)
                </span>
              </div>
            ) : (
              <div>
                <p className="text-slate-200 font-medium mb-1">
                  Click to browse or drag & drop CSV here
                </p>
                <p className="text-[11px] text-slate-500">
                  Stream-parsed with automatic delimiter & column dialect detection
                </p>
              </div>
            )}
          </div>

          {/* Sample Templates */}
          <div className="bg-[#121c2e] p-3 rounded-lg border border-[#1f2c42]">
            <div className="text-[10px] uppercase font-semibold text-slate-400 mb-2 flex items-center justify-between">
              <span>Download Test Bank Templates</span>
              <span className="text-[9px] text-slate-500 font-mono">Track 04 Ready</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {["HDFC", "ICICI", "SBI"].map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => downloadSample(b)}
                  className="px-2.5 py-1 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 hover:text-blue-300 rounded text-[11px] font-mono flex items-center gap-1 transition"
                >
                  <Download className="w-3 h-3" />
                  {b} Statement.csv
                </button>
              ))}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-3 bg-rose-950/60 border border-rose-800 rounded-lg text-rose-300 flex items-start gap-2 text-[11px]">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3.5 bg-[#0a101d] border-t border-[#182337] flex justify-end gap-2 text-xs">
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!file || uploading}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium rounded-lg shadow-md transition flex items-center gap-1.5"
          >
            {uploading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Parsing & Reconciling...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Upload & Run Engine</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
