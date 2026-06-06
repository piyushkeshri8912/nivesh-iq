"use client";

import { useState } from "react";
import { loginWithGoogle, loginAsGuest } from "@/lib/api";

interface LoginPanelProps {
  onLoginSuccess: () => void;
}

export default function LoginPanel({ onLoginSuccess }: LoginPanelProps) {
  const [loading, setLoading] = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGuestLogin = async () => {
    setGuestLoading(true);
    setError(null);
    try {
      await loginAsGuest();
      onLoginSuccess();
    } catch (err: any) {
      setError(err.message || "Failed to enter guest session.");
    } finally {
      setGuestLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      await loginWithGoogle();
    } catch (err: any) {
      setError(err.message || "Google login failed.");
      setLoading(false);
    }
  };

  return (
    <div className="relative w-full max-w-sm p-0.5 rounded-3xl bg-gradient-to-br from-indigo-500/20 via-transparent to-teal-500/20 shadow-2xl backdrop-blur-xl shrink-0 overflow-hidden font-sans">
      <div className="bg-zinc-950/90 border border-zinc-900 rounded-[22px] p-6 sm:p-8 relative z-10 flex flex-col items-center">
        
        {/* Brand Header */}
        <div className="text-center mb-6 flex flex-col items-center">
          <img
            src="/logo.svg"
            alt="NiveshIQ Logo"
            className="w-12 h-12 rounded-2xl mb-3 object-contain"
          />
          <h1 className="text-xl sm:text-2xl font-black text-zinc-100 tracking-tight">
            Nivesh<span className="bg-gradient-to-r from-indigo-400 to-teal-400 bg-clip-text text-transparent">IQ</span>
          </h1>
          <p className="text-xs text-zinc-400 mt-1 font-medium">
            AI-Driven Portfolio Intelligence Engine
          </p>
        </div>

        {/* Display Message Alerts */}
        {error && (
          <div className="w-full mb-4 p-3.5 rounded-xl bg-rose-950/20 border border-rose-900/40 text-xs font-semibold text-rose-400 animate-fadeIn">
            ⚠️ {error}
          </div>
        )}

        {/* Guest Login and Google OAuth buttons */}
        <div className="flex flex-col gap-3.5 items-center justify-center w-full mt-2">
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={loading || guestLoading}
            className="w-full py-3 rounded-2xl border border-zinc-800 hover:border-zinc-700 bg-zinc-900/40 hover:bg-zinc-900/70 text-zinc-150 font-bold text-xs tracking-wider uppercase transition-all duration-200 flex items-center justify-center gap-2.5 cursor-pointer h-[46px] active:scale-98 disabled:opacity-50"
          >
            {loading ? (
              <span className="w-4 h-4 border-2 border-zinc-400 border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" fill="#EA4335"/>
                </svg>
                <span>Continue with Google</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={handleGuestLogin}
            disabled={loading || guestLoading}
            className="w-full py-3 rounded-2xl border border-indigo-900/30 hover:border-indigo-800 bg-indigo-950/20 hover:bg-indigo-950/40 text-indigo-350 hover:text-indigo-300 font-bold text-xs tracking-wider uppercase transition-all duration-200 flex items-center justify-center gap-2.5 cursor-pointer h-[46px] active:scale-98 disabled:opacity-50"
          >
            {guestLoading ? (
              <span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                <span>Try as Guest (1h temporary)</span>
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}
