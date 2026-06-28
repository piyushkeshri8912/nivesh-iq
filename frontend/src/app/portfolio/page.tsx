"use client";

import { useEffect, useState } from "react";
import { 
  fetchHoldings, 
  fetchTransactions, 
  deleteTransaction, 
  fetchExposures,
  fetchLatestPortfolioReview,
  generatePortfolioReview,
  fetchPerformanceHistory,
  fetchProfile,
  triggerSnapshot,
  PortfolioHoldingsListResponse, 
  TransactionResponse,
  ExposuresResponse,
  PortfolioReviewResponse,
  PortfolioSnapshotResponse,
  UserProfileResponse,
  loginWithGoogle
} from "@/lib/api";
import AddTransactionDialog from "@/components/portfolio/add-transaction-dialog";
import UploadTradesDialog from "@/components/portfolio/upload-trades-dialog";
import PerformanceChart from "@/components/portfolio/performance-chart";
import AllocationChart from "@/components/portfolio/allocation-chart";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function PortfolioPage() {
  const [data, setData] = useState<PortfolioHoldingsListResponse | null>(null);
  const [transactions, setTransactions] = useState<TransactionResponse[]>([]);
  const [exposures, setExposures] = useState<ExposuresResponse | null>(null);
  const [review, setReview] = useState<PortfolioReviewResponse | null>(null);
  const [history, setHistory] = useState<PortfolioSnapshotResponse[]>([]);
  const [profile, setProfile] = useState<UserProfileResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [generatingReview, setGeneratingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [isCapturingSnapshot, setIsCapturingSnapshot] = useState(false);
  const [mainTab, setMainTab] = useState<"ledger" | "analytics">("ledger");
  const [activeTab, setActiveTab] = useState<"holdings" | "history">("holdings");
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  const loadPortfolioData = async () => {
    setLoading(true);
    try {
      const holdingsData = await fetchHoldings();
      const txData = await fetchTransactions();
      setData(holdingsData);
      setTransactions(txData);

      // Load analytics and user profile
      const [exposuresData, reviewData, historyData, profileData] = await Promise.all([
        fetchExposures(),
        fetchLatestPortfolioReview(),
        fetchPerformanceHistory(),
        fetchProfile()
      ]);
      setExposures(exposuresData);
      setReview(reviewData);
      setHistory(historyData);
      setProfile(profileData);
    } catch (err) {
      console.error("Failed to load portfolio details:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateReview = async () => {
    setGeneratingReview(true);
    setReviewError(null);
    try {
      const newReview = await generatePortfolioReview();
      setReview(newReview);
    } catch (err: any) {
      console.error(err);
      setReviewError(err.message || "Failed to generate AI review");
    } finally {
      setGeneratingReview(false);
    }
  };


  useEffect(() => {
    loadPortfolioData();
  }, []);

  const renderTextWithCitations = (text: string, references: any[]) => {
    if (!text) return "";
    const parts = text.split(/(\[[0-9]+\])/g);
    return parts.map((part, index) => {
      const match = part.match(/^\[([0-9]+)\]$/);
      if (match) {
        const refIdx = parseInt(match[1], 10) - 1;
        const ref = references && references[refIdx];
        if (ref) {
          return (
            <span key={index} className="relative inline-block group cursor-help mx-0.5 select-none">
              <span className="inline-flex items-center justify-center bg-indigo-50 hover:bg-indigo-600 hover:text-white dark:bg-indigo-950/80 dark:text-indigo-400 font-extrabold text-[10px] rounded px-1.5 py-0.2 font-mono shadow-sm transition-colors">
                [{refIdx + 1}]
              </span>
              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-3 bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 text-xs text-zinc-700 dark:text-zinc-300 rounded-xl shadow-xl opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 pointer-events-none group-hover:pointer-events-auto transition-all duration-200 z-50 flex flex-col gap-1">
                <span className="flex items-center justify-between text-[9px] font-black text-indigo-500 uppercase tracking-wide">
                  <span>Reference [{refIdx + 1}]</span>
                  <span className="text-zinc-400 dark:text-zinc-500 font-medium">({ref.source || "News"})</span>
                </span>
                <span className="font-extrabold text-zinc-900 dark:text-zinc-150 text-[11px] leading-snug line-clamp-2">
                  {ref.title}
                </span>
                {ref.link && (
                  <a
                    href={ref.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 self-end inline-flex items-center gap-1 font-black text-[9px] uppercase tracking-wide text-indigo-650 dark:text-indigo-400 hover:underline cursor-pointer"
                  >
                    Source Link
                    <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                )}
              </span>
            </span>
          );
        }
      }
      return part;
    });
  };


  const handleDeleteTransaction = async (id: number) => {
    if (confirm("Are you sure you want to delete this transaction? This will recalculate all holdings instantly.")) {
      const success = await deleteTransaction(id);
      if (success) {
        loadPortfolioData();
      } else {
        alert("Failed to delete transaction.");
      }
    }
  };

  const handleCaptureSnapshot = async () => {
    setIsCapturingSnapshot(true);
    try {
      const res = await triggerSnapshot();
      if (res) {
        await loadPortfolioData();
      } else {
        alert("Failed to capture snapshot. Check if active holdings exist.");
      }
    } catch (err) {
      console.error("Error capturing snapshot:", err);
      alert("Error capturing snapshot.");
    } finally {
      setIsCapturingSnapshot(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 bg-zinc-200 dark:bg-zinc-800 rounded-lg animate-pulse" />
        <div className="grid gap-6 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 bg-zinc-200 dark:bg-zinc-800 rounded-2xl animate-pulse" />
          ))}
        </div>
        <div className="h-96 bg-zinc-200 dark:bg-zinc-800 rounded-3xl animate-pulse" />
      </div>
    );
  }

  const holdings = data?.holdings || [];
  const summary = data?.summary || {
    total_cost: 0,
    total_value: 0,
    total_unrealized_pnl: 0,
    total_unrealized_pnl_percent: 0,
    total_realized_pnl: 0,
  };

  const isGain = summary.total_unrealized_pnl >= 0;

  return (
    <div className="space-y-8 animate-fade-in text-left">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-zinc-100">
            Portfolio
          </h1>
          <p className="text-xs sm:text-sm text-zinc-400 font-medium">
            Track assets, monitor gains and see analytics
          </p>
        </div>
        
        <div className="flex flex-wrap items-center gap-2.5 sm:gap-3 shrink-0">
          {/* Upload CSV / XLSX button */}
          <button
            onClick={() => setIsUploadOpen(true)}
            className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-xl text-xs sm:text-sm font-semibold flex items-center gap-1.5 transition-all shrink-0 cursor-pointer border border-zinc-700/60 active:scale-95"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            Upload CSV
          </button>

          {/* Manual log trade button */}
          <button
            onClick={() => setIsDialogOpen(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs sm:text-sm font-semibold shadow-md shadow-indigo-600/10 flex items-center gap-1.5 transition-all shrink-0 cursor-pointer border border-indigo-500/20 active:scale-95"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            Log Trade
          </button>
        </div>
      </div>

      {/* Metrics Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        

        <div className="p-5 sm:p-6 rounded-2xl bg-zinc-900/50 border border-zinc-800 shadow-xl shadow-black/10 backdrop-blur-md space-y-2">
          <p className="text-[10px] sm:text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            Total invested capital
          </p>
          <p className="text-xl sm:text-2xl font-bold text-zinc-100">
            ₹{summary.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>

        <div className="p-5 sm:p-6 rounded-2xl bg-zinc-900/50 border border-zinc-800 shadow-xl shadow-black/10 backdrop-blur-md space-y-2">
          <p className="text-[10px] sm:text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            Portfolio Value
          </p>
          <p className="text-xl sm:text-2xl font-bold text-zinc-100">
            ₹{summary.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>

        <div className="p-5 sm:p-6 rounded-2xl bg-zinc-900/50 border border-zinc-800 shadow-xl shadow-black/10 backdrop-blur-md space-y-2">
          <div className="flex justify-between items-start">
            <p className="text-[10px] sm:text-xs font-semibold text-zinc-400 uppercase tracking-wider">
              Unrealized Returns
            </p>
            <span
              className={`inline-flex items-center gap-0.5 text-[10px] sm:text-xs font-bold px-2 py-0.5 rounded ${
                isGain
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
              }`}
            >
              {isGain ? "+" : ""}
              {summary.total_unrealized_pnl_percent.toFixed(2)}%
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={`text-xl sm:text-2xl font-bold ${
                isGain ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              ₹{summary.total_unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        </div>

        <div className="p-5 sm:p-6 rounded-2xl bg-zinc-900/50 border border-zinc-800 shadow-xl shadow-black/10 backdrop-blur-md space-y-2">
          <p className="text-[10px] sm:text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            Realized Returns
          </p>
          <p
            className={`text-xl sm:text-2xl font-bold ${
              summary.total_realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            ₹{summary.total_realized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>
      </div>

      {/* Modern Horizontal Navigation Tabs */}
      <div className="flex overflow-x-auto whitespace-nowrap scrollbar-none border border-zinc-800 gap-1 bg-zinc-900/40 p-1 rounded-xl">
        <button
          onClick={() => setMainTab("ledger")}
          className={`py-2 px-4 sm:py-2.5 sm:px-6 text-xs sm:text-sm font-semibold rounded-lg transition-all cursor-pointer ${
            mainTab === "ledger"
              ? "bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700/50 font-bold"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30"
          }`}
        >
          Holdings
        </button>
        <button
          onClick={() => setMainTab("analytics")}
          className={`py-2 px-4 sm:py-2.5 sm:px-6 text-xs sm:text-sm font-semibold rounded-lg transition-all cursor-pointer ${
            mainTab === "analytics"
              ? "bg-zinc-800 text-zinc-100 shadow-sm border border-zinc-700/50 font-bold"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30"
          }`}
        >
          Analytics 
        </button>
      </div>

      {/* Main Container based on active tab */}
      {mainTab === "ledger" && (
        <div className="bg-zinc-900/30 border border-zinc-800 rounded-2xl overflow-hidden shadow-lg shadow-black/25">
          <div className="px-8 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/50">
            <div className="flex gap-6">
              <button
                onClick={() => setActiveTab("holdings")}
                className={`py-4 text-sm font-semibold border-b-2 transition-colors focus:outline-none cursor-pointer ${
                  activeTab === "holdings"
                    ? "border-indigo-500 text-indigo-400"
                    : "border-transparent text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Active Holdings
              </button>
              <button
                onClick={() => setActiveTab("history")}
                className={`py-4 text-sm font-semibold border-b-2 transition-colors focus:outline-none cursor-pointer ${
                  activeTab === "history"
                    ? "border-indigo-500 text-indigo-400"
                    : "border-transparent text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Trade History ({transactions.length})
              </button>
            </div>
          </div>

          {/* Tab 1: Holdings Table */}
          {activeTab === "holdings" && (
            <div className="overflow-x-auto">
              {holdings.length === 0 ? (
                <div className="text-center p-16 space-y-4">
                  <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center justify-center mx-auto">
                    <svg
                      className="w-6 h-6"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-lg font-bold text-zinc-200">
                      Your Portfolio is Empty
                    </h3>
                    <p className="text-sm text-zinc-400 max-w-sm mx-auto">
                      Log your stock purchases to track average cost basis, allocations, and live valuation details.
                    </p>
                  </div>
                  <button
                    onClick={() => setIsDialogOpen(true)}
                    className="px-5 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-505 transition-all cursor-pointer border border-indigo-500/25 active:scale-95"
                  >
                    Record Your First Trade
                  </button>
                </div>
              ) : (
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="bg-zinc-950/60 border-b border-zinc-800 text-[11px] font-bold uppercase tracking-wider text-zinc-400">
                      <th className="px-8 py-4">Stock Asset</th>
                      <th className="px-6 py-4 text-right">Shares</th>
                      <th className="px-6 py-4 text-right">Avg Cost</th>
                      <th className="px-6 py-4 text-right">Live Price</th>
                      <th className="px-6 py-4 text-right">Market Value</th>
                      <th className="px-6 py-4 text-right">Returns (P&L)</th>
                      <th className="px-8 py-4 text-right w-44">Allocation Weight</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {holdings.map((h) => {
                      const hGain = h.unrealized_pnl >= 0;
                      return (
                        <tr key={h.symbol} className="hover:bg-zinc-800/20 transition-colors">
                          <td className="px-8 py-4.5">
                            <div className="flex flex-col">
                              <span className="font-bold text-zinc-100 font-mono">
                                {h.symbol}
                              </span>
                              <span className="text-xs text-zinc-400 mt-0.5 truncate max-w-xs">
                                {h.company_name}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4.5 text-right font-semibold font-mono text-zinc-200">
                            {h.quantity}
                          </td>
                          <td className="px-6 py-4.5 text-right font-mono text-zinc-400">
                            ₹{h.average_buy_price.toFixed(2)}
                          </td>
                          <td className="px-6 py-4.5 text-right font-mono text-zinc-400">
                            ₹{h.market_price.toFixed(2)}
                          </td>
                          <td className="px-6 py-4.5 text-right font-bold font-mono text-zinc-100">
                            ₹{h.market_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-6 py-4.5 text-right">
                            <div className="flex flex-col items-end">
                              <span className={`font-bold font-mono ${hGain ? "text-emerald-400" : "text-rose-400"}`}>
                                {hGain ? "+" : ""}₹{h.unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </span>
                              <span className={`text-xs font-semibold mt-0.5 ${hGain ? "text-emerald-500" : "text-rose-500"}`}>
                                {hGain ? "+" : ""}{h.unrealized_pnl_percent.toFixed(2)}%
                              </span>
                            </div>
                          </td>
                          <td className="px-8 py-4.5 text-right">
                            <div className="flex flex-col items-end gap-1.5">
                              <span className="font-bold font-mono text-zinc-200">
                                {h.allocation_percent.toFixed(1)}%
                              </span>
                              <div className="w-full bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                                <div
                                  className="bg-indigo-500 h-full rounded-full"
                                  style={{ width: `${h.allocation_percent}%` }}
                                />
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Tab 2: Trade History */}
          {activeTab === "history" && (
            <div className="overflow-x-auto">
              {transactions.length === 0 ? (
                <div className="text-center p-16 text-zinc-400">
                  No recorded transaction history found.
                </div>
              ) : (
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="bg-zinc-955/60 border-b border-zinc-800 text-[11px] font-bold uppercase tracking-wider text-zinc-400">
                      <th className="px-8 py-4">Execution Date</th>
                      <th className="px-6 py-4">Asset symbol</th>
                      <th className="px-6 py-4">Action</th>
                      <th className="px-6 py-4 text-right">Shares</th>
                      <th className="px-6 py-4 text-right">Share Price</th>
                      <th className="px-6 py-4 text-right">Fees</th>
                      <th className="px-6 py-4 text-right">Total Trade Cost</th>
                      <th className="px-8 py-4 text-center">Manage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {transactions.map((tx) => {
                      const isBuy = tx.transaction_type === "BUY";
                      const totalCost = (tx.quantity * tx.price) + (isBuy ? tx.fees || 0 : -(tx.fees || 0));
                      return (
                        <tr key={tx.id} className="hover:bg-zinc-800/20 transition-colors">
                          <td className="px-8 py-4 text-xs font-mono text-zinc-400">
                            {new Date(tx.executed_at).toLocaleString()}
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex flex-col">
                              <span className="font-bold text-zinc-100 font-mono">
                                {tx.symbol}
                              </span>
                              <span className="text-xs text-zinc-400 truncate max-w-xs">
                                {tx.company_name}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                                isBuy
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                  : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                              }`}
                            >
                              {tx.transaction_type}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right font-semibold font-mono text-zinc-200">
                            {tx.quantity}
                          </td>
                          <td className="px-6 py-4 text-right font-mono text-zinc-400">
                            ₹{tx.price.toFixed(2)}
                          </td>
                          <td className="px-6 py-4 text-right font-mono text-zinc-450">
                            ₹{tx.fees?.toFixed(2) || "0.00"}
                          </td>
                          <td className="px-6 py-4 text-right font-bold font-mono text-zinc-100">
                            ₹{totalCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-8 py-4 text-center">
                            <button
                              onClick={() => handleDeleteTransaction(tx.id)}
                              className="p-1.5 text-zinc-450 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-all cursor-pointer border border-transparent active:scale-95"
                              title="Delete transaction log"
                            >
                              <svg
                                className="w-4.5 h-4.5"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                                />
                              </svg>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}

      {mainTab === "analytics" && (
        <div className="space-y-6">
          {holdings.length === 0 ? (
            <div className="bg-white border border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800 rounded-3xl p-12 text-center max-w-lg mx-auto space-y-4 shadow-sm">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto animate-bounce">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div className="space-y-1">
                <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">Analytics Not Available Yet</h3>
                <p className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
                  Log active holdings inside the Ledger tab to calculate exposure distributions and render performance history trends.
                </p>
              </div>
              <button
                onClick={() => setMainTab("ledger")}
                className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold shadow-sm cursor-pointer transition-colors"
              >
                Go to Ledger
              </button>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Performance Area Chart Card */}
              <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 shadow-xl shadow-black/10 backdrop-blur-md">
                <PerformanceChart history={history} />
              </div>

              {/* Exposure details grid */}
              <div className="grid gap-6 md:grid-cols-2">
                {/* Sector exposure chart card */}
                <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 shadow-xl shadow-black/10 backdrop-blur-md">
                  <AllocationChart sectors={exposures?.sectors || []} />
                </div>

                {/* Market Cap exposure list */}
                <div className="p-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 shadow-xl shadow-black/10 backdrop-blur-md space-y-4 flex flex-col justify-between">
                  <div className="space-y-1">
                    <h3 className="text-lg font-bold text-zinc-150">Market Capitalization Allocation</h3>
                  </div>
                  
                  <div className="space-y-5 my-auto">
                    {exposures?.market_caps.map((cap) => {
                      const getCapColor = (bucket: string) => {
                        if (bucket === "LARGE") return "bg-blue-700"; 
                        if (bucket === "MID") return "bg-blue-500";  
                        if (bucket === "ETFs & Others") return "bg-blue-200"; 
                        return "bg-blue-400"; 
                      };
                      
                      const getCapLabel = (bucket: string) => {
                        if (bucket === "LARGE") return "Large-Cap Holdings";
                        if (bucket === "MID") return "Mid-Cap Holdings";
                        if (bucket === "ETFs & Others") return "ETFs & Others";
                        return "Small-Cap Holdings";
                      };

                      const getCapLimitMsg = (bucket: string) => {
                        if (bucket === "LARGE") return "High Stability / Bluechip";
                        if (bucket === "MID") return "Growth Core / Medium Risk";
                        if (bucket === "ETFs & Others") return "Commodity, Index Funds, ETFs";
                        return "High Volatility / Small Venture";
                      };
                      
                      return (
                        <div key={cap.bucket} className="space-y-1.5">
                          <div className="flex justify-between items-baseline text-xs">
                            <span className="text-zinc-300 flex items-center gap-2 font-semibold">
                              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${getCapColor(cap.bucket)}`} />
                              {getCapLabel(cap.bucket)}
                            </span>
                            <span className="font-mono font-bold text-zinc-200">
                              ₹{cap.value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ({cap.percentage.toFixed(1)}%)
                            </span>
                          </div>
                          <div className="w-full bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-1000 ${getCapColor(cap.bucket)}`}
                              style={{ width: `${cap.percentage}%` }}
                            />
                          </div>
                          <p className="text-[10px] text-zinc-500 pl-4.5 font-medium">{getCapLimitMsg(cap.bucket)}</p>
                        </div>
                      );
                    })}
                  </div>

                </div>
              </div>

              {/* AI Review Shifted Below Charts */}
              <div className="pt-8 border-t border-zinc-800 space-y-6 text-left">
                

                {/* Strategic Portfolio Strategist Cockpit */}
                <div className="flex flex-col sm:flex-row justify-between sm:items-center p-6 border border-zinc-800 bg-zinc-900/40 rounded-xl gap-4 shadow-lg shadow-black/10">
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
                      AI Portfolio Strategist Cockpit
                    </h4>
                    <p className="text-[10px] text-zinc-400 font-mono">
                      {review
                        ? `Latest compilation: ${new Date(review.created_at).toLocaleString()}`
                        : "Ready to trigger AI review"}
                    </p>
                  </div>

                  <button
                    onClick={handleGenerateReview}
                    disabled={generatingReview}
                    className={`px-5 py-3 rounded-xl text-xs font-bold uppercase tracking-wider shadow-md flex items-center gap-2 cursor-pointer transition-all duration-300 border active:scale-95 ${
                      generatingReview
                        ? "bg-zinc-800 text-zinc-500 border-zinc-700/50"
                        : "bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-500/20 shadow-indigo-600/10 hover:scale-105"
                    }`}
                  >
                    {generatingReview && (
                      <svg className="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    )}
                    {generatingReview ? "Generating Insights It could take 1-2 min..." : "Request AI Review"}
                  </button>
                </div>

                {/* Skeletons/Errors State */}
                {generatingReview ? (
                  <div className="space-y-6">
                    <div className="h-44 rounded-xl bg-zinc-900 animate-pulse border border-zinc-850" />
                    <div className="h-44 rounded-xl bg-zinc-900 animate-pulse border border-zinc-850" />
                    <div className="h-44 rounded-xl bg-zinc-900 animate-pulse border border-zinc-850" />
                  </div>
                ) : reviewError ? (
                  <div className="p-6 border border-rose-500/20 bg-rose-500/5 rounded-xl text-center text-xs font-medium text-rose-400 flex flex-col items-center gap-3">
                    <span>{reviewError}</span>
                    {(reviewError.toLowerCase().includes("token limit") || reviewError.toLowerCase().includes("guest")) && (
                      <button
                        type="button"
                        onClick={() => loginWithGoogle()}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-505 text-white text-xs font-bold transition-all duration-150 cursor-pointer active:scale-95 shadow-md border border-indigo-505/20 mx-auto"
                      >
                        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                        </svg>
                        <span>Sign Up with Google</span>
                      </button>
                    )}
                  </div>
                ) : review ? (
                  <div className="space-y-8 animate-fade-in text-left">
                    {/* Card 1: AI Portfolio Strategic Analysis */}
                    {(() => {
                      let stats = { current_value: "N/A", total_pnl: "N/A", total_pnl_percent: "N/A" };
                      try {
                        if (review.diversification_summary) {
                          stats = JSON.parse(review.diversification_summary);
                        }
                      } catch (e) {
                        console.error("Failed to parse summary stats:", e);
                      }

                      const isPnlGain = !stats.total_pnl.includes("-");

                      return (
                        <div className="p-6 sm:p-8 border border-zinc-800 bg-zinc-900/50 rounded-xl shadow-xl shadow-black/10 space-y-6">
                          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-4">
                            <div className="space-y-1">
                              <h3 className="text-base sm:text-lg font-bold text-zinc-100 flex items-center gap-2">
                                <span className="w-1 h-4 bg-indigo-500 rounded-full shrink-0"></span>
                                AI Portfolio Strategic Analysis
                              </h3>
                              <p className="text-xs text-zinc-400 font-medium">
                                Executive summary, key findings, and portfolio-wide allocation signals.
                              </p>
                            </div>
                            
                            {/* Summary Stats Banner */}
                            <div className="flex flex-wrap items-center gap-3 bg-zinc-950 p-2.5 rounded-xl border border-zinc-800">
                              <div className="text-xs px-1">
                                <span className="text-[9px] text-zinc-400 block uppercase tracking-wider font-semibold">Value</span>
                                <span className="font-mono font-bold text-zinc-200">{stats.current_value}</span>
                              </div>
                              <div className="w-px h-6 bg-zinc-800" />
                              <div className="text-xs px-1">
                                <span className="text-[9px] text-zinc-400 block uppercase tracking-wider font-semibold"> P&L</span>
                                <span className={`font-mono font-bold ${isPnlGain ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  {stats.total_pnl} ({stats.total_pnl_percent})
                                </span>
                              </div>
                            </div>
                          </div>

                          <div className="border-l-2 border-indigo-500 pl-4 py-2 bg-indigo-500/5 rounded-r-xl">
                            <div className="prose prose-sm dark:prose-invert prose-headings:text-zinc-100 prose-p:text-zinc-350 prose-strong:text-indigo-400 prose-a:text-indigo-400 max-w-none font-medium leading-relaxed">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {review.risk_summary}
                              </ReactMarkdown>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* Card 2: Holdings & Allocation Recommendations */}
                    {review.potential_stock_picks && review.potential_stock_picks.length > 0 && (
                      <div className="p-6 sm:p-8 border border-zinc-800 bg-zinc-900/50 rounded-xl shadow-xl shadow-black/10 space-y-6">
                        <div className="space-y-1 border-b border-zinc-800 pb-4">
                          <h3 className="text-base sm:text-lg font-bold text-zinc-100 flex items-center gap-2">
                            <span className="w-1 h-4 bg-indigo-500 rounded-full shrink-0"></span>
                            Holdings & Allocation Recommendations
                          </h3>
                          <p className="text-xs text-zinc-400 font-medium">
                            AI recommendations and reasoning.
                          </p>
                        </div>

                        <div className="overflow-x-auto border border-zinc-800 rounded-xl bg-zinc-950/20">
                          <table className="w-full text-left text-xs border-collapse">
                            <thead>
                              <tr className="bg-zinc-955/60 border-b border-zinc-800 text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                                <th className="px-6 py-4.5">Asset</th>
                                <th className="px-6 py-4.5 text-right">Shares</th>
                                <th className="px-6 py-4.5 text-right">Avg Price</th>
                                <th className="px-6 py-4.5 text-right">Live Price</th>
                                <th className="px-6 py-4.5 text-right">Weight</th>
                                <th className="px-6 py-4.5 text-right">P&L</th>
                                <th className="px-6 py-4.5 text-center">Action (confidence)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-800/60">
                              {review.potential_stock_picks.map((pick: any, idx: number) => {
                                const getRecommendationBadge = (rec: string) => {
                                  if (rec === "BUY") return "bg-emerald-400/10 text-emerald-400 border-emerald-200/20";
                                  if (rec === "SELL") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
                                  if (rec === "AVOID") return "bg-zinc-800 text-zinc-400 border-zinc-700";
                                  return "bg-indigo-500/10 text-indigo-400 border-indigo-500/20";
                                };
                                return (
                                  <tr key={idx} className="hover:bg-zinc-800/20 transition-colors">
                                    <td className="px-6 py-4">
                                      <div className="flex flex-col">
                                        <span className="font-bold text-zinc-100 font-mono">{pick.symbol}</span>
                                        <span className="text-[10px] text-zinc-400 font-semibold truncate max-w-[150px]">{pick.company_name}</span>
                                      </div>
                                    </td>
                                    <td className="px-6 py-4 text-right font-mono font-bold text-zinc-200">{pick.quantity}</td>
                                    <td className="px-6 py-4 text-right font-mono text-zinc-400">{pick.avg_price}</td>
                                    <td className="px-6 py-4 text-right font-mono text-zinc-400">{pick.market_price}</td>
                                    <td className="px-6 py-4 text-right font-mono text-zinc-400">{pick.allocation}</td>
                                    <td className={`px-6 py-4 text-right font-mono font-bold ${!pick.pnl.includes("-") ? 'text-emerald-400' : 'text-rose-400'}`}>{pick.pnl}</td>
                                    <td className="px-6 py-4 text-center">
                                      <span className={`inline-flex px-2.5 py-0.5 rounded border text-[9px] font-bold uppercase tracking-wider ${getRecommendationBadge(pick.recommendation)}`}>
                                        {pick.recommendation} ({pick.confidence})
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>

                        {/* Rationale & Recent Developments block inside the same card below holdings table */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                          {review.potential_stock_picks.map((pick: any, idx: number) => (
                            <div key={idx} className="p-5 border border-zinc-800 bg-zinc-900/30 rounded-xl text-left space-y-3">
                              <div className="flex justify-between items-center border-b border-zinc-800/85 pb-2">
                                <span className="font-bold text-xs text-zinc-150">{pick.company_name} ({pick.symbol})</span>
                                <span className="text-[9px] font-bold text-indigo-400 uppercase tracking-wider">Analysis Reasoning</span>
                              </div>
                              <p className="text-xs text-zinc-300 leading-relaxed font-normal">
                                <strong className="text-zinc-200">Rationale:</strong> {pick.rationale}
                              </p>
                              {pick.recent_developments && (
                                <p className="text-xs text-zinc-400 leading-relaxed font-normal">
                                  <strong className="text-zinc-305">Developments:</strong> {pick.recent_developments}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Card 3: Rebalanc                    {review.rebalancing_ideas && review.rebalancing_ideas.length > 0 && (
                      <div className="p-6 sm:p-8 border border-zinc-800 bg-zinc-900/50 rounded-xl shadow-xl shadow-black/10 space-y-6">
                        <div className="space-y-1 border-b border-zinc-800 pb-4">
                          <h3 className="text-base sm:text-lg font-bold text-zinc-100 flex items-center gap-2">
                            <span className="w-1 h-4 bg-indigo-500 rounded-full shrink-0"></span>
                            Rebalancing & Optimization Plan
                          </h3>
                          <p className="text-xs text-zinc-400 font-medium">
                            Concrete strategic adjustments to capture alpha, manage drawdown, and improve asset weights.
                          </p>
                        </div>

                        <div className="space-y-3.5">
                          {review.rebalancing_ideas.map((idea: any, idx: number) => {
                            if (idea.action === "OBJECTIVE") {
                              return (
                                <div key={idx} className="p-4 bg-indigo-950/20 border border-indigo-500/20 rounded-xl text-xs font-medium text-indigo-305 leading-relaxed flex items-start gap-3">
                                  <svg className="w-5 h-5 text-indigo-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                  <span>{idea.details}</span>
                                </div>
                              );
                            }

                            const getActionBadge = (act: string) => {
                              if (act === "SIP") return "bg-teal-500/10 text-teal-400 border border-teal-500/20";
                              if (act === "SELL" || act === "TRIM") return "bg-rose-500/10 text-rose-400 border border-rose-500/20";
                              return "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
                            };

                            return (
                              <div key={idx} className="p-4.5 border border-zinc-800 bg-zinc-900/30 rounded-xl flex items-start gap-4 text-left hover:bg-zinc-900/50 transition-colors">
                                <div className="space-y-2 flex-1">
                                  <div className="flex items-center gap-2">
                                    <span className={`inline-flex px-2 py-0.5 rounded text-[9px] font-bold border uppercase tracking-wider ${getActionBadge(idea.action)}`}>
                                      {idea.action}
                                    </span>
                                    {idea.symbol && (
                                      <span className="text-xs font-bold text-zinc-100 font-mono">
                                        {idea.symbol}
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-xs text-zinc-300 leading-relaxed font-normal">
                                    {idea.details}
                                  </p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Card 4: Expected Future Scenarios & Catalyst Analysis (Portfolio-Level) */}
                    {(() => {
                      let futureScenarios: any = {};
                      try {
                        if (review.market_impact) {
                          futureScenarios = JSON.parse(review.market_impact);
                        }
                      } catch (e) {
                        console.error("Failed to parse future scenarios:", e);
                      }

                      if (!futureScenarios.bull_case && !futureScenarios.base_case && !futureScenarios.bear_case) return null;

                      return (
                        <div className="p-6 sm:p-8 border border-zinc-800 bg-zinc-900/50 rounded-xl shadow-xl shadow-black/10 space-y-6">
                          <div className="space-y-1 border-b border-zinc-800 pb-4">
                            <h3 className="text-base sm:text-lg font-bold text-zinc-100 flex items-center gap-2">
                              <span className="w-1 h-4 bg-indigo-500 rounded-full shrink-0"></span>
                              Expected Future Scenarios & Catalyst Analysis
                            </h3>
                            <p className="text-xs text-zinc-400 font-medium">
                              Portfolio-level scenario projections covering Bull, Base, and Bear cases.
                            </p>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {/* Bull Case */}
                            <div className="space-y-3 bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-5 flex flex-col">
                              <div className="flex items-center gap-2 border-b border-emerald-500/15 pb-3">
                                <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                  </svg>
                                  Bull Case
                                </span>
                              </div>
                              <div className="prose prose-sm dark:prose-invert prose-p:text-zinc-300 prose-p:leading-relaxed prose-p:font-normal max-w-none text-xs">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                  {futureScenarios.bull_case}
                                </ReactMarkdown>
                              </div>
                            </div>

                            {/* Base Case */}
                            <div className="space-y-3 bg-zinc-900/40 border border-zinc-800 rounded-xl p-5 flex flex-col">
                              <div className="flex items-center gap-2 border-b border-zinc-700/50 pb-3">
                                <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                                  </svg>
                                  Base Case
                                </span>
                              </div>
                              <div className="prose prose-sm dark:prose-invert prose-p:text-zinc-300 prose-p:leading-relaxed prose-p:font-normal max-w-none text-xs">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                  {futureScenarios.base_case}
                                </ReactMarkdown>
                              </div>
                            </div>

                            {/* Bear Case */}
                            <div className="space-y-3 bg-rose-500/5 border border-rose-500/10 rounded-xl p-5 flex flex-col">
                              <div className="flex items-center gap-2 border-b border-rose-500/15 pb-3">
                                <span className="text-[11px] font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 17h8m0 0v-8m0 8l-8-8-4 4-6-6" />
                                  </svg>
                                  Bear Case
                                </span>
                              </div>
                              <div className="prose prose-sm dark:prose-invert prose-p:text-zinc-300 prose-p:leading-relaxed prose-p:font-normal max-w-none text-xs">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                  {futureScenarios.bear_case}
                                </ReactMarkdown>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* Card 5: News Updates */}
                    {review.evidence?.news_updates && review.evidence.news_updates.length > 0 && (
                      <div className="p-6 sm:p-8 border border-zinc-800 bg-zinc-900/50 rounded-xl shadow-xl shadow-black/10 space-y-6">
                        <div className="space-y-1 border-b border-zinc-800 pb-4">
                          <h3 className="text-base sm:text-lg font-bold text-zinc-100 flex items-center gap-2">
                            <span className="w-1 h-4 bg-indigo-500 rounded-full shrink-0"></span>
                            News Updates & Sentiment Analysis
                          </h3>
                          <p className="text-xs text-zinc-400 font-medium">
                            Real-time corporate news signals, earnings filings, and regulatory updates affecting your assets.
                          </p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                          {review.evidence.news_updates.map((news: any, idx: number) => (
                            <div key={idx} className="p-5 border border-zinc-800 bg-zinc-900/30 rounded-xl text-left space-y-3.5">
                              <h4 className="font-bold text-xs text-zinc-100 border-b border-zinc-800/80 pb-2 flex justify-between items-center">
                                <span>{news.company_name}</span>
                                <span className="text-[10px] text-zinc-400 font-mono uppercase tracking-wider">{news.symbol}</span>
                              </h4>
                              <ul className="space-y-2.5 list-none pl-0 text-xs leading-relaxed font-normal">
                                {news.bullets.map((b: string, bIdx: number) => (
                                  <li key={bIdx} className="relative pl-4 text-zinc-300">
                                    <span className="absolute left-0 top-2 w-1.5 h-1.5 bg-indigo-500 rounded-full shrink-0"></span>
                                    {b}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Footer: Regulatory Disclaimer */}
                    {review.disclaimers && (
                      <div className="p-4 bg-zinc-900/30 border border-zinc-800 rounded-xl text-[10px] text-zinc-400 leading-relaxed font-medium text-left flex gap-2.5 items-start">
                        <svg className="w-4 h-4 text-zinc-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m0-6h.01M12 2a10 10 0 110 20 10 10 0 010-20z" />
                        </svg>
                        <span><strong>Regulatory Disclaimer:</strong> {review.disclaimers}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center p-12 bg-zinc-900/40 border border-zinc-800 rounded-xl text-zinc-400 shadow-lg shadow-black/10">
                    Click the Request AI Review button to trigger the strategic portfolio compiler.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal Dialogue */}
      <AddTransactionDialog
        isOpen={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        onSuccess={loadPortfolioData}
      />

      {/* Bulk Upload Modal */}
      <UploadTradesDialog
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onSuccess={loadPortfolioData}
      />
    </div>
  );
}
