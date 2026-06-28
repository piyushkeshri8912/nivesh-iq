"use client";

import { WatchlistItemResponse } from "@/lib/api";

interface WatchlistTableProps {
  items: WatchlistItemResponse[];
  onDelete: (id: number) => Promise<void>;
  loading: boolean;
}

export default function WatchlistTable({
  items,
  onDelete,
  loading,
}: WatchlistTableProps) {
  if (loading) {
    return (
      <div className="bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6 shadow-xl shadow-black/10 overflow-hidden animate-pulse">
        <div className="h-6 w-48 bg-zinc-800 rounded-lg mb-6"></div>
        <div className="space-y-4">
          {[1, 2, 3].map((n) => (
            <div key={n} className="grid grid-cols-5 gap-4 py-3 border-b border-zinc-800/60">
              <div className="h-4 bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-800 rounded col-span-1"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="bg-zinc-900/30 border border-zinc-800 rounded-2xl p-12 shadow-xl shadow-black/5 text-center space-y-4">
        <div className="w-14 h-14 bg-indigo-500/10 border border-indigo-500/25 rounded-2xl flex items-center justify-center mx-auto">
          <svg
            className="w-6 h-6 text-indigo-400"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
            />
          </svg>
        </div>
        <div className="space-y-1">
          <h4 className="text-base font-heading font-bold text-zinc-100 uppercase tracking-wider">
            No items in watchlist
          </h4>
          <p className="text-xs font-sans text-zinc-400 max-w-sm mx-auto leading-relaxed">
            Add stock tickers to monitor live market values, sectors, and price returns since addition.
          </p>
        </div>
      </div>
    );
  }

  const formatPrice = (price?: number, symbol?: string) => {
    if (price === undefined) return "—";
    const isIndian = symbol?.endsWith(".NS") || symbol?.endsWith(".BO");
    return isIndian
      ? `₹${price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : `$${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="bg-zinc-900/30 border border-zinc-800 rounded-2xl shadow-xl shadow-black/15 overflow-hidden">
      <div className="px-6 py-5 border-b border-zinc-800/80 flex justify-between items-center bg-zinc-900/50">
        <h3 className="text-sm sm:text-base font-heading font-bold text-zinc-100 uppercase tracking-wider">
          Watchlist Explorer ({items.length})
        </h3>
      </div>
      
      {/* Table view */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest bg-zinc-950/40">
              <th className="px-6 py-4">Symbol</th>
              <th className="px-6 py-4">Live Price</th>
              <th className="px-6 py-4">Sector / Bucket</th>
              <th className="px-6 py-4">Returns Since Added</th>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 font-sans">
            {items.map((item) => {
              const formatReturns = (ret?: number) => {
                if (ret === undefined || ret === null) return "—";
                const isPositive = ret >= 0;
                return (
                  <span className={`text-xs font-bold font-mono ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                    {isPositive ? "+" : ""}{ret.toFixed(2)}%
                  </span>
                );
              };

              return (
                <tr
                  key={item.id}
                  className="group hover:bg-zinc-800/20 transition-all duration-150"
                >
                  {/* Symbol & Company */}
                  <td className="px-6 py-4">
                    <div>
                      <span className="text-xs sm:text-sm font-bold text-zinc-100 font-mono">
                        {item.symbol}
                      </span>
                      <span className="block text-[10px] font-semibold text-zinc-400 max-w-[180px] truncate mt-0.5">
                        {item.company_name || item.symbol}
                      </span>
                    </div>
                  </td>
                  
                  {/* Live Price */}
                  <td className="px-6 py-4 font-bold font-mono text-zinc-200">
                    {formatPrice(item.market_price, item.symbol)}
                  </td>
                  
                  {/* Sector & Market Cap Bucket */}
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1.5">
                      <span className="inline-flex px-2 py-0.5 rounded text-[9px] font-bold bg-zinc-800/50 text-zinc-300 border border-zinc-700/30 uppercase tracking-wider">
                        {item.sector || "Other"}
                      </span>
                      {item.market_cap_bucket && (
                        <span className="inline-flex px-2 py-0.5 rounded text-[9px] font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 uppercase tracking-wider">
                          {item.market_cap_bucket}
                        </span>
                      )}
                    </div>
                  </td>
                  
                  {/* Returns Since Added */}
                  <td className="px-6 py-4">
                    {formatReturns(item.return_since_added)}
                  </td>
                  
                  {/* Delete action */}
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => onDelete(item.id)}
                      className="p-1.5 rounded-lg text-zinc-400 hover:text-rose-400 hover:bg-rose-500/10 transition-all cursor-pointer"
                      title="Remove from Watchlist"
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                        strokeWidth={2}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
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
      </div>
    </div>
  );
}
