"use client";

import { useState, useEffect } from "react";
import { fetchProfile, saveProfile, deleteAccount, logout } from "@/lib/api";

export default function ProfilePage() {
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Personal Info Form States
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [profession, setProfession] = useState("Salaried Employee");

  // Investment Profile Form States
  const [riskAppetite, setRiskAppetite] = useState("MODERATE");
  const [timeHorizon, setTimeHorizon] = useState("MEDIUM_TERM");
  const [investmentGoal, setInvestmentGoal] = useState("BALANCED");
  const [monthlyBudget, setMonthlyBudget] = useState(0);

  // Delete Account modal state
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteInput, setDeleteInput] = useState("");
  const [deleteLoading, setDeleteLoading] = useState(false);

  const loadProfileData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProfile();
      if (data) {
        setProfile(data);
        setName(data.full_name || "");
        setDob(data.dob || "");
        setProfession(data.profession || "Salaried Employee");
        setRiskAppetite(data.risk_appetite || "MODERATE");
        setTimeHorizon(data.time_horizon || "MEDIUM_TERM");
        setInvestmentGoal(data.investment_goal || "BALANCED");
        setMonthlyBudget(data.monthly_investment_budget || 0);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load user profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      await loadProfileData();
    };
    fetchData();
  }, []);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const updated = await saveProfile({
        full_name: name.trim() || undefined,
        dob: dob || undefined,
        profession: profession,
        risk_appetite: riskAppetite,
        time_horizon: timeHorizon,
        investment_goal: investmentGoal,
        monthly_investment_budget: Number(monthlyBudget),
      });
      setProfile(updated);
      setSuccess("Profile settings successfully updated in the database!");
      
      // Dispatch custom event to notify other modules
      window.dispatchEvent(new Event("profile-updated"));
    } catch (err: any) {
      setError(err.message || "Failed to update profile settings.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteInput !== "DELETE MY ACCOUNT") {
      alert("Please type exactly 'DELETE MY ACCOUNT' to confirm.");
      return;
    }

    setDeleteLoading(true);
    try {
      await deleteAccount();
      await logout();
    } catch (err: any) {
      alert(err.message || "Failed to delete account.");
      setDeleteLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <span className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const token = typeof window !== "undefined" ? localStorage.getItem("niveshiq_token") : null;
  const isGuest = !!(token && (token.startsWith("guest_") || token.endsWith("@niveshiq.guest")));

  if (isGuest) {
    return (
      <div className="max-w-md mx-auto space-y-6 pt-16 font-sans text-center animate-fadeIn select-none">
        <div className="p-0.5 rounded-3xl bg-gradient-to-br from-indigo-500/10 via-transparent to-emerald-500/10 shadow-2xl backdrop-blur-xl">
          <div className="bg-zinc-950 border border-zinc-900 rounded-[22px] p-8 text-center space-y-6">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-3xl">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            
            <div className="space-y-1">
              <h2 className="text-xl font-heading font-black text-zinc-100 tracking-tight animate-fadeIn">
                Guest Profile
              </h2>
              <p className="text-zinc-500 text-[10px] font-bold uppercase tracking-wider">
                Temporary Account Session
              </p>
            </div>

            <div className="p-4 bg-indigo-950/20 border border-indigo-500/20 rounded-xl text-xs font-semibold text-indigo-305 leading-relaxed text-left flex gap-3 items-start animate-fadeIn">
              <svg className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>
                You are logged in under a guest session. Guest account data is automatically wiped every hour to maintain server security.
              </span>
            </div>

            <button
              onClick={() => logout()}
              className="w-full py-3.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-200 hover:text-white font-heading font-bold text-xs uppercase tracking-wider rounded-xl transition-all border border-zinc-800 hover:border-zinc-700 cursor-pointer active:scale-98"
            >
              Sign Out of Guest Session
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12 animate-fadeIn text-left">
      
      {/* Title */}
      <div>
        <h1 className="text-2xl font-heading font-black tracking-tight text-white sm:text-3xl">
          User Settings & <span className="bg-gradient-to-r from-indigo-400 via-indigo-200 to-emerald-400 bg-clip-text text-transparent">Profile</span>
        </h1>
        <p className="text-xs sm:text-sm text-zinc-400 mt-1 font-medium">
          Manage your personal details, dynamic risk parameters, and active credentials.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-rose-500/5 border border-rose-500/20 rounded-xl text-xs font-semibold text-rose-400 flex items-center gap-2">
          <svg className="w-4 h-4 text-rose-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="p-4 bg-emerald-500/5 border border-emerald-500/20 rounded-xl text-xs font-semibold text-emerald-400 flex items-center gap-2 animate-fadeIn">
          <svg className="w-4 h-4 text-emerald-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{success}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Columns: Forms */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Card 1: Personal Details */}
          <div className="bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6 sm:p-8 shadow-xl shadow-black/10">
            <h2 className="text-base font-heading font-bold text-zinc-100 mb-6 flex items-center gap-2.5 uppercase tracking-wider">
              <svg className="w-5 h-5 text-indigo-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span>Personal Information</span>
            </h2>
            
            <form onSubmit={handleSaveProfile} className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <div className="space-y-1.5">
                  <label className="block text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest ml-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter your name"
                    className="w-full px-4 py-3.5 rounded-xl border border-zinc-800 bg-zinc-950/20 text-zinc-100 placeholder-zinc-600 text-xs font-semibold focus:outline-none focus:border-indigo-500/50 transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="block text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest ml-1">
                    Date of Birth
                  </label>
                  <input
                    type="date"
                    required
                    value={dob}
                    onChange={(e) => setDob(e.target.value)}
                    className="w-full px-4 py-3.5 rounded-xl border border-zinc-800 bg-zinc-950/20 text-zinc-100 text-xs font-semibold focus:outline-none focus:border-indigo-500/50 transition-colors"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest ml-1">
                  Profession
                </label>
                <select
                  required
                  value={profession}
                  onChange={(e) => setProfession(e.target.value)}
                  className="w-full px-4 py-3.5 rounded-xl border border-zinc-800 bg-zinc-950/20 text-zinc-200 text-xs font-semibold focus:outline-none focus:border-indigo-500/50 transition-colors cursor-pointer"
                >
                  <option value="Student">Student</option>
                  <option value="Salaried Employee">Salaried Employee</option>
                  <option value="Self-Employed">Self-Employed</option>
                  <option value="Others">Others</option>
                </select>
              </div>

              {/* Onboarding Constraints inside the save flow */}
              <div className="pt-6 border-t border-zinc-800/80">
                <h3 className="text-base font-heading font-bold text-zinc-100 mb-6 flex items-center gap-2.5 uppercase tracking-wider">
                  <svg className="w-5 h-5 text-indigo-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                  </svg>
                  <span>Investment Profile</span>
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-5">
                  <div className="space-y-1.5">
                    <label className="block text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest ml-1">
                      Risk Appetite
                    </label>
                    <select
                      value={riskAppetite}
                      onChange={(e) => setRiskAppetite(e.target.value)}
                      className="w-full px-4 py-3.5 rounded-xl border border-zinc-800 bg-zinc-950/20 text-zinc-200 text-xs font-semibold focus:outline-none cursor-pointer"
                    >
                      <option value="CONSERVATIVE">CONSERVATIVE</option>
                      <option value="MODERATE">MODERATE</option>
                      <option value="AGGRESSIVE">AGGRESSIVE</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest ml-1">
                      Time Horizon
                    </label>
                    <select
                      value={timeHorizon}
                      onChange={(e) => setTimeHorizon(e.target.value)}
                      className="w-full px-4 py-3.5 rounded-xl border border-zinc-800 bg-zinc-950/20 text-zinc-200 text-xs font-semibold focus:outline-none cursor-pointer"
                    >
                      <option value="SHORT_TERM">SHORT TERM</option>
                      <option value="MEDIUM_TERM">MEDIUM TERM</option>
                      <option value="LONG_TERM">LONG TERM</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest ml-1">
                      Investment Goal
                    </label>
                    <select
                      value={investmentGoal}
                      onChange={(e) => setInvestmentGoal(e.target.value)}
                      className="w-full px-4 py-3.5 rounded-xl border border-zinc-800 bg-zinc-950/20 text-zinc-200 text-xs font-semibold focus:outline-none cursor-pointer"
                    >
                      <option value="WEALTH_ACCUMULATION">WEALTH ACCUMULATION</option>
                      <option value="RETIREMENT">RETIREMENT</option>
                      <option value="INCOME">INCOME</option>
                      <option value="BALANCED">BALANCED</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-[10px] font-heading font-bold text-zinc-400 uppercase tracking-widest ml-1">
                    Monthly surplus budget (₹)
                  </label>
                  <input
                    type="number"
                    value={monthlyBudget}
                    onChange={(e) => setMonthlyBudget(Number(e.target.value))}
                    placeholder="Enter budget (e.g. 10000)"
                    className="w-full px-4 py-3.5 rounded-xl border border-zinc-800 bg-zinc-950/20 text-zinc-100 placeholder-zinc-650 text-xs font-semibold focus:outline-none focus:border-indigo-500/50"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-4">
                <button
                  type="submit"
                  disabled={saving}
                  className="px-6 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-heading font-bold text-xs uppercase tracking-wider transition-all duration-200 cursor-pointer shadow-md shadow-indigo-600/10 active:scale-98"
                >
                  {saving ? "Saving settings..." : "Save Settings Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>

        {/* Right Columns: Active Action Cards */}
        <div className="space-y-8">
          
          {/* Card 2: Logout Operations */}
          <div className="bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6 shadow-xl shadow-black/10 space-y-4">
            <div className="space-y-1">
              <h2 className="text-sm font-heading font-bold text-zinc-100 flex items-center gap-2 uppercase tracking-wider">
                <svg className="w-4.5 h-4.5 text-zinc-450" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h3a3 3 0 013 3v2" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M17 15l5-5-5-5M21 10H9" />
                </svg>
                <span>Log Out</span>
              </h2>
              <p className="text-xs text-zinc-400 leading-relaxed font-normal">
                Disconnect from your session securely and wipe your local state cache.
              </p>
            </div>
            <button
              onClick={() => logout()}
              className="w-full py-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-heading font-bold text-xs uppercase tracking-wider rounded-xl transition-all cursor-pointer active:scale-98 border border-zinc-700/30"
            >
              Sign Out of Session
            </button>
          </div>

          {/* Card 3: Danger Zone - Delete Account */}
          <div className="bg-zinc-900/40 border border-rose-950/40 rounded-2xl p-6 shadow-xl shadow-black/10 space-y-4">
            <div className="space-y-1">
              <h2 className="text-sm font-heading font-bold text-rose-400 flex items-center gap-2 uppercase tracking-wider">
                <svg className="w-4.5 h-4.5 text-rose-450" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>Danger Zone</span>
              </h2>
              <p className="text-xs text-zinc-400 leading-relaxed font-normal">
                Permanently delete all profile, transactions, watchlists, and AI summaries forever.
              </p>
            </div>
            <button
              onClick={() => setShowDeleteModal(true)}
              className="w-full py-3 bg-rose-600/10 hover:bg-rose-600 border border-rose-500/20 text-rose-400 hover:text-white font-heading font-bold text-xs uppercase tracking-wider rounded-xl transition-all cursor-pointer active:scale-98"
            >
              Delete My Account
            </button>
          </div>

        </div>

      </div>

      {/* Delete Account Modal Dialog Overlay */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-md p-6 animate-fadeIn">
          <div className="relative max-w-md w-full p-0.5 rounded-3xl bg-gradient-to-br from-rose-500/30 via-transparent to-zinc-900 shadow-2xl">
            <div className="bg-zinc-950 border border-zinc-900 rounded-[22px] p-6 text-center space-y-4">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-500 text-2xl mb-2 animate-bounce">
                <svg className="w-6 h-6 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              
              <div className="space-y-1">
                <h3 className="text-lg font-heading font-black text-zinc-100 leading-tight">
                  Delete Account Permanently?
                </h3>
                <p className="text-xs text-zinc-400 leading-relaxed font-normal">
                  This action is permanent and cannot be reversed. It will cascade and delete all your holdings, watchlist tickers, snapshots, and AI analyses.
                </p>
              </div>

              <div className="text-left space-y-2 pt-2">
                <label className="block text-[10px] font-heading font-bold text-zinc-500 uppercase tracking-widest leading-none ml-1">
                  Type <span className="text-zinc-200">"DELETE MY ACCOUNT"</span> to confirm:
                </label>
                <input
                  type="text"
                  required
                  value={deleteInput}
                  onChange={(e) => setDeleteInput(e.target.value)}
                  placeholder="DELETE MY ACCOUNT"
                  className="w-full px-4 py-3 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-700 text-xs font-semibold focus:outline-none focus:border-rose-500/50"
                />
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <button
                  onClick={() => {
                    setShowDeleteModal(false);
                    setDeleteInput("");
                  }}
                  className="py-3 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 rounded-xl font-heading font-bold text-xs tracking-wider uppercase transition-all cursor-pointer border border-zinc-800 hover:border-zinc-700"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={deleteLoading || deleteInput !== "DELETE MY ACCOUNT"}
                  className="py-3 bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white rounded-xl font-heading font-bold text-xs tracking-wider uppercase transition-all cursor-pointer flex items-center justify-center gap-1 shadow-md shadow-rose-600/10"
                >
                  {deleteLoading ? (
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    "Delete Forever"
                  )}
                </button>
              </div>

            </div>
          </div>
        </div>
      )}

    </div>
  );
}
