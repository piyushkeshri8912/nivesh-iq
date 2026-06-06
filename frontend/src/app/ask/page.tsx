"use client";

import { useState, useEffect, useRef } from "react";
import { 
  askCopilot, 
  AskResponse, 
  fetchChatSessions, 
  createChatSession, 
  fetchSessionMessages, 
  deleteChatSession, 
  ChatSessionResponse,
  loginWithGoogle
} from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Message {
  id: string;
  sender: "user" | "copilot";
  text: string;
  payload?: AskResponse;
  timestamp: Date;
}

export default function AskPage() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [previousSessionId, setPreviousSessionId] = useState<string | null>(null);
  const [statusSteps, setStatusSteps] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [temporary, setTemporary] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);


  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, isThinking]);

  // Load chat sessions on mount & when temporary mode toggles
  useEffect(() => {
    if (!temporary) {
      loadSessionsAndSelectRecent();
    }
  }, [temporary]);

  const loadSessionsAndSelectRecent = async () => {
    try {
      const list = await fetchChatSessions();
      setSessions(list);
      if (list.length > 0 && !activeSessionId) {
        setActiveSessionId(list[0].id);
        loadSessionMessages(list[0].id);
      }
    } catch (err) {
      console.error("Failed to load chat sessions:", err);
    }
  };

  const loadSessionMessages = async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      const msgs = await fetchSessionMessages(sessionId);
      setMessages(
        msgs.map((m) => ({
          id: String(m.id),
          sender: m.role === "user" ? "user" : "copilot",
          text: m.content,
          timestamp: new Date(m.created_at),
        }))
      );
    } catch (err: any) {
      console.error(err);
      setError("Failed to retrieve chat messages. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSession = (sessionId: string) => {
    if (loading) return;
    setActiveSessionId(sessionId);
    loadSessionMessages(sessionId);
    setSessionsOpen(false);
  };

  const handleNewChat = () => {
    if (loading) return;
    setActiveSessionId(null);
    setMessages([]);
    setError(null);
    setSessionsOpen(false);
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (loading) return;
    try {
      const success = await deleteChatSession(sessionId);
      if (success) {
        setSessions((prev) => prev.filter((s) => s.id !== sessionId));
        if (activeSessionId === sessionId) {
          setActiveSessionId(null);
          setMessages([]);
        }
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  const handleToggleIncognito = () => {
    if (loading) return;
    if (!temporary) {
      // Toggle ON temporary mode
      setPreviousSessionId(activeSessionId);
      setActiveSessionId(null);
      setMessages([]);
      setTemporary(true);
    } else {
      // Toggle OFF temporary mode
      setTemporary(false);
      if (previousSessionId) {
        setActiveSessionId(previousSessionId);
        loadSessionMessages(previousSessionId);
      } else {
        loadSessionsAndSelectRecent();
      }
    }
  };

  const handleSend = async (textToSend: string) => {
    if (!textToSend.trim() || loading) return;

    setLoading(true);
    setIsThinking(true);
    setError(null);
    setStatusSteps([]);

    let currentSessionId = activeSessionId;

    // Auto-create session if not in temporary mode and no session is active
    if (!temporary && !currentSessionId) {
      try {
        const { session_id } = await createChatSession();
        currentSessionId = session_id;
        setActiveSessionId(session_id);
        setSessions((prev) => [
          { id: session_id, title: textToSend.substring(0, 40), created_at: new Date().toISOString(), last_message_at: new Date().toISOString() },
          ...prev,
        ]);
      } catch (err) {
        console.error("Failed to create session on first query:", err);
      }
    }

    const userMsgId = `user-${Date.now()}`;
    const newUserMessage: Message = {
      id: userMsgId,
      sender: "user",
      text: textToSend,
      timestamp: new Date(),
    };

    const copilotMsgId = `copilot-${Date.now()}`;
    const newCopilotMessage: Message = {
      id: copilotMsgId,
      sender: "copilot",
      text: "",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, newUserMessage, newCopilotMessage]);
    setQuery("");

    try {
      const data = await askCopilot(
        textToSend,
        temporary,
        currentSessionId || undefined,
        (chunk) => {
          setIsThinking(false); // Stop showing thinking checklist on first text chunk
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === copilotMsgId ? { ...msg, text: msg.text + chunk } : msg
            )
          );
        },
        (status) => {
          setStatusSteps((prev) => {
            if (prev.includes(status)) return prev;
            return [...prev, status];
          });
        }
      );
      
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === copilotMsgId
            ? { ...msg, text: data.answer, payload: data }
            : msg
        )
      );

      // Refresh sessions to update dynamically generated title from the first message
      if (!temporary) {
        const list = await fetchChatSessions();
        setSessions(list);
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to retrieve copilot recommendations. Please try again later.");
      setMessages((prev) => prev.filter((msg) => msg.id !== copilotMsgId));
    } finally {
      setLoading(false);
      setIsThinking(false);
    }
  };

  const handleRetry = () => {
    const userMsgs = messages.filter((m) => m.sender === "user");
    if (userMsgs.length === 0) return;
    const lastUserMsg = userMsgs[userMsgs.length - 1];
    setMessages((prev) => prev.filter((msg) => msg.id !== lastUserMsg.id));
    handleSend(lastUserMsg.text);
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-6.5rem)] md:h-[calc(100vh-8rem)] min-h-[450px] md:min-h-[600px] max-w-6xl mx-auto select-none relative">
      {/* Sessions Left Sidebar Panel */}
      {!temporary && (
        <>
          {/* Backdrop for mobile drawer overlay */}
          {sessionsOpen && (
            <div
              className="fixed inset-0 z-30 bg-black/60 md:hidden animate-fadeIn"
              onClick={() => setSessionsOpen(false)}
            />
          )}

          <div 
            className={`${
              sessionsOpen 
                ? "fixed inset-y-20 left-4 z-40 w-64 h-[calc(100vh-12rem)] my-auto shadow-2xl flex" 
                : "hidden"
            } md:flex md:relative md:inset-auto md:w-64 md:h-auto bg-zinc-950 border border-zinc-800 rounded-3xl p-4 flex flex-col justify-between shrink-0 select-none transition-all duration-300`}
          >
            <div className="space-y-4 flex-1 flex flex-col min-h-0">
              <button
                onClick={handleNewChat}
                className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-2xl bg-indigo-650 hover:bg-indigo-750 text-white font-bold text-sm shadow-md transition-all duration-200 cursor-pointer active:scale-98 shrink-0"
              >
                <svg className="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                </svg>
                <span>New Chat</span>
              </button>

              <div className="flex-1 overflow-y-auto space-y-2 pr-1 min-h-0">
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest block pl-1">
                  Recent Chats
                </span>
                {sessions.length === 0 ? (
                  <div className="text-zinc-500 text-xs text-center py-8">No chats yet</div>
                ) : (
                  sessions.map((s) => (
                    <div
                      key={s.id}
                      className={`group flex items-center justify-between p-3 rounded-2xl border text-left transition-all duration-200 cursor-pointer text-xs font-bold ${
                        activeSessionId === s.id
                          ? "bg-zinc-900 border-zinc-800 text-zinc-100"
                          : "bg-transparent border-transparent text-zinc-500 hover:bg-zinc-900/40 hover:text-zinc-300"
                      }`}
                      onClick={() => handleSelectSession(s.id)}
                    >
                      <span className="truncate pr-2 flex-1 leading-snug">{s.title}</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteSession(s.id);
                        }}
                        className="p-1 rounded-lg text-zinc-500 hover:text-rose-400 hover:bg-rose-950/20 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer duration-200 shrink-0"
                        title="Delete chat"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Main Chat Interface Panel */}
      <div className="flex-1 flex flex-col justify-between bg-transparent md:bg-white/80 md:dark:bg-zinc-900/80 md:backdrop-blur-xl md:border md:border-zinc-150 md:dark:border-zinc-800 rounded-none md:rounded-3xl p-0 md:p-6 shadow-none md:shadow-xl md:shadow-zinc-100/50 md:dark:shadow-none min-h-0">
        
        {/* Header toolbar */}
        <div className="flex items-center justify-between border-b border-zinc-100 dark:border-zinc-800/80 pb-4 shrink-0">
          <div className="flex items-center gap-3">
            {/* Mobile-only toggle button for chat history sidebar */}
            {!temporary && (
              <button
                type="button"
                onClick={() => setSessionsOpen(!sessionsOpen)}
                className="md:hidden p-2.5 rounded-xl bg-zinc-100 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-800 text-zinc-650 dark:text-zinc-350 cursor-pointer active:scale-95 transition-all select-none"
                title="Chat History"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 6h16M4 12h16M4 18h7" />
                </svg>
              </button>
            )}
            <div className="flex flex-col gap-1.5 text-left">
              <h1 className="text-xl font-black bg-gradient-to-r from-indigo-500 via-violet-400 to-pink-400 bg-clip-text text-transparent">
                {temporary ? "Incognito Chat" : activeSessionId ? "Ask Copilot" : "NiveshIQ Copilot"}
              </h1>
            <p className="text-zinc-500 dark:text-zinc-400 text-xs leading-none">
              {temporary
                ? "Incognito Mode — stateless, zero context to user profiles, nothing saved."
                : "Personalized financial advisor with cross-session memory."}
            </p>
          </div>
        </div>

          {/* Incognito Switcher */}
          <button
            onClick={handleToggleIncognito}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all border cursor-pointer select-none active:scale-98 ${
              temporary
                ? "bg-violet-50 dark:bg-violet-950/30 border-violet-200 dark:border-violet-800/80 text-violet-600 dark:text-violet-400 shadow-sm"
                : "bg-zinc-50 dark:bg-zinc-800/40 border-zinc-200 dark:border-zinc-800 text-zinc-500 dark:text-zinc-450 hover:bg-zinc-100 dark:hover:bg-zinc-800/60"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {temporary ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878l4.242 4.242M15 12a3 3 0 11-6 0m9.878 9.878L21 21" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              )}
            </svg>
            <span>{temporary ? "Incognito On" : "Incognito Off"}</span>
          </button>
        </div>

        {/* Conversation flow messages list */}
        <div className="flex-1 space-y-6 overflow-y-auto max-h-none md:max-h-[500px] my-6 pr-2 scrollbar-thin select-text">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center text-center py-16 space-y-4">
              <div className="w-14 h-14 rounded-3xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center animate-pulse border border-indigo-100 dark:border-indigo-900/30 shadow-md">
                <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <h3 className="text-lg font-bold text-zinc-800 dark:text-zinc-200 tracking-tight">
                {temporary ? "Secret Chats" : "Something On Your Mind "}
              </h3>
              <p className="text-xs text-zinc-500 dark:text-zinc-405 max-w-sm leading-relaxed">
                {temporary ? "Trust me no one will know anything about our conversation, it's just you and me" : "Receive compliance-friendly, evidence-backed advice about weight spreads, watchlist items, or macro events."}
              </p>
            </div>
          ) : (
            messages.map((msg) => {
              // Hide empty copilot bubble above thinking box when first starting streaming content
              if (msg.sender === "copilot" && !msg.text.trim() && !msg.payload) {
                return null;
              }

              return (
                <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"} animate-fadeIn`}>
                  <div className={`max-w-[85%] rounded-3xl px-5 py-4 ${
                    msg.sender === "user" 
                      ? "bg-gradient-to-br from-indigo-600 to-violet-650 text-white rounded-tr-none shadow-md shadow-indigo-150/40"
                      : "bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-100 dark:border-zinc-800 text-zinc-800 dark:text-zinc-200 rounded-tl-none shadow-sm"
                  }`}>
                    {msg.sender === "user" ? (
                      <p className="text-sm leading-relaxed font-medium">{msg.text}</p>
                    ) : (
                      <div className="space-y-4">
                        {/* Markdown answer content */}
                        <div className="prose prose-sm dark:prose-invert prose-headings:text-zinc-800 dark:prose-headings:text-zinc-200 prose-p:text-zinc-700 dark:prose-p:text-zinc-300 prose-strong:text-indigo-650 dark:prose-strong:text-indigo-400 prose-a:text-indigo-600 dark:prose-a:text-indigo-400 prose-table:text-xs max-w-none [&_table]:border-collapse [&_th]:bg-zinc-100 dark:[&_th]:bg-zinc-800 [&_th]:px-3 [&_th]:py-1.5 [&_td]:px-3 [&_td]:py-1.5 [&_th]:border [&_td]:border [&_th]:border-zinc-200 dark:[&_th]:border-zinc-700 [&_td]:border-zinc-200 dark:[&_td]:border-zinc-700 [&_th]:text-left">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.text}
                          </ReactMarkdown>
                        </div>

                        {/* Caveat disclosure */}
                        {msg.payload?.caveat && (
                          <div className="bg-amber-50/50 dark:bg-amber-950/10 border border-amber-250/30 dark:border-amber-900/20 rounded-2xl p-3.5 flex gap-2.5 animate-fadeIn">
                            <svg className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <div className="space-y-0.5">
                              <span className="text-xs font-bold text-amber-800 dark:text-amber-400 block tracking-tight">
                                Compliance Disclosure
                              </span>
                              <span className="text-[11px] text-amber-700/90 dark:text-amber-500/80 leading-normal font-medium block">
                                {msg.payload.caveat}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {/* Thinking Checklist Loader */}
          {isThinking && (
            <div className="flex justify-start animate-fadeIn">
              <div className="bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-100 dark:border-zinc-800 rounded-3xl rounded-tl-none px-5 py-4 flex flex-col gap-2.5 shadow-sm min-w-[220px]">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold tracking-tight text-indigo-500 dark:text-indigo-400">
                    Thinking
                  </span>
                  <span className="flex space-x-1">
                    <span className="w-1.5 h-1.5 bg-indigo-500 dark:bg-indigo-400 rounded-full animate-bounce delay-75"></span>
                    <span className="w-1.5 h-1.5 bg-indigo-500 dark:bg-indigo-400 rounded-full animate-bounce delay-150"></span>
                    <span className="w-1.5 h-1.5 bg-indigo-500 dark:bg-indigo-400 rounded-full animate-bounce delay-300"></span>
                  </span>
                </div>
                {statusSteps.length > 0 && (
                  <div className="flex flex-col gap-1.5 border-t border-zinc-100 dark:border-zinc-700/50 pt-2.5 text-xs text-zinc-600 dark:text-zinc-400 font-medium">
                    {statusSteps.map((step, idx) => (
                      <div key={idx} className="flex items-center gap-2 animate-fadeIn">
                        <span className="text-emerald-500 font-bold">✓</span>
                        <span>{step.replace(/^✓\s*/, "")}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="bg-rose-50/50 dark:bg-rose-950/10 border border-rose-200/50 dark:border-rose-900/30 text-rose-600 dark:text-rose-400 p-4 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-fadeIn shrink-0">
              <div className="flex items-center gap-3">
                <svg className="w-5 h-5 shrink-0 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-xs font-semibold">{error}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0 w-full sm:w-auto justify-end">
                {(error.toLowerCase().includes("token limit") || error.toLowerCase().includes("guest")) ? (
                  <button
                    type="button"
                    onClick={() => loginWithGoogle()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all duration-150 cursor-pointer active:scale-95 shadow-sm"
                  >
                    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                    </svg>
                    <span>Sign Up with Google</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleRetry}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-100 hover:bg-rose-200 dark:bg-rose-950/45 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-350 text-xs font-bold transition-all duration-150 cursor-pointer active:scale-95"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H17" />
                    </svg>
                    <span>Retry</span>
                  </button>
                )}
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-zinc-100 dark:border-zinc-800/80 pt-4 shrink-0">
          {/* Query submit box */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend(query);
            }}
            className="flex items-center gap-2"
          >
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask Copilot"
              disabled={loading}
              className="flex-1 bg-zinc-50 dark:bg-zinc-800/30 hover:bg-zinc-100/50 focus:bg-white dark:hover:bg-zinc-800/50 dark:focus:bg-zinc-900 border border-zinc-200 focus:border-indigo-500 dark:border-zinc-800 dark:focus:border-indigo-500 rounded-2xl px-4 py-3.5 text-sm text-zinc-800 dark:text-zinc-200 focus:ring-1 focus:ring-indigo-500 focus:outline-none transition-all duration-200 font-semibold"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="bg-indigo-650 hover:bg-indigo-750 text-white disabled:bg-zinc-100 disabled:text-zinc-400 dark:disabled:bg-zinc-800/80 dark:disabled:text-zinc-600 px-5 py-3.5 rounded-2xl font-bold text-sm shadow-md transition-all duration-200 active:scale-98 shrink-0 flex items-center gap-1.5 cursor-pointer"
            >
              <span>Ask</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
