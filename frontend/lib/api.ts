import { createAuthClient } from '@neondatabase/neon-js/auth';

// Neon Auth Client initialization
export const authClient = createAuthClient(
  typeof window !== "undefined"
    ? `${window.location.origin}/api/auth`
    : (process.env.NEON_AUTH_BASE_URL || "http://localhost:3000/api/auth")
);

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";

// Security Header Injection Helper
function getAuthHeaders(hasBody: boolean = false): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("niveshiq_token") : null;
  const headers: Record<string, string> = {
    "Authorization": `Bearer ${token || "demo-token"}`,
  };
  if (hasBody) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
}

// DATA INTERFACES
export interface UserProfile {
  risk_appetite: string;
  time_horizon: string;
  investment_goal: string;
  monthly_investment_budget: number;
  full_name?: string;
  dob?: string;
  profession?: string;
}

export interface UserProfileResponse extends UserProfile {
  id: number;
  user_id: string;
}

export interface Transaction {
  symbol: string;
  company_name?: string;
  transaction_type: string; // BUY, SELL
  quantity: number;
  price: number;
  fees?: number;
  executed_at?: string;
}

export interface TransactionResponse extends Transaction {
  id: number;
  user_id: string;
  executed_at: string;
}

export interface HoldingResponse {
  symbol: string;
  company_name?: string;
  quantity: number;
  average_buy_price: number;
  market_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  allocation_percent: number;
}

export interface PortfolioSummaryResponse {
  total_cost: number;
  total_value: number;
  total_unrealized_pnl: number;
  total_unrealized_pnl_percent: number;
  total_realized_pnl: number;
}

export interface PortfolioHoldingsListResponse {
  holdings: HoldingResponse[];
  summary: PortfolioSummaryResponse;
}

export interface RegisterResponse {
  message: string;
  email_sent: boolean;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// Helper to safely extract and store session tokens from Better Auth
async function syncSessionToken(): Promise<string | null> {
  try {
    const { data } = await authClient.getSession();
    const emailVal = data?.user?.email;
    if (emailVal) {
      localStorage.setItem("niveshiq_token", emailVal);
      return emailVal;
    }
  } catch (e) {
    console.error("Failed to sync session token:", e);
  }
  return null;
}

// AUTHENTICATION APIS
// No longer using email/password authentication endpoints

export async function loginWithGoogle(): Promise<void> {
  try {
    await authClient.signIn.social({
      provider: "google",
      callbackURL: typeof window !== "undefined" ? window.location.origin : "http://localhost:3000"
    });
  } catch (error) {
    console.error("Google sign-in error:", error);
    throw error;
  }
}

/**
 * Call this function on your landing / callback route (e.g., /auth/callback or a root layout useEffect)
 * to catch social redirects and record the token locally.
 */
export async function handleAuthCallback(): Promise<string | null> {
  return await syncSessionToken();
}

export async function loginAsGuest(): Promise<void> {
  // Generate a random guest ID
  const guestId = Math.random().toString(36).substring(2, 10);
  const email = `guest_${guestId}@niveshiq.guest`;
  // Neon Auth requires email, password, and name for email sign-up
  const password = `guest-pass-${Math.random().toString(36).substring(2, 15)}`;
  
  const { data, error } = await authClient.signUp.email({
    email,
    password,
    name: `GUEST_${guestId.toUpperCase()}`,
  });

  if (error || !data) {
    throw new Error(error?.message || "Guest login failed");
  }

  // Set the guest email in local storage as the authorization token
  localStorage.setItem("niveshiq_token", email);
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<string> {
  const res = await fetch(`${API_BASE}/profile/change-password`, {
    method: "POST",
    headers: getAuthHeaders(true),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to change password");
  }
  const data = await res.json();
  return data.message;
}

export async function deleteAccount(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/profile/delete-account`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to delete account");
  }
  return res.ok;
}

export async function logout(): Promise<void> {
  try {
    await authClient.signOut();
  } catch (e) {
    console.error("Failed to sign out of Neon Auth server:", e);
  }
  localStorage.removeItem("niveshiq_token");
  localStorage.removeItem("niveshiq_refresh_token");
  if (typeof window !== "undefined") {
    window.location.href = "/";
  }
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("niveshiq_token");
}

// PROFILE APIS
export async function fetchProfile(): Promise<UserProfileResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/profile`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error("Failed to fetch profile");
    return await res.json();
  } catch (error) {
    console.error("fetchProfile error:", error);
    return null;
  }
}

export async function saveProfile(profile: UserProfile): Promise<UserProfileResponse> {
  const res = await fetch(`${API_BASE}/profile`, {
    method: "POST",
    headers: getAuthHeaders(true),
    body: JSON.stringify(profile),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to save profile");
  }
  return await res.json();
}

// TRANSACTION APIS
export async function fetchTransactions(): Promise<TransactionResponse[]> {
  try {
    const res = await fetch(`${API_BASE}/transactions`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch transactions");
    return await res.json();
  } catch (error) {
    console.error("fetchTransactions error:", error);
    return [];
  }
}

export async function addTransaction(tx: Transaction): Promise<TransactionResponse> {
  const res = await fetch(`${API_BASE}/transactions`, {
    method: "POST",
    headers: getAuthHeaders(true),
    body: JSON.stringify(tx),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to record transaction");
  }
  return await res.json();
}

export async function updateTransaction(txId: number, tx: Transaction): Promise<TransactionResponse> {
  const res = await fetch(`${API_BASE}/transactions/${txId}`, {
    method: "PUT",
    headers: getAuthHeaders(true),
    body: JSON.stringify(tx),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to update transaction");
  }
  return await res.json();
}

export async function deleteTransaction(txId: number): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/transactions/${txId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    return res.ok;
  } catch (error) {
    console.error("deleteTransaction error:", error);
    return false;
  }
}

// PORTFOLIO APIS
export async function fetchHoldings(): Promise<PortfolioHoldingsListResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/portfolio/holdings`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch holdings");
    return await res.json();
  } catch (error) {
    console.error("fetchHoldings error:", error);
    return null;
  }
}

// ANALYTICS APIS
export interface SectorExposure {
  sector: string;
  value: number;
  percentage: number;
}

export interface MarketCapExposure {
  bucket: string;
  value: number;
  percentage: number;
}

export interface ExposuresResponse {
  sectors: SectorExposure[];
  market_caps: MarketCapExposure[];
}

export interface PortfolioHealthWarning {
  type: string;
  symbol: string;
  message: string;
}

export interface PortfolioHealthResponse {
  risk_score: number;
  diversification_score: number;
  warnings: PortfolioHealthWarning[];
  status: string;
}

export interface PortfolioSnapshotResponse {
  id: number;
  user_id: string;
  captured_at: string;
  total_value: number;
  total_cost: number;
}

export async function fetchExposures(): Promise<ExposuresResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/analytics/exposures`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch exposures");
    return await res.json();
  } catch (error) {
    console.error("fetchExposures error:", error);
    return null;
  }
}

export async function fetchPortfolioHealth(): Promise<PortfolioHealthResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/analytics/health`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch health");
    return await res.json();
  } catch (error) {
    console.error("fetchPortfolioHealth error:", error);
    return null;
  }
}

export async function fetchPerformanceHistory(): Promise<PortfolioSnapshotResponse[]> {
  try {
    const res = await fetch(`${API_BASE}/analytics/performance-history`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch performance history");
    return await res.json();
  } catch (error) {
    console.error("fetchPerformanceHistory error:", error);
    return [];
  }
}

export async function triggerSnapshot(): Promise<PortfolioSnapshotResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/analytics/snapshot`, {
      method: "POST",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to trigger snapshot");
    return await res.json();
  } catch (error) {
    console.error("triggerSnapshot error:", error);
    return null;
  }
}

// WATCHLIST APIS
export interface WatchlistItem {
  symbol: string;
}

export interface WatchlistItemResponse extends WatchlistItem {
  id: number;
  user_id: string;
  company_name?: string;
  market_price?: number;
  sector?: string;
  market_cap_bucket?: string;
  return_since_added?: number;
  added_at: string;
}

export async function fetchWatchlist(): Promise<WatchlistItemResponse[]> {
  try {
    const res = await fetch(`${API_BASE}/watchlist`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch watchlist");
    return await res.json();
  } catch (error) {
    console.error("fetchWatchlist error:", error);
    return [];
  }
}

export async function addWatchlistItem(item: WatchlistItem): Promise<WatchlistItemResponse> {
  const res = await fetch(`${API_BASE}/watchlist`, {
    method: "POST",
    headers: getAuthHeaders(true),
    body: JSON.stringify(item),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to add watchlist item");
  }
  return await res.json();
}

export async function deleteWatchlistItem(itemId: number): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/watchlist/${itemId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    return res.ok;
  } catch (error) {
    console.error("deleteWatchlistItem error:", error);
    return false;
  }
}

// NEWS APIS
export interface NewsItemResponse {
  symbol: string;
  company_name?: string;
  title: string;
  link: string;
  source: string;
  published_at: string;
  why_matters: string;
}

export async function fetchPortfolioNews(): Promise<NewsItemResponse[]> {
  try {
    const res = await fetch(`${API_BASE}/news`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch news");
    return await res.json();
  } catch (error) {
    console.error("fetchPortfolioNews error:", error);
    return [];
  }
}

// INSIGHTS APIS
export interface PortfolioReviewResponse {
  id: number;
  user_id: string;
  created_at: string;
  risk_summary: string;
  diversification_summary: string;
  rebalancing_ideas: any[];
  potential_stock_picks: any[];
  warnings: any[];
  market_impact: string;
  evidence: any;
  disclaimers: string;
}

export interface WatchlistAIRecommendation {
  symbol: string;
  recommendation: string;
  compatibility: string;
}

export async function fetchLatestPortfolioReview(): Promise<PortfolioReviewResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/insights`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error("Failed to fetch latest review");
    return await res.json();
  } catch (error) {
    console.error("fetchLatestPortfolioReview error:", error);
    return null;
  }
}

export async function generatePortfolioReview(): Promise<PortfolioReviewResponse> {
  const res = await fetch(`${API_BASE}/insights/generate`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to generate AI review");
  }
  return await res.json();
}


export interface AskResponse {
  answer: string;
  caveat: string;
  evidence?: string[];
  next_steps?: string[];
}

export async function askCopilot(
  query: string,
  temporary: boolean = false,
  sessionId?: string,
  onChunk?: (chunk: string) => void,
  onStatus?: (status: string) => void
): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: getAuthHeaders(true),
    body: JSON.stringify({ query, temporary, session_id: sessionId }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to query portfolio copilot");
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("Failed to read response stream from copilot");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";
  let finalPayload: AskResponse = { answer: "", caveat: "", evidence: [], next_steps: [] };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      // The last line may be partial, keep it in the buffer
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;

        try {
          const jsonStr = trimmed.substring(5).trim();
          const parsed = JSON.parse(jsonStr);

          if (parsed.type === "content") {
            answer += parsed.text;
            if (onChunk) {
              onChunk(parsed.text);
            }
          } else if (parsed.type === "status") {
            if (onStatus) {
              onStatus(parsed.text);
            }
          } else if (parsed.type === "done") {
            finalPayload = parsed.payload;
          }
        } catch (err) {
          console.error("Failed to parse SSE JSON chunk:", trimmed, err);
        }
      }
    }

    // Process any remaining content in the buffer
    const trimmedBuffer = buffer.trim();
    if (trimmedBuffer.startsWith("data:")) {
      try {
        const jsonStr = trimmedBuffer.substring(5).trim();
        const parsed = JSON.parse(jsonStr);
        if (parsed.type === "content") {
          answer += parsed.text;
          if (onChunk) {
            onChunk(parsed.text);
          }
        } else if (parsed.type === "status") {
          if (onStatus) {
            onStatus(parsed.text);
          }
        } else if (parsed.type === "done") {
          finalPayload = parsed.payload;
        }
      } catch (err) {
        console.error("Failed to parse final SSE JSON chunk:", trimmedBuffer, err);
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (!finalPayload.answer) {
    finalPayload.answer = answer;
  }

  return finalPayload;
}

export interface ChatSessionResponse {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string;
}

export interface ChatMessageResponse {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export async function fetchChatSessions(): Promise<ChatSessionResponse[]> {
  try {
    const res = await fetch(`${API_BASE}/ask/sessions`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch chat sessions");
    return await res.json();
  } catch (error) {
    console.error("fetchChatSessions error:", error);
    return [];
  }
}

export async function createChatSession(): Promise<{ session_id: string }> {
  const res = await fetch(`${API_BASE}/ask/sessions`, {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error("Failed to create chat session");
  return await res.json();
}

export async function fetchSessionMessages(sessionId: string): Promise<ChatMessageResponse[]> {
  try {
    const res = await fetch(`${API_BASE}/ask/sessions/${sessionId}/messages`, {
      cache: "no-store",
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to fetch session messages");
    return await res.json();
  } catch (error) {
    console.error("fetchSessionMessages error:", error);
    return [];
  }
}

export async function deleteChatSession(sessionId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/ask/sessions/${sessionId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    return res.ok;
  } catch (error) {
    console.error("deleteChatSession error:", error);
    return false;
  }
}