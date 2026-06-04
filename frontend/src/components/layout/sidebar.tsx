"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { authClient } from "@/lib/api";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export default function Sidebar({ 
  isOpen, 
  onClose,
  isCollapsed,
  onToggleCollapse
}: SidebarProps) {
  const pathname = usePathname();
  const [userSession, setUserSession] = useState<{ name: string; image?: string | null } | null>(null);

  // Fetch logged-in user profile details (Google name and avatar image) on mount
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
      .catch((err) => console.error("Error fetching sidebar session:", err));
  }, []);

  const navItems = [
    {
      name: "Portfolio",
      path: "/portfolio",
      icon: (
        <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
    },
    {
      name: "Watchlist",
      path: "/watchlist",
      icon: (
        <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      ),
    },
    {
      name: "Ask AI",
      path: "/ask",
      icon: (
        <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      ),
    },
  ];

  return (
    <aside className={`fixed inset-y-0 left-0 z-50 bg-zinc-950 text-zinc-100 flex flex-col border-r border-zinc-800 transform md:translate-x-0 md:static md:h-auto transition-all duration-300 ease-in-out ${
      isCollapsed ? "md:w-[72px]" : "md:w-64"
    } ${isOpen ? "translate-x-0 w-64" : "-translate-x-full w-64"}`}>
      
      {/* Sidebar Header */}
      <div className={`h-16 flex items-center justify-between border-b border-zinc-800 ${
        isCollapsed ? "md:px-3 md:justify-center" : "px-6"
      }`}>
        
        {/* Brand Logo & Name */}
        <Link href="/" className="flex items-center gap-3 shrink-0" onClick={onClose}>
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-lg tracking-wider shadow-md shadow-indigo-500/20 shrink-0">
            N
          </div>
          <span className={`font-semibold text-lg tracking-tight bg-gradient-to-r from-zinc-50 to-zinc-400 bg-clip-text text-transparent transition-all duration-300 ${
            isCollapsed ? "md:hidden" : ""
          }`}>
            NiveshIQ
          </span>
        </Link>

        {/* Desktop Collapse Arrow Button */}
        <button
          onClick={onToggleCollapse}
          className="hidden md:flex p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 focus:outline-none cursor-pointer shrink-0 transition-transform duration-300"
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {isCollapsed ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          )}
        </button>

        {/* Mobile Close Button */}
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 md:hidden focus:outline-none cursor-pointer"
          aria-label="Close sidebar"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 px-4 py-6 space-y-1.5 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.path;
          return (
            <Link
              key={item.name}
              href={item.path}
              onClick={onClose}
              className={`group flex items-center gap-3 rounded-2xl text-sm font-semibold transition-all duration-200 ${
                isCollapsed 
                  ? "md:p-3 md:justify-center" 
                  : "gap-3 px-4 py-3"
              } ${
                isActive
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/10"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
              }`}
            >
              <div className={`transition-transform duration-200 group-hover:scale-110 shrink-0 ${
                isActive ? "text-white" : "text-zinc-400 group-hover:text-zinc-200"
              }`}>
                {item.icon}
              </div>
              <span className={`transition-all duration-300 ${
                isCollapsed ? "md:hidden" : ""
              }`}>
                {item.name}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Footer User Profile Redirection Button */}
      <div className={`border-t border-zinc-800 ${
        isCollapsed ? "md:p-2" : "p-4"
      }`}>
        <Link
          href="/profile"
          className={`block bg-zinc-900/50 hover:bg-zinc-900 border border-zinc-800/80 hover:border-zinc-700/80 rounded-2xl transition-all duration-300 group cursor-pointer ${
            isCollapsed ? "md:p-1.5 flex justify-center" : "p-4"
          }`}
          title="User Settings"
        >
          <div className="flex items-center gap-3 shrink-0">
            {userSession?.image ? (
              <img
                src={userSession.image}
                alt={userSession.name}
                className="w-10 h-10 rounded-full object-cover shrink-0 shadow-sm border border-zinc-800/40"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center text-sm font-extrabold text-white shrink-0 shadow-sm border border-indigo-500/30">
                {userSession?.name ? userSession.name.charAt(0).toUpperCase() : "U"}
              </div>
            )}
            
            <div className={`transition-all duration-300 ${
              isCollapsed ? "md:hidden" : ""
            }`}>
              <p className="text-[10px] text-zinc-500 group-hover:text-zinc-400 leading-none">Welcome back,</p>
              <p className="text-xs font-semibold text-zinc-200 group-hover:text-white mt-1 truncate max-w-[120px]">
                {userSession?.name || "Investor"}
              </p>
            </div>
          </div>
        </Link>
      </div>
    </aside>
  );
}
