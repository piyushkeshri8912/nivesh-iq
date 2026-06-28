"use client";

import Link from "next/link";

export default function Home() {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center text-center font-sans px-6 relative overflow-hidden animate-fadeIn">
      {/* AI Portfolio Intelligence Background - Full viewport coverage */}
      <div className="fixed inset-0 -z-10 pointer-events-none">
        <svg
          className="w-full h-full"
          viewBox="0 0 3840 2160"
          preserveAspectRatio="xMidYMid slice"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <radialGradient id="bg" cx="70%" cy="35%">
              <stop offset="0%" stopColor="#0b2f66" />
              <stop offset="35%" stopColor="#071a3d" />
              <stop offset="100%" stopColor="#020812" />
            </radialGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="8" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <rect width="100%" height="100%" fill="url(#bg)" />
          {/* ambient waves */}
          <g opacity="0.18" stroke="#3ea0ff" fill="none">
            <path d="M0 1700 C700 1400,1200 2000,1900 1700 S3000 1400,3840 1800" strokeWidth="3" />
            <path d="M0 1780 C800 1500,1300 2050,2100 1750 S3100 1450,3840 1850" strokeWidth="2" />
            <path d="M0 1860 C900 1550,1500 2100,2400 1800 S3200 1500,3840 1900" strokeWidth="2" />
          </g>
          {/* globe */}
          <g transform="translate(2550,980)">
            <circle r="520" fill="none" stroke="#52a8ff" strokeWidth="4" opacity="0.8" filter="url(#glow)" />
            <circle r="500" fill="none" stroke="#1f5fbf" strokeWidth="1" />
            <g stroke="#2f7fe8" opacity="0.35">
              <ellipse rx="500" ry="500" fill="none" />
              <ellipse rx="400" ry="500" fill="none" />
              <ellipse rx="300" ry="500" fill="none" />
              <ellipse rx="200" ry="500" fill="none" />
              <ellipse rx="500" ry="150" fill="none" />
              <ellipse rx="500" ry="300" fill="none" />
            </g>
          </g>
          {/* network */}
          <g stroke="#59b0ff" strokeWidth="2" opacity="0.5">
            <line x1="1800" y1="600" x2="2100" y2="750" />
            <line x1="2100" y1="750" x2="2400" y2="520" />
            <line x1="2400" y1="520" x2="2800" y2="700" />
            <line x1="2100" y1="750" x2="2300" y2="1050" />
          </g>
          <g fill="#59b0ff" filter="url(#glow)">
            <circle cx="1800" cy="600" r="8" />
            <circle cx="2100" cy="750" r="8" />
            <circle cx="2400" cy="520" r="8" />
            <circle cx="2800" cy="700" r="8" />
            <circle cx="2300" cy="1050" r="8" />
          </g>
          {/* finance charts */}
          <g opacity="0.25">
            <rect x="2800" y="1450" width="700" height="350" rx="12" fill="none" stroke="#2f7fe8" />
            <polyline points="2850,1680 2950,1620 3020,1650 3120,1550 3200,1600 3330,1500 3450,1560 3520,1470" fill="none" stroke="#59b0ff" strokeWidth="4" />
          </g>
          <g opacity="0.18">
            <rect x="1700" y="1200" width="25" height="280" fill="#59b0ff" />
            <rect x="1770" y="1100" width="25" height="380" fill="#59b0ff" />
            <rect x="1840" y="1250" width="25" height="230" fill="#59b0ff" />
            <rect x="1910" y="950" width="25" height="530" fill="#59b0ff" />
            <rect x="1980" y="800" width="25" height="680" fill="#59b0ff" />
          </g>
        </svg>
      </div>

      <div className="max-w-4xl relative z-10 space-y-7">
        {/* Hero Typography Section */}
        <div className="space-y-4">
          <h1 className="text-4xl sm:text-6xl font-heading font-black tracking-tight text-white leading-none">
            AI Portfolio <span className="bg-gradient-to-r from-indigo-400 via-indigo-200 to-emerald-400 bg-clip-text text-transparent">Intelligence</span>
          </h1>
          <p className="text-base sm:text-lg font-sans font-medium text-zinc-400 max-w-2xl mx-auto leading-relaxed">
            NiveshIQ delivers institutional-grade explainable analytics, rebalancing models, and real-time news analysis to optimize your wealth strategies.
          </p>
        </div>

        {/* Feature Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Card 1: Portfolio Diagnostics */}
          <div className="group p-5 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 shadow-lg shadow-black/5 hover:bg-zinc-900/60 hover:border-zinc-700/60 transition-all duration-200 cursor-pointer text-left">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-3 transition-all duration-200 group-hover:bg-indigo-500 group-hover:text-white shrink-0">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="text-xs font-heading font-bold text-zinc-100 uppercase tracking-wider">Portfolio</h3>
            <p className="text-xs font-sans text-zinc-400 mt-2 leading-relaxed font-normal">
              Track portfolio live returns and portfolio historical timeline.
            </p>
          </div>

          {/* Card 2: AI Advisor Copilot */}
          <div className="group p-5 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 shadow-lg shadow-black/5 hover:bg-zinc-900/60 hover:border-zinc-700/60 transition-all duration-200 cursor-pointer text-left">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-3 transition-all duration-200 group-hover:bg-indigo-500 group-hover:text-white shrink-0">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <h3 className="text-xs font-heading font-bold text-zinc-100 uppercase tracking-wider">AI Copilot</h3>
            <p className="text-xs font-sans text-zinc-400 mt-2 leading-relaxed font-normal">
              Inquire about portfolio, holdings, news, earnings and general finance.
            </p>
          </div>

          {/* Card 3: Watchlist Signals */}
          <div className="group p-5 rounded-2xl bg-zinc-900/40 border border-zinc-800/80 shadow-lg shadow-black/5 hover:bg-zinc-900/60 hover:border-zinc-700/60 transition-all duration-200 cursor-pointer text-left">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-3 transition-all duration-200 group-hover:bg-indigo-500 group-hover:text-white shrink-0">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </div>
            <h3 className="text-xs font-heading font-bold text-zinc-100 uppercase tracking-wider">Watchlist Explorer</h3>
            <p className="text-xs font-sans text-zinc-400 mt-2 leading-relaxed font-normal">
              Track tickers and review performance deltas since addition.
            </p>
          </div>
        </div>

        {/* Actions Button Panel */}
        <div className="flex flex-col sm:flex-row justify-center items-center gap-4">
          <Link
            href="/portfolio"
            className="w-full sm:w-auto px-8 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-heading font-bold text-xs uppercase tracking-wider transition-all duration-200 cursor-pointer shadow-lg shadow-indigo-600/10 hover:shadow-indigo-600/20 active:scale-98"
          >
            Portfolio 
          </Link>
          <Link
            href="/ask"
            className="w-full sm:w-auto px-8 py-3.5 rounded-xl border border-zinc-800 bg-zinc-900/30 hover:bg-zinc-900/60 hover:border-zinc-700 text-zinc-200 hover:text-white font-heading font-bold text-xs uppercase tracking-wider transition-all duration-200 cursor-pointer active:scale-98"
          >
            AI Copilot
          </Link>
        </div>
      </div>
    </div>
  );
}
