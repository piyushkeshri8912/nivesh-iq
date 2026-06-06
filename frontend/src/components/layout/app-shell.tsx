"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import Sidebar from "./sidebar";
import LoginPanel from "../auth/login-panel";
import { authClient } from "@/lib/api";
import AskAIDrawer from "./ask-ai-drawer";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [userSession, setUserSession] = useState<{ name: string; image?: string | null } | null>(null);
  const pathname = usePathname();

  // Safely initialize state from localStorage on client mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const cached = localStorage.getItem("sidebar-collapsed");
      if (cached === "true") {
        setIsCollapsed(true);
      }
      
      const token = localStorage.getItem("niveshiq_token");
      const hasVerifier = window.location.search.includes("neon_auth_session_verifier");
      
      if (token && !hasVerifier) {
        setIsAuthenticated(true);
      } else {
        // Automatically check/verify session using the Neon Auth client SDK
        const checkSession = async () => {
          try {
            const { data } = await authClient.getSession();
            const emailVal = data?.user?.email;
            if (emailVal) {
              localStorage.setItem("niveshiq_token", emailVal);
              setIsAuthenticated(true);
              
              if (hasVerifier) {
                const newUrl = window.location.pathname;
                window.history.replaceState({}, document.title, newUrl);
              }
              return;
            }
          } catch (e) {
            console.error("Session verification failed:", e);
          }
          localStorage.removeItem("niveshiq_token");
          setIsAuthenticated(false);
        };
        checkSession();
      }
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      authClient.getSession()
        .then(({ data }) => {
          if (data?.user) {
            setUserSession({
              name: data.user.name,
              image: data.user.image,
            });
          }
        })
        .catch((err) => console.error("Error fetching app shell session:", err));
    }
  }, [isAuthenticated]);

  const handleToggleCollapse = () => {
    const nextVal = !isCollapsed;
    setIsCollapsed(nextVal);
    if (typeof window !== "undefined") {
      localStorage.setItem("sidebar-collapsed", String(nextVal));
    }
  };

  // Prevent hydration flash of unauthenticated view
  if (isAuthenticated === null) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-zinc-950">
        <span className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Render Login Panel for unauthenticated sessions
  if (isAuthenticated === false) {
    return (
      <div className="min-h-screen w-screen overflow-y-auto bg-zinc-950 flex flex-col items-center py-12 px-4 relative font-sans">
        {/* Sleek Grid Overlay background */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#18181b_1px,transparent_1px),linear-gradient(to_bottom,#18181b_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-60 pointer-events-none" />
        
        <div className="my-auto w-full flex justify-center z-10 relative">
          <LoginPanel onLoginSuccess={() => setIsAuthenticated(true)} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-50 dark:bg-zinc-950 font-sans animate-fadeIn">
      {/* Collapsible Sidebar for Desktop */}
      <Sidebar 
        isOpen={false} 
        onClose={() => {}} 
        isCollapsed={isCollapsed}
        onToggleCollapse={handleToggleCollapse}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto bg-zinc-50 dark:bg-zinc-950">
          <div className="max-w-7xl mx-auto p-4 pb-20 sm:p-8 sm:pb-8">{children}</div>
        </main>
      </div>

      {/* Sliding compact Ask AI chat drawer panel (Desktop only) */}
      <AskAIDrawer isOpen={isChatOpen} onClose={() => setIsChatOpen(false)} />

      {/* Floating assistant action sparkles button (hidden on /ask itself and hidden on mobile screens) */}
      {pathname !== "/ask" && (
        <button
          onClick={() => setIsChatOpen(true)}
          className="hidden md:flex fixed bottom-6 right-6 z-40 bg-indigo-650 hover:bg-indigo-750 text-white rounded-full p-4 shadow-xl shadow-indigo-650/20 hover:scale-105 active:scale-95 transition-all cursor-pointer border border-indigo-500/35 items-center justify-center"
          title="Ask Portfolio Assistant"
        >
          {/* Sparkles / message icon */}
          <svg className="w-5.5 h-5.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </button>
      )}

      {/* Sleek bottom navigation bar for mobile viewports */}
      <nav className="fixed bottom-0 inset-x-0 z-40 bg-zinc-950/85 backdrop-blur-lg border-t border-zinc-800/80 md:hidden flex items-center justify-around py-3 px-2 shadow-[0_-8px_30px_rgba(0,0,0,0.4)]">
        {/* Portfolio Tab */}
        <Link
          href="/portfolio"
          className={`flex flex-col items-center gap-1 transition-all duration-200 cursor-pointer ${
            pathname === "/portfolio"
              ? "text-indigo-500 scale-105"
              : "text-zinc-500 hover:text-zinc-350"
          }`}
        >
          <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
          </svg>
          <span className="text-[10px] font-bold tracking-tight">Portfolio</span>
        </Link>

        {/* Watchlist Tab */}
        <Link
          href="/watchlist"
          className={`flex flex-col items-center gap-1 transition-all duration-200 cursor-pointer ${
            pathname === "/watchlist"
              ? "text-indigo-500 scale-105"
              : "text-zinc-500 hover:text-zinc-350"
          }`}
        >
          <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
          <span className="text-[10px] font-bold tracking-tight">Watchlist</span>
        </Link>

        {/* Ask AI Tab */}
        <Link
          href="/ask"
          className={`flex flex-col items-center gap-1 transition-all duration-200 cursor-pointer ${
            pathname === "/ask"
              ? "text-indigo-500 scale-105"
              : "text-zinc-500 hover:text-zinc-350"
          }`}
        >
          <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span className="text-[10px] font-bold tracking-tight">Ask AI</span>
        </Link>

        {/* Profile/Settings Tab */}
        <Link
          href="/profile"
          className={`flex flex-col items-center gap-1 transition-all duration-200 cursor-pointer ${
            pathname === "/profile"
              ? "text-indigo-500 scale-105"
              : "text-zinc-500 hover:text-zinc-350"
          }`}
        >
          {userSession?.image ? (
            <img
              src={userSession.image}
              alt="Profile"
              className={`w-5 h-5 rounded-full object-cover shrink-0 border border-zinc-800/40 ${
                pathname === "/profile" ? "ring-2 ring-indigo-500 ring-offset-2 ring-offset-zinc-950" : ""
              }`}
            />
          ) : userSession?.name ? (
            <div className={`w-5 h-5 rounded-full bg-indigo-600 text-white font-extrabold text-[9px] flex items-center justify-center border border-indigo-500/30 ${
              pathname === "/profile" ? "ring-2 ring-indigo-500 ring-offset-2 ring-offset-zinc-950" : ""
            }`}>
              {userSession.name.charAt(0).toUpperCase()}
            </div>
          ) : (
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          )}
          <span className="text-[10px] font-bold tracking-tight">Profile</span>
        </Link>
      </nav>
    </div>
  );
}
