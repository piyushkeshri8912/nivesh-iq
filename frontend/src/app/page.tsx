"use client";

import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-[80vh] flex flex-col items-center justify-center text-center font-sans px-4 relative overflow-hidden animate-fadeIn">
      
      {/* Premium Background Grid Glow Effect */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f2937_1px,transparent_1px),linear-gradient(to_bottom,#1f2937_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_60%,transparent_100%)] opacity-30 pointer-events-none" />
      
      <div className="max-w-3xl relative z-10 space-y-8">
        
        {/* Animated Brand Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-bold uppercase tracking-wider animate-pulse">
          ✨ Welcome to the Future of Investing
        </div>

        {/* Dynamic Title Header */}
        <div className="space-y-4">
          <h1 className="text-4xl sm:text-6xl font-black tracking-tight text-zinc-900 dark:text-zinc-50 leading-none">
            Welcome to <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-teal-400 bg-clip-text text-transparent">NiveshIQ</span>
          </h1>
          <p className="text-lg sm:text-xl font-medium text-zinc-500 dark:text-zinc-400 max-w-2xl mx-auto leading-relaxed">
            Your personal, state-of-the-art AI portfolio intelligence assistant designed to elevate and simplify your investing journey.
          </p>
        </div>

        {/* Core Capabilities Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 pt-8">
          
          {/* Card 1: Portfolio */}
          <div className="group p-6 rounded-2xl bg-white dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800/80 shadow-sm transition-all duration-300 hover:border-indigo-500/30 hover:shadow-indigo-500/5 hover:-translate-y-1">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center text-lg font-bold mb-4 group-hover:bg-indigo-500 group-hover:text-white transition-all">
              📊
            </div>
            <h3 className="text-md font-bold text-zinc-800 dark:text-zinc-200">Portfolio Review</h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2 leading-relaxed">
              Track weighted average costs, allocations, and live unrealized gains and losses.
            </p>
          </div>

          {/* Card 2: AI Copilot */}
          <div className="group p-6 rounded-2xl bg-white dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800/80 shadow-sm transition-all duration-300 hover:border-purple-500/30 hover:shadow-purple-500/5 hover:-translate-y-1">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center text-lg font-bold mb-4 group-hover:bg-purple-500 group-hover:text-white transition-all">
              🤖
            </div>
            <h3 className="text-md font-bold text-zinc-800 dark:text-zinc-200">AI Copilot</h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2 leading-relaxed">
              Ask stock questions, execute reviews, and receive deep explainable market insights.
            </p>
          </div>

          {/* Card 3: Watchlist */}
          <div className="group p-6 rounded-2xl bg-white dark:bg-zinc-900/60 border border-zinc-200 dark:border-zinc-800/80 shadow-sm transition-all duration-300 hover:border-teal-500/30 hover:shadow-teal-500/5 hover:-translate-y-1">
            <div className="w-10 h-10 rounded-xl bg-teal-500/10 text-teal-400 flex items-center justify-center text-lg font-bold mb-4 group-hover:bg-teal-500 group-hover:text-white transition-all">
              👁️
            </div>
            <h3 className="text-md font-bold text-zinc-800 dark:text-zinc-200">Watchlist</h3>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-2 leading-relaxed">
              Monitor key stock price signals, Change since the day you added and follow tickers dynamically.
            </p>
          </div>

        </div>

        {/* Navigation Action CTA */}
        <div className="pt-8 flex flex-col sm:flex-row justify-center items-center gap-4">
          <Link
            href="/portfolio"
            className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm tracking-wide shadow-lg shadow-indigo-600/10 hover:shadow-indigo-600/20 active:scale-98 transition-all duration-200"
          >
            Launch Portfolio Dashboard
          </Link>
          <Link
            href="/ask"
            className="w-full sm:w-auto px-8 py-3.5 rounded-2xl border border-zinc-300 dark:border-zinc-800 bg-white hover:bg-zinc-50 dark:bg-zinc-900/30 dark:hover:bg-zinc-900/60 text-zinc-800 dark:text-zinc-200 font-bold text-sm tracking-wide hover:border-zinc-400 dark:hover:border-zinc-700 transition-all duration-200"
          >
            Consult AI Copilot
          </Link>
        </div>

      </div>
    </div>
  );
}
