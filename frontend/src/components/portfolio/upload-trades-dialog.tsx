"use client";

import { useRef, useState } from "react";
import { uploadTrades, UploadTradesResult } from "@/lib/api";

interface UploadTradesDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

type UploadState = "idle" | "validating" | "uploading" | "done" | "error";

export default function UploadTradesDialog({
  isOpen,
  onClose,
  onSuccess,
}: UploadTradesDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [result, setResult] = useState<UploadTradesResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const MAX_SIZE = 10 * 1024 * 1024; // 10 MB

  if (!isOpen) return null;

  const handleClose = () => {
    // Reset state fully on close
    setSelectedFile(null);
    setUploadState("idle");
    setResult(null);
    setErrorMessage(null);
    setIsDragging(false);
    onClose();
  };

  const validateFile = (file: File): string | null => {
    const allowed = [".csv", ".xlsx", ".xls"];
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      return "Only CSV and XLSX files are supported.";
    }
    if (file.size > MAX_SIZE) {
      return `File is too large (${(file.size / (1024 * 1024)).toFixed(1)} MB). Maximum allowed size is 10 MB.`;
    }
    return null;
  };

  const handleFileSelect = (file: File) => {
    setResult(null);
    setErrorMessage(null);
    setUploadState("validating");

    const err = validateFile(file);
    if (err) {
      setErrorMessage(err);
      setUploadState("error");
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
    setUploadState("idle");
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFileSelect(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploadState("uploading");
    setErrorMessage(null);
    setResult(null);

    try {
      const res = await uploadTrades(selectedFile);
      setResult(res);
      setUploadState("done");
      if (res.imported > 0) {
        onSuccess();
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Upload failed. Please try again.");
      setUploadState("error");
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const isUploading = uploadState === "uploading";

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 backdrop-blur-sm">
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="w-full max-w-lg bg-zinc-900 border border-zinc-800 rounded-3xl p-6 shadow-2xl animate-scale-in text-left">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <div className="flex items-center gap-3">
              {/* Upload Icon */}
              <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <svg className="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-bold text-zinc-100">Bulk Trade Upload</h3>
                <p className="text-[11px] text-zinc-400 font-medium">CSV or XLSX · Max 10 MB</p>
              </div>
            </div>
            <button
              onClick={handleClose}
              disabled={isUploading}
              className="p-1.5 rounded-lg text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors disabled:opacity-40"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Format hint */}
          <div className="mb-4 p-3 rounded-xl bg-zinc-800/60 border border-zinc-700/50 text-xs text-zinc-400 leading-relaxed space-y-1">
            <p className="font-semibold text-zinc-300 flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5 text-indigo-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              AI automatically maps your column headers
            </p>
            <p>
              Common supported columns: <span className="font-mono text-zinc-300">Symbol</span>,{" "}
              <span className="font-mono text-zinc-300">Buy/Sell</span>,{" "}
              <span className="font-mono text-zinc-300">Qty</span>,{" "}
              <span className="font-mono text-zinc-300">Price</span>,{" "}
              <span className="font-mono text-zinc-300">Date</span>,{" "}
              <span className="font-mono text-zinc-300">Fees</span>
            </p>
          </div>

          {/* Drop zone */}
          {uploadState !== "done" && (
            <div
              ref={dropRef}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => !isUploading && fileInputRef.current?.click()}
              className={`relative flex flex-col items-center justify-center gap-3 p-8 rounded-2xl border-2 border-dashed transition-all cursor-pointer select-none ${
                isUploading
                  ? "border-zinc-700 bg-zinc-800/30 cursor-not-allowed"
                  : isDragging
                  ? "border-indigo-500 bg-indigo-500/10"
                  : selectedFile
                  ? "border-emerald-500/50 bg-emerald-500/5 hover:bg-emerald-500/10"
                  : "border-zinc-700 bg-zinc-800/20 hover:border-indigo-500/50 hover:bg-indigo-500/5"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={handleInputChange}
                className="hidden"
                disabled={isUploading}
              />

              {isUploading ? (
                <>
                  <svg className="w-8 h-8 text-indigo-400 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <p className="text-sm font-semibold text-indigo-300">Parsing & importing trades…</p>
                  <p className="text-xs text-zinc-400">AI is mapping columns. This may take a few seconds.</p>
                </>
              ) : selectedFile ? (
                <>
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                    <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-bold text-zinc-100">{selectedFile.name}</p>
                    <p className="text-xs text-zinc-400 mt-0.5">{formatBytes(selectedFile.size)}</p>
                  </div>
                  <p className="text-[11px] text-zinc-500">Click to change file</p>
                </>
              ) : (
                <>
                  <div className="w-10 h-10 rounded-xl bg-zinc-700/60 border border-zinc-600/50 flex items-center justify-center">
                    <svg className="w-5 h-5 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-semibold text-zinc-300">
                      Drop your file here, or <span className="text-indigo-400">browse</span>
                    </p>
                    <p className="text-xs text-zinc-500 mt-0.5">CSV or XLSX, up to 10 MB</p>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Error message */}
          {errorMessage && (
            <div className="mt-4 p-3 bg-rose-950/40 border border-rose-500/20 rounded-xl text-xs text-rose-400 font-medium">
              {errorMessage}
            </div>
          )}

          {/* Result panel (shown after done) */}
          {uploadState === "done" && result && (
            <div className="space-y-4">
              {/* Summary cards */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-center">
                  <p className="text-2xl font-extrabold text-emerald-400">{result.imported}</p>
                  <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wide mt-0.5">Imported</p>
                </div>
                <div className={`p-4 rounded-xl border text-center ${
                  result.duplicates > 0
                    ? "bg-amber-500/10 border-amber-500/20"
                    : "bg-zinc-800/60 border-zinc-700/50"
                }`}>
                  <p className={`text-2xl font-extrabold ${result.duplicates > 0 ? "text-amber-400" : "text-zinc-400"}`}>
                    {result.duplicates ?? 0}
                  </p>
                  <p className={`text-[10px] font-semibold uppercase tracking-wide mt-0.5 ${result.duplicates > 0 ? "text-amber-500" : "text-zinc-500"}`}>
                    Duplicates
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-zinc-800/60 border border-zinc-700/50 text-center">
                  <p className="text-2xl font-extrabold text-zinc-300">{result.skipped}</p>
                  <p className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wide mt-0.5">Parse Errors</p>
                </div>
                <div className={`p-4 rounded-xl border text-center ${
                  result.errors.length > 0
                    ? "bg-rose-500/10 border-rose-500/20"
                    : "bg-zinc-800/60 border-zinc-700/50"
                }`}>
                  <p className={`text-2xl font-extrabold ${result.errors.length > 0 ? "text-rose-400" : "text-zinc-400"}`}>
                    {result.errors.length}
                  </p>
                  <p className={`text-[10px] font-semibold uppercase tracking-wide mt-0.5 ${result.errors.length > 0 ? "text-rose-500" : "text-zinc-500"}`}>
                    Row Errors
                  </p>
                </div>
              </div>

              {/* Success message */}
              <div className={`p-3 rounded-xl border text-xs font-medium ${
                result.imported > 0
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : "bg-zinc-800/60 border-zinc-700/50 text-zinc-400"
              }`}>
                {result.message}
              </div>

              {/* Per-row errors list */}
              {result.errors.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wide">Row Errors</p>
                  <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                    {result.errors.map((err, idx) => (
                      <div key={idx} className="text-[11px] text-rose-400 font-medium leading-snug px-2 py-1 rounded-lg bg-rose-500/5 border border-rose-500/10">
                        {err}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-3 justify-end mt-6 pt-4 border-t border-zinc-800">
            {uploadState === "done" ? (
              <button
                onClick={handleClose}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold shadow-md shadow-indigo-600/10 transition-all cursor-pointer border border-indigo-500/20 active:scale-95"
              >
                Done
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleClose}
                  disabled={isUploading}
                  className="px-4 py-2 rounded-xl border border-zinc-800 text-sm font-medium hover:bg-zinc-800 text-zinc-300 transition-colors disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  onClick={handleUpload}
                  disabled={!selectedFile || isUploading}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-semibold shadow-md shadow-indigo-600/10 transition-all cursor-pointer border border-indigo-500/20 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isUploading ? (
                    <>
                      <svg className="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Importing…
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}
                          d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                      </svg>
                      Import Trades
                    </>
                  )}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
