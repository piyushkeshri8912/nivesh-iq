"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { authClient } from "@/lib/api";

export default function Navbar() {
  const pathname = usePathname();
  const [userSession, setUserSession] = useState<{ name: string; image?: string | null } | null>(null);

  useEffect(() => {
    authClient.getSession()
      .then(({ data }) => {
        if (data?.user) {
          setUserSession({
            name: data.user.name,
            image: data.user.image,
          });
        }
      })
      .catch((err) => console.error("Error fetching navbar session:", err));
  }, []);

  const navItems = [
    {
      name: "Portfolio",
      path: "/portfolio",
      icon: (
        <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
    },
    {
      name: "Watchlist",
      path: "/watchlist",
      icon: (
        <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      ),
    },
    {
      name: "Copilot",
      path: "/ask",
      icon: (
        <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      ),
    },
  ];

  return (
    <>
      {/* Mobile-only Top Header Bar (all pages) */}
      <header className="md:hidden fixed top-0 inset-x-0 h-14 flex items-center justify-between px-5 z-50 select-none"
        style={{
          background: "linear-gradient(180deg, #0D1224 0%, #09101F 50%, #060B16 100%)",
          borderBottom: "1px solid rgba(85, 120, 255, 0.12)",
          backdropFilter: "blur(20px)",
        }}>
        <Link href="/" className="flex items-center gap-2.5">
          <img
            src="/logo.svg"
            alt="NiveshIQ Logo"
            className="w-7 h-7 rounded-lg shrink-0 object-contain"
          />
          <span className="font-heading font-black text-xs tracking-widest text-white uppercase">
            NiveshIQ
          </span>
        </Link>
      </header>

      {/* Desktop Top Navbar Layout */}
      <header className={`hidden md:flex fixed top-0 inset-x-0 h-16 items-center justify-between px-8 z-40 select-none ${
        pathname !== "/" ? "bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800/80" : ""
      }`}
        style={pathname === "/" ? {
          background: "linear-gradient(180deg, #0D1224 0%, #09101F 50%, #060B16 100%)",
          borderBottom: "1px solid rgba(85, 120, 255, 0.12)",
          backdropFilter: "blur(20px)",
        } : undefined}>
        {/* Left: Brand Logo */}
        <Link href="/" className="flex items-center gap-3 shrink-0">
          <img
            src="/logo.svg"
            alt="NiveshIQ Logo"
            className="w-8 h-8 rounded-lg shrink-0 object-contain"
          />
          <span className="font-heading font-black text-sm tracking-widest text-white uppercase">
            NiveshIQ
          </span>
        </Link>

        {/* Center: Navigation Links */}
        <nav className="flex items-center gap-2">
          {navItems.map((item) => {
            const isActive = pathname === item.path;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`px-4 py-2.5 rounded-xl text-[10px] font-heading font-bold uppercase tracking-wider transition-all duration-200 ${
                  isActive
                    ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-md shadow-indigo-650/5"
                    : "text-zinc-400 hover:text-zinc-200 border border-transparent"
                }`}
              >
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Right: Investor Session Profile */}
        <div className="shrink-0">
          <Link
            href="/profile"
            className={`flex items-center gap-2.5 bg-zinc-900/40 hover:bg-zinc-900 border rounded-xl px-3 py-1.5 transition-all duration-200 ${
              pathname === "/profile" ? "border-indigo-500/40" : "border-zinc-800/80 hover:border-zinc-700/80"
            }`}
          >
            <span className="text-[10px] font-sans text-zinc-400 font-medium">Investor Session</span>
            {userSession?.image ? (
              <img
                src={userSession.image}
                alt={userSession.name}
                className="w-6 h-6 rounded-full object-cover shrink-0 border border-zinc-800"
              />
            ) : (
              <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center text-[9px] font-extrabold text-white uppercase shrink-0 border border-indigo-500/30">
                {userSession?.name ? userSession.name.charAt(0).toUpperCase() : "I"}
              </div>
            )}
          </Link>
        </div>
      </header>

      {/* Mobile Bottom Tabbar Navigation Layout */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 h-16 bg-zinc-950/85 backdrop-blur-lg border-t border-zinc-800/80 flex items-center justify-around py-2 px-2 shadow-[0_-8px_30px_rgba(0,0,0,0.5)] z-40 select-none">
        {navItems.map((item) => {
          const isActive = pathname === item.path;
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`flex flex-col items-center gap-1 transition-all duration-200 cursor-pointer ${
                isActive ? "text-indigo-400 scale-105" : "text-zinc-500 hover:text-zinc-350"
              }`}
            >
              {item.icon}
              <span className="text-[9px] font-heading font-bold uppercase tracking-wider">{item.name}</span>
            </Link>
          );
        })}

        {/* Profile Link */}
        <Link
          href="/profile"
          className={`flex flex-col items-center gap-1 transition-all duration-200 cursor-pointer ${
            pathname === "/profile" ? "text-indigo-400 scale-105" : "text-zinc-500 hover:text-zinc-350"
          }`}
        >
          {userSession?.image ? (
            <img
              src={userSession.image}
              alt="Profile"
              className={`w-5 h-5 rounded-full object-cover shrink-0 border ${
                pathname === "/profile" ? "border-indigo-500" : "border-zinc-800"
              }`}
            />
          ) : (
            <div className={`w-5 h-5 rounded-full bg-indigo-600 text-white font-extrabold text-[9px] flex items-center justify-center border border-indigo-500/30 ${
              pathname === "/profile" ? "ring-2 ring-indigo-500 ring-offset-2 ring-offset-zinc-950" : ""
            }`}>
              {userSession?.name ? userSession.name.charAt(0).toUpperCase() : "I"}
            </div>
          )}
          <span className="text-[9px] font-heading font-bold uppercase tracking-wider">Profile</span>
        </Link>
      </nav>
    </>
  );
}
