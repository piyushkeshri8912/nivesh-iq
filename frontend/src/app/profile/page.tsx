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
        <div className="p-0.5 rounded-3xl bg-gradient-to-br from-indigo-500/20 via-transparent to-teal-500/20 shadow-2xl backdrop-blur-xl">
          <div className="bg-zinc-950 border border-zinc-900 rounded-[22px] p-8 text-center space-y-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-indigo-500/10 border border-indigo-500/25 text-indigo-400 text-3xl">
              👤
            </div>
            
            <div className="space-y-2">
              <h2 className="text-xl font-black text-zinc-100 tracking-tight animate-fadeIn">
                Guest Profile
              </h2>
              <p className="text-zinc-500 text-xs font-semibold uppercase tracking-wider">
                Temporary Account Session
              </p>
            </div>

            <div className="p-4 bg-indigo-950/20 border border-indigo-900/40 rounded-2xl text-xs font-bold text-indigo-300 leading-relaxed text-left flex gap-3 items-start animate-fadeIn">
              <span className="text-indigo-400 text-base shrink-0 leading-none">ℹ️</span>
              <span>
                It is a guest account, It automatically gets deleted in 1hr along with any data it's store.
              </span>
            </div>

            <button
              onClick={() => logout()}
              className="w-full py-3 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 hover:text-zinc-100 font-bold text-xs uppercase tracking-wider rounded-xl transition-all border border-zinc-800 hover:border-zinc-700 cursor-pointer"
            >
              Sign Out of Guest Session
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 font-sans max-w-5xl mx-auto pb-12 animate-fadeIn">
      
      {/* Title */}
      <div>
        <h1 className="text-2xl font-black tracking-tight text-zinc-950 dark:text-zinc-50 sm:text-3xl">
          User Settings & <span className="bg-gradient-to-r from-indigo-500 to-teal-400 bg-clip-text text-transparent">Profile</span>
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 font-medium">
          Manage your personal details, dynamic risk parameters, and active credentials.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/40 rounded-2xl text-sm font-semibold text-rose-700 dark:text-rose-400">
          ⚠️ {error}
        </div>
      )}

      {success && (
        <div className="p-4 bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/40 rounded-2xl text-sm font-semibold text-emerald-700 dark:text-emerald-400 animate-fadeIn">
          ✓ {success}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Columns: Forms */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Card 1: Personal Details */}
          <div className="bg-white border border-zinc-200 rounded-3xl dark:bg-zinc-900 dark:border-zinc-800 p-6 sm:p-8 shadow-sm">
            <h2 className="text-lg font-extrabold text-zinc-800 dark:text-zinc-100 mb-6 flex items-center gap-2">
              👤 Personal Information
            </h2>
            
            <form onSubmit={handleSaveProfile} className="space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-1.5 ml-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter your name"
                    className="w-full px-4 py-3 rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 placeholder-zinc-400 text-sm font-semibold focus:outline-none focus:border-indigo-500/50 transition-colors"
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-1.5 ml-1">
                    Date of Birth
                  </label>
                  <input
                    type="date"
                    required
                    value={dob}
                    onChange={(e) => setDob(e.target.value)}
                    className="w-full px-4 py-3 rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 text-sm font-semibold focus:outline-none focus:border-indigo-500/50 transition-colors"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-1.5 ml-1">
                  Profession
                </label>
                <select
                  required
                  value={profession}
                  onChange={(e) => setProfession(e.target.value)}
                  className="w-full px-4 py-3 rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 text-sm font-semibold focus:outline-none focus:border-indigo-500/50 transition-colors cursor-pointer"
                >
                  <option value="Student">Student</option>
                  <option value="Salaried Employee">Salaried Employee</option>
                  <option value="Self-Employed">Self-Employed</option>
                  <option value="Others">Others</option>
                </select>
              </div>

              {/* Onboarding Constraints inside the save flow */}
              <div className="pt-6 border-t border-zinc-100 dark:border-zinc-800/80">
                <h3 className="text-md font-extrabold text-zinc-800 dark:text-zinc-200 mb-4 flex items-center gap-2">
                  📈 Investment Profile
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
                  <div>
                    <label className="block text-[10px] font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-1.5 ml-1">
                      Risk Appetite
                    </label>
                    <select
                      value={riskAppetite}
                      onChange={(e) => setRiskAppetite(e.target.value)}
                      className="w-full px-4 py-3 rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 text-sm font-semibold focus:outline-none cursor-pointer"
                    >
                      <option value="CONSERVATIVE">CONSERVATIVE</option>
                      <option value="MODERATE">MODERATE</option>
                      <option value="AGGRESSIVE">AGGRESSIVE</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-1.5 ml-1">
                      Time Horizon
                    </label>
                    <select
                      value={timeHorizon}
                      onChange={(e) => setTimeHorizon(e.target.value)}
                      className="w-full px-4 py-3 rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 text-sm font-semibold focus:outline-none cursor-pointer"
                    >
                      <option value="SHORT_TERM">SHORT TERM</option>
                      <option value="MEDIUM_TERM">MEDIUM TERM</option>
                      <option value="LONG_TERM">LONG TERM</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-1.5 ml-1">
                      Investment Goal
                    </label>
                    <select
                      value={investmentGoal}
                      onChange={(e) => setInvestmentGoal(e.target.value)}
                      className="w-full px-4 py-3 rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 text-sm font-semibold focus:outline-none cursor-pointer"
                    >
                      <option value="WEALTH_ACCUMULATION">WEALTH ACCUMULATION</option>
                      <option value="RETIREMENT">RETIREMENT</option>
                      <option value="INCOME">INCOME</option>
                      <option value="BALANCED">BALANCED</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-[10px] font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-widest mb-1.5 ml-1">
                    Monthly surplus budget (₹)
                  </label>
                  <input
                    type="number"
                    value={monthlyBudget}
                    onChange={(e) => setMonthlyBudget(Number(e.target.value))}
                    placeholder="Enter budget (e.g. 10000)"
                    className="w-full px-4 py-3 rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 placeholder-zinc-400 text-sm font-semibold focus:outline-none focus:border-indigo-500/50"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-4">
                <button
                  type="submit"
                  disabled={saving}
                  className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-2xl font-bold text-sm tracking-wide shadow-md shadow-indigo-600/10 disabled:opacity-50 transition-all cursor-pointer"
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
          <div className="bg-white border border-zinc-200 rounded-3xl dark:bg-zinc-900 dark:border-zinc-800 p-6 shadow-sm">
            <h2 className="text-md font-extrabold text-zinc-800 dark:text-zinc-100 mb-2 flex items-center gap-2">
              🔒 Log Out
            </h2>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-6 font-medium leading-relaxed">
              Disconnect from your session securely and wipe your local state cache.
            </p>
            <button
              onClick={() => logout()}
              className="w-full py-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-bold text-xs uppercase tracking-wider rounded-xl transition-all shadow-md cursor-pointer flex items-center justify-center gap-2"
            >
              Sign Out of Session
            </button>
          </div>

          {/* Card 3: Danger Zone - Delete Account */}
          <div className="bg-white border border-rose-200 rounded-3xl dark:bg-zinc-900 dark:border-rose-950/40 p-6 shadow-sm">
            <h2 className="text-md font-extrabold text-rose-600 dark:text-rose-400 mb-2 flex items-center gap-2">
              🚨 Danger Zone
            </h2>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-6 font-medium leading-relaxed">
              Actions in this section are permanent and cannot be reversed.
            </p>
            <button
              onClick={() => setShowDeleteModal(true)}
              className="w-full py-3 bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs uppercase tracking-wider rounded-xl transition-all shadow-md shadow-rose-600/10 cursor-pointer flex items-center justify-center gap-2"
            >
              🗑&nbsp;&nbsp;Delete My Account
            </button>
          </div>

        </div>

      </div>

      {/* Delete Account Modal Dialog Overlay */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-md p-4 sm:p-6 animate-fadeIn">
          <div className="relative max-w-md w-full p-0.5 rounded-3xl bg-gradient-to-br from-rose-500/30 via-transparent to-zinc-900 shadow-2xl">
            <div className="bg-zinc-950 border border-zinc-900 rounded-[22px] p-6 text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-500 text-2xl mb-4">
                ⚠️
              </div>
              
              <h3 className="text-lg font-black text-zinc-100 leading-tight animate-fadeIn">
                Delete Account Permanently?
              </h3>
              
              <p className="text-xs text-zinc-400 mt-4 leading-relaxed font-medium">
                This action is **irreversible**. It will immediately cascade and delete all your holdings, watchlist tickers, snapshots, portfolio AI reviews, and login metrics permanently.
              </p>

              <div className="mt-6 text-left space-y-2">
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest leading-none ml-1">
                  Type <span className="text-zinc-200">"DELETE MY ACCOUNT"</span> to confirm:
                </label>
                <input
                  type="text"
                  required
                  value={deleteInput}
                  onChange={(e) => setDeleteInput(e.target.value)}
                  placeholder="DELETE MY ACCOUNT"
                  className="w-full px-4 py-3 rounded-2xl bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-700 text-sm font-semibold focus:outline-none focus:border-rose-500/50"
                />
              </div>

              <div className="grid grid-cols-2 gap-4 mt-6">
                <button
                  onClick={() => {
                    setShowDeleteModal(false);
                    setDeleteInput("");
                  }}
                  className="py-3 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 rounded-xl font-bold text-xs tracking-wider uppercase transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={deleteLoading || deleteInput !== "DELETE MY ACCOUNT"}
                  className="py-3 bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white rounded-xl font-bold text-xs tracking-wider uppercase transition-all cursor-pointer flex items-center justify-center gap-1 shadow-md shadow-rose-600/10"
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
