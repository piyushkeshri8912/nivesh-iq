"use client";

import { useEffect, useState } from "react";
import { addWatchlistItem } from "@/lib/api";

interface AddWatchlistDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function AddWatchlistDialog({
  isOpen,
  onClose,
  onSuccess,
}: AddWatchlistDialogProps) {
  const [symbol, setSymbol] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSymbol("");
      setError(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    const cleanSymbol = symbol.trim().toUpperCase();

    if (!cleanSymbol) {
      setError("Ticker symbol is required.");
      setSubmitting(false);
      return;
    }

    try {
      await addWatchlistItem({
        symbol: cleanSymbol,
      });
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to add watchlist item.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 backdrop-blur-sm">
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="w-full max-w-md bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-2xl animate-scale-in text-left">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">
              Add Watchlist Candidate
            </h3>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-rose-50 border border-rose-100 text-rose-800 text-xs rounded-xl dark:bg-rose-950/20 dark:border-rose-900/40 dark:text-rose-400">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                Stock Symbol
              </label>
              <input
                type="text"
                placeholder="e.g. INFY.NS, TCS, HDFCBANK.NS"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full px-3.5 py-2.5 border border-zinc-200 dark:border-zinc-850 rounded-xl bg-zinc-50 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:border-indigo-500 text-sm font-medium"
              />
              <p className="text-[10px] text-zinc-400 dark:text-zinc-500">
                Use suffix .NS for NSE stocks (e.g., RELIANCE.NS)
              </p>
            </div>

            <div className="flex gap-3 justify-end pt-4 border-t border-zinc-150 dark:border-zinc-800 mt-6">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl border border-zinc-200 dark:border-zinc-800 text-sm font-medium hover:bg-zinc-50 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-medium shadow-md shadow-indigo-600/10 transition-colors disabled:opacity-50"
              >
                {submitting ? "Adding..." : "Add to Watchlist"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

