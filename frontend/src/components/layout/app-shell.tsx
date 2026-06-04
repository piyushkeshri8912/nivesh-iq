"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./sidebar";
import LoginPanel from "../auth/login-panel";
import { authClient } from "@/lib/api";
import AskAIDrawer from "./ask-ai-drawer";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
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
      {/* Mobile sidebar backdrop overlay */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-40 bg-zinc-950/60 transition-opacity duration-300 md:hidden"
        />
      )}

      {/* Mobile-only menu toggle button */}
      <button
        onClick={() => setSidebarOpen(true)}
        className="fixed bottom-4 left-4 z-40 p-3.5 rounded-full bg-indigo-600 text-white shadow-2xl md:hidden hover:bg-indigo-500 active:scale-95 transition-all focus:outline-none cursor-pointer"
        aria-label="Open menu"
      >
        <svg className="w-5.5 h-5.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Responsive Collapsible Sidebar */}
      <Sidebar 
        isOpen={sidebarOpen} 
        onClose={() => setSidebarOpen(false)} 
        isCollapsed={isCollapsed}
        onToggleCollapse={handleToggleCollapse}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto bg-zinc-50 dark:bg-zinc-950">
          <div className="max-w-7xl mx-auto p-4 sm:p-8">{children}</div>
        </main>
      </div>

      {/* Sliding compact Ask AI chat drawer panel */}
      <AskAIDrawer isOpen={isChatOpen} onClose={() => setIsChatOpen(false)} />

      {/* Floating assistant action sparkles button (hidden on /ask itself) */}
      {pathname !== "/ask" && (
        <button
          onClick={() => setIsChatOpen(true)}
          className="fixed bottom-6 right-6 z-40 bg-indigo-600 hover:bg-indigo-700 text-white rounded-full p-4 shadow-xl shadow-indigo-600/20 hover:scale-105 active:scale-95 transition-all cursor-pointer border border-indigo-500/35 flex items-center justify-center"
          title="Ask Portfolio Assistant"
        >
          {/* Sparkles / message icon */}
          <svg className="w-5.5 h-5.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </button>
      )}
    </div>
  );
}
