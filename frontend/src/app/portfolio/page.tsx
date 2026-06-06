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
import PerformanceChart from "@/components/portfolio/performance-chart";
import AllocationChart from "@/components/portfolio/allocation-chart";

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
  const [mainTab, setMainTab] = useState<"ledger" | "analytics" | "ai-review">("ledger");
  const [activeTab, setActiveTab] = useState<"holdings" | "history">("holdings");
  const [isDialogOpen, setIsDialogOpen] = useState(false);

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
    <div className="space-y-8 animate-fade-in">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
            {mainTab === "ledger" 
              ? "Portfolio Ledger" 
              : mainTab === "analytics" 
              ? "Portfolio Analytics" 
              : "AI Portfolio Review"}
          </h1>
          <p className="text-xs sm:text-sm text-zinc-500 dark:text-zinc-400 font-medium">
            {mainTab === "ledger"
              ? "Track assets, calculate average cost basis, and monitor gains."
              : mainTab === "analytics"
              ? "Performance tracking, asset weight distributions, and market cap exposure."
              : "AI powered asset concentration risk reviews, sector diversification guides, and warnings."}
          </p>
        </div>
        
        <div className="flex flex-wrap items-center gap-2.5 sm:gap-3 shrink-0">
          <button
            onClick={() => setIsDialogOpen(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs sm:text-sm font-semibold shadow-md shadow-indigo-600/10 flex items-center gap-1.5 transition-all shrink-0 cursor-pointer"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M12 4v16m8-8H4"
              />
            </svg>
            Log Trade
          </button>
        </div>
      </div>

      {/* Metrics Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        <div className="p-5 sm:p-6 rounded-2xl bg-white border border-zinc-200 shadow-sm dark:bg-zinc-900 dark:border-zinc-800 space-y-1">
          <p className="text-[10px] sm:text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Portfolio Value
          </p>
          <p className="text-xl sm:text-2xl font-bold text-zinc-900 dark:text-zinc-50">
            ₹{summary.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className="text-[10px] sm:text-xs text-zinc-400">Current market worth</p>
        </div>

        <div className="p-5 sm:p-6 rounded-2xl bg-white border border-zinc-200 shadow-sm dark:bg-zinc-900 dark:border-zinc-800 space-y-1">
          <p className="text-[10px] sm:text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Total Cost Basis
          </p>
          <p className="text-xl sm:text-2xl font-bold text-zinc-900 dark:text-zinc-50">
            ₹{summary.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className="text-[10px] sm:text-xs text-zinc-400">Total invested capital</p>
        </div>

        <div className="p-5 sm:p-6 rounded-2xl bg-white border border-zinc-200 shadow-sm dark:bg-zinc-900 dark:border-zinc-800 space-y-1">
          <p className="text-[10px] sm:text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Unrealized Returns
          </p>
          <div className="flex items-baseline gap-2">
            <span
              className={`text-xl sm:text-2xl font-bold ${
                isGain ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
              }`}
            >
              ₹{summary.total_unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <span
            className={`inline-flex items-center gap-1 text-[10px] sm:text-xs font-semibold px-2 py-0.5 rounded-full ${
              isGain
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400"
                : "bg-rose-50 text-rose-700 dark:bg-rose-950/20 dark:text-rose-400"
            }`}
          >
            {isGain ? "+" : ""}
            {summary.total_unrealized_pnl_percent.toFixed(2)}%
          </span>
        </div>

        <div className="p-5 sm:p-6 rounded-2xl bg-white border border-zinc-200 shadow-sm dark:bg-zinc-900 dark:border-zinc-800 space-y-1">
          <p className="text-[10px] sm:text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Realized Profits
          </p>
          <p
            className={`text-xl sm:text-2xl font-bold ${
              summary.total_realized_pnl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
            }`}
          >
            ₹{summary.total_realized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className="text-[10px] sm:text-xs text-zinc-400">Profits locked from sales</p>
        </div>
      </div>

      {/* Modern Horizontal Navigation Tabs */}
      <div className="flex overflow-x-auto whitespace-nowrap scrollbar-none border-b border-zinc-200 dark:border-zinc-800/80 gap-1 bg-zinc-50/20 dark:bg-zinc-900/10 p-1.5 rounded-2xl">
        <button
          onClick={() => setMainTab("ledger")}
          className={`py-2 px-4 sm:py-2.5 sm:px-6 text-xs sm:text-sm font-semibold rounded-xl transition-all cursor-pointer ${
            mainTab === "ledger"
              ? "bg-white text-indigo-600 shadow-sm dark:bg-zinc-850 dark:text-indigo-400 font-extrabold"
              : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
          }`}
        >
          Ledger List
        </button>
        <button
          onClick={() => setMainTab("analytics")}
          className={`py-2 px-4 sm:py-2.5 sm:px-6 text-xs sm:text-sm font-semibold rounded-xl transition-all cursor-pointer ${
            mainTab === "analytics"
              ? "bg-white text-indigo-600 shadow-sm dark:bg-zinc-850 dark:text-indigo-400 font-extrabold"
              : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
          }`}
        >
          Analytics Charts
        </button>
        <button
          onClick={() => setMainTab("ai-review")}
          className={`py-2 px-4 sm:py-2.5 sm:px-6 text-xs sm:text-sm font-semibold rounded-xl transition-all cursor-pointer ${
            mainTab === "ai-review"
              ? "bg-white text-indigo-600 shadow-sm dark:bg-zinc-850 dark:text-indigo-400 font-extrabold"
              : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
          }`}
        >
          AI Review
        </button>
      </div>

      {/* Main Container based on active tab */}
      {mainTab === "ledger" && (
        <div className="bg-white border border-zinc-200 rounded-3xl overflow-hidden shadow-sm dark:bg-zinc-900 dark:border-zinc-800">
          <div className="px-8 border-b border-zinc-200 dark:border-zinc-800 flex justify-between items-center bg-zinc-50/50 dark:bg-zinc-900/50">
            <div className="flex gap-6">
              <button
                onClick={() => setActiveTab("holdings")}
                className={`py-4 text-sm font-semibold border-b-2 transition-colors focus:outline-none cursor-pointer ${
                  activeTab === "holdings"
                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                    : "border-transparent text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
                }`}
              >
                Active Holdings
              </button>
              <button
                onClick={() => setActiveTab("history")}
                className={`py-4 text-sm font-semibold border-b-2 transition-colors focus:outline-none cursor-pointer ${
                  activeTab === "history"
                    ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                    : "border-transparent text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
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
                  <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto">
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
                    <h3 className="text-lg font-bold text-zinc-800 dark:text-zinc-200">
                      Your Portfolio is Empty
                    </h3>
                    <p className="text-sm text-zinc-500 dark:text-zinc-400 max-w-sm mx-auto">
                      Log your stock purchases to track average cost basis, allocations, and live valuation details.
                    </p>
                  </div>
                  <button
                    onClick={() => setIsDialogOpen(true)}
                    className="px-5 py-2 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors cursor-pointer"
                  >
                    Record Your First Trade
                  </button>
                </div>
              ) : (
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="bg-zinc-50/50 border-b border-zinc-200 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900/50 dark:border-zinc-800 dark:text-zinc-400">
                      <th className="px-8 py-4">Stock Asset</th>
                      <th className="px-6 py-4 text-right">Shares</th>
                      <th className="px-6 py-4 text-right">Avg Cost</th>
                      <th className="px-6 py-4 text-right">Live Price</th>
                      <th className="px-6 py-4 text-right">Market Value</th>
                      <th className="px-6 py-4 text-right">Returns (P&L)</th>
                      <th className="px-8 py-4 text-right w-44">Allocation Weight</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                    {holdings.map((h) => {
                      const hGain = h.unrealized_pnl >= 0;
                      return (
                        <tr key={h.symbol} className="hover:bg-zinc-50/30 dark:hover:bg-zinc-800/20 transition-colors">
                          <td className="px-8 py-4.5">
                            <div className="flex flex-col">
                              <span className="font-bold text-zinc-900 dark:text-zinc-50 font-mono">
                                {h.symbol}
                              </span>
                              <span className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate max-w-xs">
                                {h.company_name}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4.5 text-right font-semibold font-mono text-zinc-800 dark:text-zinc-200">
                            {h.quantity}
                          </td>
                          <td className="px-6 py-4.5 text-right font-mono text-zinc-600 dark:text-zinc-400">
                            ₹{h.average_buy_price.toFixed(2)}
                          </td>
                          <td className="px-6 py-4.5 text-right font-mono text-zinc-600 dark:text-zinc-400">
                            ₹{h.market_price.toFixed(2)}
                          </td>
                          <td className="px-6 py-4.5 text-right font-bold font-mono text-zinc-900 dark:text-zinc-50">
                            ₹{h.market_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-6 py-4.5 text-right">
                            <div className="flex flex-col items-end">
                              <span className={`font-bold font-mono ${hGain ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                                {hGain ? "+" : ""}₹{h.unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </span>
                              <span className={`text-xs font-semibold mt-0.5 ${hGain ? "text-emerald-500" : "text-rose-500"}`}>
                                {hGain ? "+" : ""}{h.unrealized_pnl_percent.toFixed(2)}%
                              </span>
                            </div>
                          </td>
                          <td className="px-8 py-4.5 text-right">
                            <div className="flex flex-col items-end gap-1.5">
                              <span className="font-bold font-mono text-zinc-800 dark:text-zinc-200">
                                {h.allocation_percent.toFixed(1)}%
                              </span>
                              <div className="w-full bg-zinc-100 dark:bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                                <div
                                  className="bg-indigo-600 dark:bg-indigo-500 h-full rounded-full"
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
                <div className="text-center p-16 text-zinc-500 dark:text-zinc-400">
                  No recorded transaction history found.
                </div>
              ) : (
                <table className="w-full text-left text-sm border-collapse">
                  <thead>
                    <tr className="bg-zinc-50/50 border-b border-zinc-200 text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900/50 dark:border-zinc-800 dark:text-zinc-400">
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
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                    {transactions.map((tx) => {
                      const isBuy = tx.transaction_type === "BUY";
                      const totalCost = (tx.quantity * tx.price) + (isBuy ? tx.fees || 0 : -(tx.fees || 0));
                      return (
                        <tr key={tx.id} className="hover:bg-zinc-50/30 dark:hover:bg-zinc-800/20 transition-colors">
                          <td className="px-8 py-4 font-medium text-zinc-500 dark:text-zinc-400">
                            {new Date(tx.executed_at).toLocaleString()}
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex flex-col">
                              <span className="font-bold text-zinc-850 dark:text-zinc-100 font-mono">
                                {tx.symbol}
                              </span>
                              <span className="text-xs text-zinc-400 truncate max-w-xs">
                                {tx.company_name}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                                isBuy
                                  ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/20 dark:text-emerald-400"
                                  : "bg-rose-50 text-rose-800 dark:bg-rose-950/20 dark:text-rose-400"
                              }`}
                            >
                              {tx.transaction_type}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right font-semibold font-mono text-zinc-800 dark:text-zinc-200">
                            {tx.quantity}
                          </td>
                          <td className="px-6 py-4 text-right font-mono text-zinc-600 dark:text-zinc-400">
                            ₹{tx.price.toFixed(2)}
                          </td>
                          <td className="px-6 py-4 text-right font-mono text-zinc-500">
                            ₹{tx.fees?.toFixed(2) || "0.00"}
                          </td>
                          <td className="px-6 py-4 text-right font-bold font-mono text-zinc-900 dark:text-zinc-50">
                            ₹{totalCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className="px-8 py-4 text-center">
                            <button
                              onClick={() => handleDeleteTransaction(tx.id)}
                              className="p-1.5 text-zinc-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/20 rounded-lg transition-all cursor-pointer"
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
              <div className="p-6 rounded-3xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm">
                <PerformanceChart history={history} />
              </div>

              {/* Exposure details grid */}
              <div className="grid gap-6 md:grid-cols-2">
                {/* Sector exposure chart card */}
                <div className="p-6 rounded-3xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm">
                  <AllocationChart sectors={exposures?.sectors || []} />
                </div>

                {/* Market Cap exposure list */}
                <div className="p-6 rounded-3xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm space-y-4 flex flex-col justify-between">
                  <div className="space-y-1">
                    <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">Market Capitalization Allocation</h3>
                    <p className="text-xs text-zinc-400">Exposure bucket sizes using local asset currencies</p>
                  </div>
                  
                  <div className="space-y-5 my-auto">
                    {exposures?.market_caps.map((cap) => {
                      const getCapColor = (bucket: string) => {
                        if (bucket === "LARGE") return "bg-indigo-600 dark:bg-indigo-500";
                        if (bucket === "MID") return "bg-cyan-500 dark:bg-cyan-400";
                        return "bg-pink-500 dark:bg-pink-400";
                      };
                      
                      const getCapLabel = (bucket: string) => {
                        if (bucket === "LARGE") return "Large-Cap Holdings";
                        if (bucket === "MID") return "Mid-Cap Holdings";
                        return "Small-Cap Holdings";
                      };

                      const getCapLimitMsg = (bucket: string) => {
                        if (bucket === "LARGE") return "High Stability / Bluechip";
                        if (bucket === "MID") return "Growth Core / Medium Risk";
                        return "High Volatility / Small Venture";
                      };
                      
                      return (
                        <div key={cap.bucket} className="space-y-1.5">
                          <div className="flex justify-between items-baseline text-xs font-bold">
                            <span className="text-zinc-800 dark:text-zinc-250 flex items-center gap-2">
                              <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${getCapColor(cap.bucket)}`} />
                              {getCapLabel(cap.bucket)}
                            </span>
                            <span className="font-mono text-zinc-500 dark:text-zinc-450">
                              ₹{cap.value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ({cap.percentage.toFixed(1)}%)
                            </span>
                          </div>
                          <div className="w-full bg-zinc-100 dark:bg-zinc-800 h-2 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-1000 ${getCapColor(cap.bucket)}`}
                              style={{ width: `${cap.percentage}%` }}
                            />
                          </div>
                          <p className="text-[10px] text-zinc-400/80 pl-4">{getCapLimitMsg(cap.bucket)}</p>
                        </div>
                      );
                    })}
                  </div>

                  <div className="pt-4 border-t border-zinc-100 dark:border-zinc-800/80 text-[11px] text-zinc-400/90 leading-relaxed pl-1">
                    Buckets are automatically classified using SEBI Guidelines (Large-Cap &gt; ₹20k Cr, Mid-cap &gt; ₹5k Cr) for NS/BO symbols, and global indexes ($20B, $5B) for USD assets.
                  </div>
                </div>
              </div>
            </div>
              )}
            </div>
          )}

          {mainTab === "ai-review" && (
        <div className="space-y-8 text-left">
          {/* SEBI Disclaimer Header */}
          <div className="p-4 bg-amber-50/50 border border-amber-200 dark:bg-amber-950/10 dark:border-amber-900/30 rounded-2xl text-xs font-black text-amber-700 dark:text-amber-400 flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-amber-500 animate-pulse shrink-0"></span>
            Educational analysis only: Not SEBI-registered financial advice. All investments carry risk.
          </div>

          {holdings.length === 0 ? (
            <div className="bg-white border border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800 rounded-3xl p-12 text-center max-w-lg mx-auto space-y-4 shadow-sm">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto animate-bounce">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              </div>
              <div className="space-y-1">
                <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-50">AI Review Not Available</h3>
                <p className="text-sm text-zinc-555 dark:text-zinc-400 leading-relaxed">
                  Log active holdings inside the Ledger tab to compile and execute a strategic LangGraph AI Review of your asset portfolio.
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
              {/* Strategic Compilation Controls */}
              <div className="flex flex-col sm:flex-row justify-between sm:items-center p-6 border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-[2rem] gap-4 shadow-sm">
                <div className="space-y-1">
                  <h4 className="text-sm font-extrabold text-zinc-900 dark:text-zinc-50 uppercase tracking-wider">
                    AI Portfolio Strategist Cockpit
                  </h4>
                  <p className="text-[10px] text-zinc-400">
                    {review
                      ? `Latest compilation: ${new Date(review.created_at).toLocaleString()}`
                      : "Ready to trigger LangGraph reasoning graph"}
                  </p>
                </div>

                <button
                  onClick={handleGenerateReview}
                  disabled={generatingReview}
                  className={`px-5 py-3 rounded-2xl text-xs font-black uppercase tracking-wider shadow-md flex items-center gap-2 cursor-pointer transition-all duration-300 ${
                    generatingReview
                      ? "bg-zinc-100 text-zinc-450 dark:bg-zinc-880 dark:text-zinc-500"
                      : "bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/10 hover:scale-105 active:scale-95"
                  }`}
                >
                  {generatingReview && (
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  )}
                  {generatingReview ? "Generating Strategic Insights..." : "Request AI Review"}
                </button>
              </div>

              {/* Skeletons/Errors State */}
              {generatingReview ? (
                <div className="space-y-6">
                  <div className="h-44 rounded-[2rem] bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
                  <div className="h-44 rounded-[2rem] bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
                  <div className="h-44 rounded-[2rem] bg-zinc-100 dark:bg-zinc-800 animate-pulse" />
                </div>
              ) : reviewError ? (
                <div className="p-6 border border-rose-250 bg-rose-50/20 dark:border-rose-900/30 dark:bg-rose-955/10 rounded-[2rem] text-center text-xs font-semibold text-rose-600 dark:text-rose-455 flex flex-col items-center gap-3">
                  <span>{reviewError}</span>
                  {(reviewError.toLowerCase().includes("token limit") || reviewError.toLowerCase().includes("guest")) && (
                    <button
                      type="button"
                      onClick={() => loginWithGoogle()}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-2xl bg-indigo-650 hover:bg-indigo-750 text-white text-xs font-bold transition-all duration-150 cursor-pointer active:scale-95 shadow-sm mx-auto"
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
                <div className="space-y-6 animate-fade-in">
                  {/* 1. Portfolio Summary Section */}
                  <div className="p-6 sm:p-8 border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-[2rem] shadow-sm space-y-4">
                    <h3 className="text-base sm:text-lg font-black text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 bg-indigo-500 rounded-full shrink-0 animate-pulse"></span>
                      Portfolio Summary
                    </h3>
                    <p className="text-xs text-zinc-400 font-medium">
                      A comprehensive strategic analysis of your portfolio holdings, concentration risks, and sector diversification spread.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                      <div className="space-y-2.5 bg-zinc-50/50 dark:bg-zinc-950/20 border border-zinc-150/40 dark:border-zinc-850/50 rounded-2xl p-4.5">
                        <h4 className="text-[10px] font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
                          <svg className="w-3.5 h-3.5 text-zinc-450" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                          Risk & Concentration Evaluation
                        </h4>
                        <p className="text-xs sm:text-sm text-zinc-700 dark:text-zinc-300 font-semibold leading-relaxed">
                          {renderTextWithCitations(review.risk_summary, review.evidence?.references)}
                        </p>
                      </div>
                      <div className="space-y-2.5 bg-zinc-50/50 dark:bg-zinc-950/20 border border-zinc-150/40 dark:border-zinc-850/50 rounded-2xl p-4.5">
                        <h4 className="text-[10px] font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-wider flex items-center gap-1.5">
                          <svg className="w-3.5 h-3.5 text-zinc-450" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
                          </svg>
                          Diversification & Sector Spreads
                        </h4>
                        <p className="text-xs sm:text-sm text-zinc-700 dark:text-zinc-300 font-semibold leading-relaxed">
                          {renderTextWithCitations(review.diversification_summary, review.evidence?.references)}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* 2. Recommended Actions Section */}
                  <div className="p-6 sm:p-8 border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-[2rem] shadow-sm space-y-4">
                    <h3 className="text-base sm:text-lg font-black text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 bg-emerald-500 rounded-full shrink-0"></span>
                      Recommended Actions
                    </h3>
                    <p className="text-xs text-zinc-400 font-medium">
                      Actionable adjustments covering rebalancing ratios, SIP allocations, sector trims, or risk reduction policies.
                    </p>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                      {/* Risk Alerts & Warnings */}
                      <div className="space-y-3">
                        <h4 className="text-[10px] font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">
                          Risk Alerts & Warnings
                        </h4>
                        {!review.warnings || review.warnings.length === 0 ? (
                          <div className="p-4 bg-emerald-50/30 border border-emerald-100 dark:bg-emerald-950/10 dark:border-emerald-900/30 rounded-2xl text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-2">
                            <span className="w-2.5 h-2.5 bg-emerald-500 rounded-full shrink-0"></span>
                            All allocations are currently within target risk tolerances.
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {review.warnings.map((w, idx) => {
                              const isRed = w.warning_level === "RED";
                              return (
                                <div
                                  key={idx}
                                  className={`p-4 border rounded-2xl space-y-1 ${
                                    isRed
                                      ? "border-rose-100 bg-rose-50/20 dark:border-rose-955 dark:bg-rose-955/10"
                                      : "border-amber-100 bg-amber-50/20 dark:border-amber-955 dark:bg-amber-955/10"
                                  }`}
                                >
                                  <div className="flex justify-between items-center">
                                    <span className={`inline-flex px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider border ${
                                      isRed
                                        ? "bg-rose-50 text-rose-700 border-rose-100/30 dark:bg-rose-950 dark:text-rose-455"
                                        : "bg-amber-50 text-amber-700 border-amber-100/30 dark:bg-amber-950 dark:text-amber-400"
                                    }`}>
                                      {w.symbol || "PORTFOLIO"}
                                    </span>
                                    <span className={`text-[9px] font-black uppercase tracking-wider ${
                                      isRed ? "text-rose-500" : "text-amber-500"
                                    }`}>
                                      {isRed ? "Strong warning" : "Medium warning"}
                                    </span>
                                  </div>
                                  <p className="text-xs text-zinc-650 dark:text-zinc-400 font-semibold leading-relaxed">
                                    {w.message}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>

                      {/* Rebalancing Guides */}
                      <div className="space-y-3">
                        <h4 className="text-[10px] font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">
                          Rebalancing Action Plan
                        </h4>
                        {!review.rebalancing_ideas || review.rebalancing_ideas.length === 0 ? (
                          <div className="p-4 bg-zinc-50 dark:bg-zinc-805 border border-zinc-150 dark:border-zinc-850 rounded-2xl text-xs font-semibold text-zinc-500 leading-relaxed">
                            Your current sector allocation weights align nicely with target profiles. No rebalancing changes recommended.
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {review.rebalancing_ideas.map((idea, idx) => {
                              const getActionBadge = (act: string) => {
                                if (act === "SIP") {
                                  return "bg-teal-50 text-teal-700 border-teal-100 dark:bg-teal-950/30 dark:text-teal-400";
                                }
                                if (act === "AVOID_ADDING") {
                                  return "bg-rose-50 text-rose-700 border-rose-100 dark:bg-rose-950/30 dark:text-rose-455";
                                }
                                if (act === "TRIM") {
                                  return "bg-amber-50 text-amber-700 border-amber-100 dark:bg-amber-955/30 dark:text-amber-400";
                                }
                                return "bg-indigo-50 text-indigo-700 border-indigo-100 dark:bg-indigo-950/30 dark:text-indigo-400";
                              };

                              return (
                                <div
                                  key={idx}
                                  className="p-4 border border-zinc-150 dark:border-zinc-800 bg-zinc-50/20 dark:bg-zinc-950/10 rounded-2xl flex items-start gap-4"
                                >
                                  <div className="space-y-1.5 flex-1 text-left">
                                    <div className="flex items-center gap-2">
                                      <span className={`inline-flex px-2 py-0.5 rounded-full text-[9px] font-black border ${getActionBadge(idea.action)}`}>
                                        {idea.action} {idea.target_change_percent ? `${Math.abs(idea.target_change_percent)}%` : ""}
                                      </span>
                                      <span className="text-xs font-black text-zinc-850 dark:text-zinc-100">
                                        {idea.sector} Sector
                                      </span>
                                    </div>
                                    <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed font-semibold">
                                      {idea.explanation}
                                    </p>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 3. Stocks Recommended Section */}
                  <div className="p-6 sm:p-8 border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-[2rem] shadow-sm space-y-4">
                    <h3 className="text-base sm:text-lg font-black text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 bg-purple-500 rounded-full shrink-0"></span>
                      Stocks Recommended
                    </h3>
                    <p className="text-xs text-zinc-400 font-medium">
                      Curated stock selections derived from your Watchlist candidates or similar high-suitability assets aligned with your profile.
                    </p>
                    <div className="pt-2">
                      {!review.potential_stock_picks || review.potential_stock_picks.length === 0 ? (
                        <p className="text-xs text-zinc-550 pl-1 leading-relaxed">
                          No specific stock recommendations found.
                        </p>
                      ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {review.potential_stock_picks.map((pick, idx) => {
                            const getBadgeClass = (comp: string) => {
                              if (comp === "EXCELLENT") return "bg-emerald-50 text-emerald-700 border-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-450";
                              if (comp === "GOOD") return "bg-indigo-50 text-indigo-700 border-indigo-100 dark:bg-indigo-950/30 dark:text-indigo-400";
                              if (comp === "NEUTRAL") return "bg-amber-50 text-amber-700 border-amber-100 dark:bg-amber-950/30 dark:text-amber-400";
                              return "bg-rose-50 text-rose-700 border-rose-100 dark:bg-rose-950/30 dark:text-rose-455";
                            };
                            return (
                              <div
                                key={idx}
                                className="p-4 border border-zinc-150 dark:border-zinc-800 bg-zinc-50/20 dark:bg-zinc-950/10 rounded-2xl flex flex-col justify-between gap-3 text-left hover:scale-[1.01] transition-transform duration-200"
                              >
                                <div className="space-y-1.5 flex-1">
                                  <div className="flex items-center gap-2">
                                    <span className="font-extrabold text-sm text-zinc-900 dark:text-zinc-100">
                                      {pick.symbol}
                                    </span>
                                    <span className="text-[10px] text-zinc-400 font-medium truncate max-w-[120px]">
                                      {pick.company_name}
                                    </span>
                                    <span className={`inline-flex px-2 py-0.5 rounded-full text-[9px] font-black border ${getBadgeClass(pick.compatibility)}`}>
                                      {pick.compatibility} FIT ({pick.score ? pick.score.toFixed(1) : "—"}/10)
                                    </span>
                                  </div>
                                  <p className="text-xs text-zinc-550 dark:text-zinc-400 leading-relaxed font-semibold">
                                    {pick.reasoning}
                                  </p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 4. News Insights Section */}
                  <div className="p-6 sm:p-8 border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-[2rem] shadow-sm space-y-4">
                    <h3 className="text-base sm:text-lg font-black text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 bg-blue-500 rounded-full shrink-0"></span>
                      News Insights
                    </h3>
                    <p className="text-xs text-zinc-400 font-medium">
                      Real-time compiled news signals and macro intelligence related to your holdings and watchlist, with interactive source references.
                    </p>
                    <div className="pt-2 pl-1">
                      {!review.evidence?.news_insights || review.evidence.news_insights.length === 0 ? (
                        <p className="text-xs text-zinc-555 leading-relaxed">
                          No news insights compiled in this review. Ensure active holdings or watchlist candidates exist.
                        </p>
                      ) : (
                        <ul className="space-y-3.5 list-disc pl-5">
                          {review.evidence.news_insights.map((bullet: string, idx: number) => (
                            <li 
                              key={idx}
                              className="text-xs sm:text-sm text-zinc-700 dark:text-zinc-300 font-semibold leading-relaxed"
                            >
                              {renderTextWithCitations(bullet, review.evidence?.references)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>

                  {/* 5. Expected Future Scenario Section */}
                  <div className="p-6 sm:p-8 border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-[2rem] shadow-sm space-y-4">
                    <h3 className="text-base sm:text-lg font-black text-zinc-900 dark:text-zinc-50 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: "#f97316" }}></span>
                      Expected Future Scenario
                    </h3>
                    <p className="text-xs text-zinc-400 font-medium">
                      Projected performance indicators, macro volatility factors, and analyst consensus forecasting long-term trends.
                    </p>
                    <div className="pt-2 bg-gradient-to-r from-orange-500/5 to-transparent border border-orange-500/10 dark:border-orange-500/5 rounded-2xl p-4.5">
                      <p className="text-xs sm:text-sm text-zinc-700 dark:text-zinc-300 font-semibold leading-relaxed">
                        {renderTextWithCitations(review.market_impact, review.evidence?.references)}
                      </p>
                    </div>
                  </div>

                </div>
              ) : (
                <div className="text-center p-12 bg-white border border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800 rounded-[2rem] text-zinc-500 shadow-sm">
                  Click the Request AI Review button to trigger the strategic portfolio compiler.
                </div>
              )}
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
    </div>
  );
}
