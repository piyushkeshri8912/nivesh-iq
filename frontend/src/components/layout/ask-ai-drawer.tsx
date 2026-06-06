"use client";

import { useState, useEffect, useRef } from "react";
import { 
  askCopilot, 
  AskResponse, 
  fetchChatSessions, 
  createChatSession, 
  fetchSessionMessages, 
  deleteChatSession, 
  ChatSessionResponse 
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

interface AskAIDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function AskAIDrawer({ isOpen, onClose }: AskAIDrawerProps) {
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
  
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const starterPrompts = [
    { text: "Am I too concentrated?", label: "Concentration Check" },
    { text: "What should I do with ₹10,000 this month?", label: "Investment Strategy" },
    { text: "Which watchlist stock fits my profile best?", label: "Watchlist Match" },
    { text: "What is my biggest risk right now?", label: "Risk Exposure" },
  ];

  // Auto-scroll to bottom of chat when messages update
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, isThinking]);

  // Focus input on drawer open
  useEffect(() => {
    if (isOpen && inputRef.current) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 300);
    }
  }, [isOpen]);

  // Load chat sessions when drawer opens or when temporary mode toggles
  useEffect(() => {
    if (isOpen && !temporary) {
      loadSessionsAndSelectRecent();
    }
  }, [isOpen, temporary]);

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
  };

  const handleNewChat = () => {
    if (loading) return;
    setActiveSessionId(null);
    setMessages([]);
    setError(null);
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
      setPreviousSessionId(activeSessionId);
      setActiveSessionId(null);
      setMessages([]);
      setTemporary(true);
    } else {
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

      // Refresh sessions list
      if (!temporary) {
        const list = await fetchChatSessions();
        setSessions(list);
      }
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to retrieve copilot response. Please try again later.");
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
    <>
      {/* Backdrop backdrop-blur */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-zinc-950/40 backdrop-blur-sm transition-opacity duration-300"
        />
      )}

      {/* Slide-out Panel container */}
      <div
        className={`fixed top-0 right-0 h-full w-96 max-w-full z-50 bg-zinc-950/95 border-l border-zinc-800/80 shadow-2xl flex flex-col transition-transform duration-300 ease-in-out select-none ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Drawer Header */}
        <div className="px-5 h-16 flex items-center justify-between border-b border-zinc-800/60 shrink-0">
          <div className="flex items-center gap-2 text-left">
            <span className="flex h-2 w-2 rounded-full bg-indigo-500 animate-ping"></span>
            <div>
              <h4 className="text-sm font-extrabold text-zinc-100  tracking-wider leading-none">
                {temporary ? "Incognito Chat" : "NiveshIQ Copilot"}
              </h4>
              <span className="text-[10px] text-zinc-500 mt-1 block">
                {temporary ? "Your Private AI Buddy" : "Your Smart AI Buddy"}
                </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* New Chat & Delete Session buttons */}
            {!temporary && (
              <div className="flex items-center gap-1 border-r border-zinc-800 pr-2 mr-1">
                <button
                  onClick={handleNewChat}
                  disabled={loading}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors cursor-pointer disabled:opacity-50"
                  title="New Chat"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                  </svg>
                </button>
                {activeSessionId && (
                  <button
                    onClick={() => handleDeleteSession(activeSessionId)}
                    disabled={loading}
                    className="p-1.5 rounded-lg text-zinc-400 hover:text-rose-400 hover:bg-rose-950/20 transition-colors cursor-pointer disabled:opacity-50"
                    title="Delete current chat"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}
              </div>
            )}

            {/* Temporary Chat Toggle */}
            <button
              onClick={handleToggleIncognito}
              className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
                temporary
                  ? "text-violet-400 bg-violet-950/30 border border-violet-800/50"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900"
              }`}
              title={temporary ? "Incognito On — no memories saved" : "Incognito Off — memories active"}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {temporary ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878l4.242 4.242M15 12a3 3 0 11-6 0m9.878 9.878L21 21" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                )}
              </svg>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors cursor-pointer"
              aria-label="Close chat drawer"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Temporary Mode Indicator */}
        {temporary && (
          <div className="px-5 py-2 bg-violet-950/20 border-b border-violet-900/30 flex items-center gap-2">
            <svg className="w-3 h-3 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243" />
            </svg>
            <span className="text-[10px] font-bold text-violet-400 uppercase tracking-widest">Incognito — No memories saved</span>
          </div>
        )}

        {/* Messages List Area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 select-text">
          {messages.length === 0 ? (
            <div className="flex flex-col justify-center space-y-6 h-full py-6">
              <div className="flex flex-col items-center justify-center text-center space-y-3 shrink-0">
                <div className="w-12 h-12 rounded-2xl bg-indigo-950/40 text-indigo-400 flex items-center justify-center animate-pulse border border-indigo-900/30">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
                </div>
                <div>
                  <h5 className="text-sm font-bold text-zinc-200 tracking-tight">
                    {temporary ? "Secret Chats" : "Something On Your Mind?" }
                  </h5>
                  <p className="text-[11px] text-zinc-500 max-w-[200px] mx-auto mt-1 leading-normal">
                    {temporary ? "Trust me, No one will know anything about our conversation, it's just between you and me" : "Inquire about weight spreads, watchlist returns, or sector trends dynamically."}
                  </p>
                </div>
              </div>

              {/* Recent chats list inside drawer when empty */}
              {!temporary && sessions.length > 0 && (
                <div className="space-y-2 max-h-[180px] overflow-y-auto pr-1">
                  <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest block pl-0.5 text-left">
                    Recent Chats
                  </span>
                  <div className="space-y-1.5">
                    {sessions.slice(0, 5).map((s) => (
                      <div
                        key={s.id}
                        onClick={() => handleSelectSession(s.id)}
                        className={`group flex items-center justify-between p-2.5 rounded-xl border text-left cursor-pointer text-[11px] font-bold transition-all ${
                          activeSessionId === s.id
                            ? "bg-zinc-900 border-zinc-800 text-zinc-100"
                            : "bg-zinc-900/40 border-transparent text-zinc-400 hover:bg-zinc-900 hover:text-zinc-250"
                        }`}
                      >
                        <span className="truncate pr-2 flex-1 leading-snug">{s.title}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSession(s.id);
                          }}
                          className="p-1 rounded text-zinc-500 hover:text-rose-400 hover:bg-rose-950/20 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer duration-200 shrink-0"
                          title="Delete chat"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            messages.map((msg) => {
              // Hide empty copilot bubble above thinking box when first starting streaming content
              if (msg.sender === "copilot" && !msg.text.trim() && !msg.payload) {
                return null;
              }

              return (
                <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"} animate-fadeIn`}>
                  <div className={`max-w-[90%] rounded-2xl px-4 py-3.5 text-xs ${
                    msg.sender === "user" 
                      ? "bg-gradient-to-br from-indigo-650 to-violet-600 text-white rounded-tr-none shadow-md shadow-indigo-900/10"
                      : "bg-zinc-900/70 border border-zinc-800 text-zinc-200 rounded-tl-none shadow-sm"
                  }`}>
                    {msg.sender === "user" ? (
                      <p className="leading-relaxed font-semibold">{msg.text}</p>
                    ) : (
                      <div className="space-y-3">
                        {/* Markdown-Rendered Main Answer */}
                        <div className="prose prose-xs dark:prose-invert prose-p:text-zinc-300 prose-strong:text-indigo-400 prose-a:text-indigo-400 prose-headings:text-zinc-200 prose-table:text-[10px] max-w-none [&_table]:border-collapse [&_th]:bg-zinc-800 [&_th]:px-2 [&_th]:py-1 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_td]:border [&_th]:border-zinc-700 [&_td]:border-zinc-700 [&_th]:text-left [&_p]:text-xs [&_li]:text-xs [&_h2]:text-sm [&_h3]:text-xs">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.text}
                          </ReactMarkdown>
                        </div>

                        {/* Disclaimer caveat */}
                        {msg.payload?.caveat && (
                          <div className="bg-amber-950/10 border border-amber-900/20 rounded-xl p-2.5 flex gap-2">
                            <svg className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <div className="space-y-0.5">
                              <span className="text-[10px] font-bold text-amber-400 block tracking-tight">
                                Compliance Note
                              </span>
                              <span className="text-[9px] text-amber-500/80 leading-normal font-semibold block">
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

          {/* Typing Indicator with Progress Checklist */}
          {isThinking && (
            <div className="flex justify-start animate-fadeIn w-full">
              <div className="bg-zinc-900/75 border border-zinc-800/80 rounded-2xl rounded-tl-none px-4 py-3 flex flex-col gap-2 shadow-md w-full max-w-[260px]">
                <div className="flex items-center space-x-1.5">
                  <span className="text-[10px] font-bold tracking-tight text-indigo-400">
                    Thinking
                  </span>
                  <span className="flex space-x-0.5">
                    <span className="w-1 h-1 bg-indigo-500 rounded-full animate-bounce delay-75"></span>
                    <span className="w-1 h-1 bg-indigo-500 rounded-full animate-bounce delay-150"></span>
                    <span className="w-1 h-1 bg-indigo-500 rounded-full animate-bounce delay-300"></span>
                  </span>
                </div>
                {statusSteps.length > 0 && (
                  <div className="flex flex-col gap-1 border-t border-zinc-800/60 pt-2 text-[10px] text-zinc-400 font-medium">
                    {statusSteps.map((step, idx) => (
                      <div key={idx} className="flex items-center gap-1.5 animate-fadeIn">
                        <span className="text-emerald-500 font-bold">✓</span>
                        <span>{step.replace(/^✓\s*/, "")}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Error notice */}
          {error && (
            <div className="bg-rose-950/15 border border-rose-900/30 text-rose-400 p-3 rounded-xl flex items-center justify-between gap-2 text-[10px] font-semibold w-full animate-fadeIn shrink-0">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{error}</span>
              </div>
              <button
                type="button"
                onClick={handleRetry}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-950/30 hover:bg-rose-900/40 text-rose-300 text-[10px] font-bold border border-rose-900/50 transition-colors cursor-pointer active:scale-95 shrink-0"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H17" />
                </svg>
                <span>Retry</span>
              </button>
            </div>
          )}
          
          <div ref={chatEndRef} />
        </div>

        {/* Input area */}
        <div className="p-4 border-t border-zinc-800/60 bg-zinc-950 shrink-0">
          {messages.length === 0 && !temporary && (
            <div className="mb-4 space-y-1.5">
              <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest block pl-0.5 text-left">
                Suggested Starters
              </span>
              <div className="grid grid-cols-1 gap-1.5">
                {starterPrompts.map((prompt, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(prompt.text)}
                    disabled={loading}
                    className="w-full text-left p-2.5 rounded-xl bg-zinc-900 hover:bg-zinc-850 border border-zinc-800/80 hover:border-zinc-700/80 text-zinc-350 hover:text-indigo-400 text-[10px] font-bold transition-all flex justify-between items-center cursor-pointer active:scale-[0.99]"
                  >
                    <span>{prompt.text}</span>
                    <svg className="w-3 h-3 text-zinc-555 group-hover:text-indigo-400 ml-1.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend(query);
            }}
            className="flex items-center gap-1.5"
          >
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask Copilot..."
              disabled={loading}
              className="flex-1 bg-zinc-900 border border-zinc-800 focus:border-indigo-650 focus:outline-none rounded-xl px-3.5 py-2.5 text-xs text-zinc-200 focus:ring-1 focus:ring-indigo-650/40 transition-all font-semibold"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="p-2.5 bg-indigo-600 hover:bg-indigo-750 text-white rounded-xl disabled:bg-zinc-900 disabled:text-zinc-600 transition-colors flex items-center justify-center cursor-pointer shrink-0"
              aria-label="Send query"
            >
              <svg className="w-3.5 h-3.5 " fill="currentColor" viewBox="0 0 24 24">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
