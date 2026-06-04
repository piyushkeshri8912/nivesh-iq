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
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-sm overflow-hidden animate-pulse">
        <div className="h-6 w-48 bg-zinc-200 dark:bg-zinc-800 rounded-lg mb-6"></div>
        <div className="space-y-4">
          {[1, 2, 3].map((n) => (
            <div key={n} className="grid grid-cols-5 gap-4 py-3 border-b border-zinc-100 dark:border-zinc-800">
              <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded col-span-1"></div>
              <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded col-span-1"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-12 shadow-sm text-center">
        <div className="w-16 h-16 bg-indigo-50 dark:bg-indigo-955/30 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg
            className="w-8 h-8 text-indigo-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
            />
          </svg>
        </div>
        <h4 className="text-base font-bold text-zinc-900 dark:text-zinc-50 mb-1">
          No items in watchlist
        </h4>
        <p className="text-sm text-zinc-555 dark:text-zinc-400 max-w-sm mx-auto mb-6">
          Add stocks you are watching to monitor their live market prices and returns.
        </p>
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
    <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl shadow-sm overflow-hidden">
      <div className="px-6 py-5 border-b border-zinc-100 dark:border-zinc-800 flex justify-between items-center bg-zinc-50/20 dark:bg-zinc-950/20">
        <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-50">
          Watchlist Explorer ({items.length})
        </h3>
      </div>
      
      {/* Table view */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-zinc-100 dark:border-zinc-800 text-[11px] font-bold text-zinc-400 dark:text-zinc-500 uppercase bg-zinc-50/50 dark:bg-zinc-950/30">
              <th className="px-6 py-4">Symbol</th>
              <th className="px-6 py-4">Live Price</th>
              <th className="px-6 py-4">Sector / Bucket</th>
              <th className="px-6 py-4">Returns Since Added</th>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800/80">
            {items.map((item) => {
              const formatReturns = (ret?: number) => {
                if (ret === undefined || ret === null) return "—";
                const isPositive = ret >= 0;
                return (
                  <span className={`text-sm font-extrabold ${isPositive ? "text-emerald-500 dark:text-emerald-450" : "text-rose-500 dark:text-rose-455"}`}>
                    {isPositive ? "+" : ""}{ret.toFixed(2)}%
                  </span>
                );
              };

              return (
                <tr
                  key={item.id}
                  className="group hover:bg-zinc-50/50 dark:hover:bg-zinc-950/20 transition-all"
                >
                  {/* Symbol & Company */}
                  <td className="px-6 py-4.5">
                    <div>
                      <span className="text-sm font-bold text-zinc-900 dark:text-zinc-50">
                        {item.symbol}
                      </span>
                      <span className="block text-[11px] font-medium text-zinc-400 dark:text-zinc-500 max-w-[180px] truncate">
                        {item.company_name || item.symbol}
                      </span>
                    </div>
                  </td>
                  
                  {/* Live Price */}
                  <td className="px-6 py-4.5 font-semibold text-sm text-zinc-800 dark:text-zinc-200">
                    {formatPrice(item.market_price, item.symbol)}
                  </td>
                  
                  {/* Sector & Market Cap Bucket */}
                  <td className="px-6 py-4.5">
                    <div className="flex flex-wrap gap-1.5">
                      <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-semibold bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 border border-zinc-200/20 dark:border-none">
                        {item.sector || "Other"}
                      </span>
                      {item.market_cap_bucket && (
                        <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50/50 text-indigo-600 dark:bg-indigo-950/30 dark:text-indigo-300">
                          {item.market_cap_bucket}
                        </span>
                      )}
                    </div>
                  </td>
                  
                  {/* Returns Since Added */}
                  <td className="px-6 py-4.5 font-semibold text-sm">
                    {formatReturns(item.return_since_added)}
                  </td>
                  
                  {/* Delete action */}
                  <td className="px-6 py-4.5 text-right">
                    <button
                      onClick={() => onDelete(item.id)}
                      className="p-1.5 rounded-lg text-zinc-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-955/30 dark:hover:text-rose-400 transition-all opacity-80 group-hover:opacity-100 cursor-pointer"
                      title="Remove from Watchlist"
                    >
                      <svg
                        className="w-4 h-4"
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
      </div>
    </div>
  );
}
