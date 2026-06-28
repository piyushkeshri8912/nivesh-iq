"use client";

import { useState, useEffect, useRef } from "react";
import { 
  askCopilot, 
  AskResponse, 
  fetchActiveSession, 
  clearChatHistory, 
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
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [statusSteps, setStatusSteps] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [temporary, setTemporary] = useState(false);
  const [showTextareaScrollbar, setShowTextareaScrollbar] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const streamingTextRef = useRef("");
  const targetTextRef = useRef("");
  const typewriterTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setQuery(val);
    
    // Auto grow height
    const textarea = e.target;
    textarea.style.height = "auto";
    const scrollHeight = textarea.scrollHeight;
    textarea.style.height = `${Math.min(scrollHeight, 120)}px`;
    
    // Only show scrollbar when height exceeds max limit (120px)
    setShowTextareaScrollbar(scrollHeight > 120);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        return;
      }
      e.preventDefault();
      handleSend(query);
    }
  };

  useEffect(() => {
    return () => {
      if (typewriterTimeoutRef.current) {
        clearTimeout(typewriterTimeoutRef.current);
      }
    };
  }, []);

  const startTypewriter = (copilotMsgId: string) => {
    if (typewriterTimeoutRef.current) return;

    const tick = () => {
      const currentText = streamingTextRef.current;
      const targetText = targetTextRef.current;

      if (currentText.length < targetText.length) {
        const diff = targetText.length - currentText.length;
        let step = 1;
        if (diff > 120) step = 8;
        else if (diff > 60) step = 4;
        else if (diff > 20) step = 2;

        const nextText = targetText.substring(0, currentText.length + step);
        streamingTextRef.current = nextText;

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === copilotMsgId ? { ...msg, text: nextText } : msg
          )
        );

        typewriterTimeoutRef.current = setTimeout(tick, 10);
      } else {
        typewriterTimeoutRef.current = null;
      }
    };

    tick();
  };

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, isThinking]);

  // Load chat session on mount & when temporary mode toggles
  useEffect(() => {
    if (!temporary) {
      loadActiveSession();
    } else {
      setActiveSessionId(null);
      setMessages([]);
    }
  }, [temporary]);

  const loadActiveSession = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchActiveSession();
      setActiveSessionId(data.session_id);
      setMessages(
        data.messages.map((m) => ({
          id: String(m.id),
          sender: m.role === "user" ? "user" : "copilot",
          text: m.content,
          timestamp: new Date(m.created_at),
        }))
      );
    } catch (err: any) {
      console.error("Failed to load active session:", err);
      setError("Failed to retrieve chat messages. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleClearHistory = async () => {
    if (loading) return;
    if (temporary) {
      setMessages([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const success = await clearChatHistory();
      if (success) {
        setMessages([]);
      } else {
        setError("Failed to clear chat history.");
      }
    } catch (err) {
      console.error("Failed to clear chat history:", err);
      setError("Failed to clear chat history.");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleIncognito = () => {
    if (loading) return;
    setTemporary(!temporary);
  };

  const handleSend = async (textToSend: string) => {
    if (!textToSend.trim() || loading) return;

    setLoading(true);
    setIsThinking(true);
    setError(null);
    setStatusSteps([]);

    streamingTextRef.current = "";
    targetTextRef.current = "";
    if (typewriterTimeoutRef.current) {
      clearTimeout(typewriterTimeoutRef.current);
      typewriterTimeoutRef.current = null;
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
    setShowTextareaScrollbar(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    try {
      const data = await askCopilot(
        textToSend,
        temporary,
        activeSessionId || undefined,
        (chunk) => {
          setIsThinking(false);
          targetTextRef.current += chunk;
          startTypewriter(copilotMsgId);
        },
        (status) => {
          setStatusSteps((prev) => {
            if (prev.includes(status)) return prev;
            return [...prev, status];
          });
        }
      );
      
      targetTextRef.current = data.answer;

      // Wait for typewriter to fully catch up to the target text before resolving
      await new Promise<void>((resolve) => {
        const check = () => {
          if (streamingTextRef.current.length < targetTextRef.current.length) {
            setTimeout(check, 30);
          } else {
            resolve();
          }
        };
        check();
      });

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === copilotMsgId
            ? { ...msg, text: data.answer, payload: data }
            : msg
        )
      );
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
    <div className="flex justify-center h-full w-full select-none relative min-h-0 bg-zinc-950 overflow-hidden text-zinc-150">
      {/* Main Chat Interface Panel centered */}
      <div className="w-full max-w-4xl flex-1 flex flex-col justify-between pt-1 pb-4 px-3 md:pt-4 md:pb-6 md:px-8 min-h-0 h-full relative">
        
        {/* Header toolbar */}
        <div className="flex items-center justify-between pb-3  shrink-0">
          <div className="flex items-center gap-3">
            {/* Trash/Clear History Icon Button */}
            <button
              type="button"
              onClick={handleClearHistory}
              className="p-2.5 rounded-xl bg-zinc-900 border border-zinc-850 text-zinc-400 hover:text-rose-450 hover:bg-rose-950/20 hover:border-rose-900/30 cursor-pointer active:scale-95 transition-all select-none flex items-center justify-center"
              title="Clear chat history"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>

          {/* Incognito Switcher */}
          <button
            onClick={handleToggleIncognito}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-bold transition-all border cursor-pointer select-none active:scale-98 ${
              temporary
                ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-400 shadow-sm"
                : "bg-zinc-800/40 border-zinc-800 text-zinc-400 hover:bg-zinc-800/60"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {temporary ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878l4.242 4.242M15 12a3 3 0 11-6 0m9.878 9.878L21 21" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              )}
            </svg>
          </button>
        </div>

        {/* Conversation flow messages list */}
        <div className="flex-1 space-y-6 overflow-y-auto px-1 pr-2 select-text min-h-0 py-4 custom-scrollbar">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center text-center py-16 space-y-4">
              <div className="w-14 h-14 rounded-3xl bg-indigo-950/40 text-indigo-400 flex items-center justify-center animate-pulse border border-indigo-900/30 shadow-md">
                <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <h3 className="text-lg font-bold text-zinc-200 tracking-tight">
                {temporary ? "Temporary Chat" : "Ask NiveshIQ Copilot"}
              </h3>
              <p className="text-xs text-zinc-400 max-w-sm leading-relaxed">
                {temporary 
                  ? "The chat history will not be saved" : "Inquire about market trends, discuss portfolio news, or any other query."}
              </p>
            </div>
          ) : (
            messages.map((msg) => {
              if (msg.sender === "copilot" && !msg.text.trim() && !msg.payload) {
                return null;
              }

              return (
                <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"} animate-fadeIn w-full`}>
                  <div className={`${
                    msg.sender === "user" 
                      ? "max-w-[85%] md:max-w-[75%] px-4 py-3 bg-indigo-600 text-white rounded-2xl rounded-tr-none shadow-md shadow-indigo-650/10 font-medium"
                      : "w-full max-w-full pl-4 pr-12 md:pl-6 md:pr-20 py-2 bg-transparent text-zinc-200 border-0 shadow-none"
                  }`}>
                    {msg.sender === "user" ? (
                      <p className="text-xs sm:text-sm leading-relaxed font-semibold whitespace-pre-wrap">{msg.text}</p>
                    ) : (
                      <div className="space-y-4">
                        {/* Markdown answer content */}
                        <div className="prose prose-sm prose-invert prose-headings:text-zinc-150 prose-p:text-zinc-300 prose-strong:text-indigo-400 prose-a:text-indigo-400 prose-table:text-xs max-w-none [&_table]:border-collapse [&_th]:bg-zinc-950 [&_th]:px-3 [&_th]:py-1.5 [&_td]:px-3 [&_td]:py-1.5 [&_th]:border [&_td]:border [&_th]:border-zinc-850 [&_td]:border-zinc-850 [&_th]:text-left">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.text}
                          </ReactMarkdown>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {/* Thinking Checklist Loader */}
          {isThinking && (
            <div className="flex justify-start animate-fadeIn w-full">
              <div className="bg-transparent border-0 rounded-none px-0 py-2 flex flex-col gap-2.5 shadow-none min-w-[220px]">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold tracking-tight text-indigo-400">
                    Thinking
                  </span>
                  <span className="flex space-x-1">
                    <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce delay-75"></span>
                    <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce delay-150"></span>
                    <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce delay-300"></span>
                  </span>
                </div>
                {statusSteps.length > 0 && (
                  <div className="flex flex-col gap-1.5 border-t border-zinc-850 pt-2.5 text-xs text-zinc-400 font-medium">
                    {statusSteps.map((step, idx) => (
                      <div key={idx} className="flex items-center gap-2 animate-fadeIn">
                        <svg className="w-3.5 h-3.5 text-emerald-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
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
            <div className="bg-rose-500/5 border border-rose-500/15 text-rose-400 p-4 rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-fadeIn shrink-0">
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
                    className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition-all duration-150 cursor-pointer active:scale-95 shadow-md border border-indigo-500/20 mx-auto"
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
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-450 text-xs font-bold transition-all duration-150 cursor-pointer active:scale-95 border border-rose-500/20"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H17" />
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
        <div className="border-t border-zinc-800/80 pt-4 shrink-0">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend(query);
            }}
            className="flex items-end gap-2"
          >
            <textarea
              ref={textareaRef}
              rows={1}
              value={query}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask Copilot..."
              disabled={loading}
              className={`flex-1 bg-zinc-950 border border-zinc-850 hover:border-zinc-700/60 focus:border-indigo-500/50 rounded-xl px-4 py-3.5 text-xs sm:text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none transition-all duration-200 font-semibold resize-none max-h-[120px] min-h-[46px] ${showTextareaScrollbar ? "overflow-y-auto" : "overflow-y-hidden"}`}
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="bg-indigo-650 hover:bg-indigo-550 text-white disabled:bg-zinc-800/85 disabled:text-zinc-650 px-5 py-3 rounded-xl font-heading font-bold text-xs uppercase tracking-wider shadow-md transition-all duration-200 active:scale-98 shrink-0 flex items-center gap-1.5 cursor-pointer"
            >
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
