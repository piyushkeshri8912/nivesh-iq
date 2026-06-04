"use client";

import { useEffect, useState } from "react";
import { 
  fetchWatchlist, 
  deleteWatchlistItem, 
  WatchlistItemResponse 
} from "@/lib/api";
import WatchlistTable from "@/components/watchlist/watchlist-table";
import AddWatchlistDialog from "@/components/watchlist/add-watchlist-dialog";

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItemResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const loadWatchlistData = async () => {
    setLoading(true);
    try {
      const data = await fetchWatchlist();
      setItems(data);
    } catch (err) {
      console.error("Failed to load watchlist data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWatchlistData();
  }, []);

  const handleDeleteWatchlistItem = async (id: number) => {
    if (confirm("Are you sure you want to remove this stock from your watchlist?")) {
      const success = await deleteWatchlistItem(id);
      if (success) {
        loadWatchlistData();
      } else {
        alert("Failed to remove watchlist item.");
      }
    }
  };

  const handleAddSuccess = () => {
    loadWatchlistData();
  };

  return (
    <div className="space-y-8 animate-fade-in text-left relative min-h-[75vh]">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
            Watchlist Explorer
          </h1>
          <p className="text-xs sm:text-sm text-zinc-500 dark:text-zinc-400 font-medium">
            Monitor potential stock picks, track live market prices, and review their returns since addition.
          </p>
        </div>
        
        <div className="flex shrink-0">
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
            Add Ticker
          </button>
        </div>
      </div>

      {/* Main layout */}
      <div className="space-y-8">
        {/* Watchlist Main Explorer Table */}
        <WatchlistTable
          items={items}
          onDelete={handleDeleteWatchlistItem}
          loading={loading}
        />
      </div>

      {/* Add Stock modal Dialog */}
      <AddWatchlistDialog
        isOpen={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        onSuccess={handleAddSuccess}
      />
    </div>
  );
}
