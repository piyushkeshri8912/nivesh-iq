"use client";

import { useState, useEffect, useRef } from "react";
import { 
  askCopilot, 
  AskResponse, 
  fetchActiveSession, 
  clearChatHistory 
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
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [statusSteps, setStatusSteps] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [temporary, setTemporary] = useState(false);
  const [width, setWidth] = useState(384); // Default width: 384px
  const [showTextareaScrollbar, setShowTextareaScrollbar] = useState(false);
  const isResizing = useRef(false);

  const startResizing = (mouseDownEvent: React.MouseEvent) => {
    mouseDownEvent.preventDefault();
    isResizing.current = true;

    const startX = mouseDownEvent.clientX;
    const startWidth = width;

    const doDrag = (mouseMoveEvent: MouseEvent) => {
      if (!isResizing.current) return;
      const deltaX = startX - mouseMoveEvent.clientX;
      const maxWidth = typeof window !== "undefined" ? window.innerWidth / 2 : 1000;
      const newWidth = Math.min(maxWidth, Math.max(384, startWidth + deltaX));
      setWidth(newWidth);
    };

    const doTouchDrag = (touchMoveEvent: TouchEvent) => {
      if (!isResizing.current) return;
      const deltaX = startX - touchMoveEvent.touches[0].clientX;
      const maxWidth = typeof window !== "undefined" ? window.innerWidth / 2 : 1000;
      const newWidth = Math.min(maxWidth, Math.max(384, startWidth + deltaX));
      setWidth(newWidth);
    };

    const stopDrag = () => {
      isResizing.current = false;
      document.removeEventListener("mousemove", doDrag);
      document.removeEventListener("mouseup", stopDrag);
      document.removeEventListener("touchmove", doTouchDrag);
      document.removeEventListener("touchend", stopDrag);
    };

    document.addEventListener("mousemove", doDrag);
    document.addEventListener("mouseup", stopDrag);
    document.addEventListener("touchmove", doTouchDrag);
    document.addEventListener("touchend", stopDrag);
  };
  
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
    textarea.style.height = `${Math.min(scrollHeight, 100)}px`;

    // Only show scrollbar when height exceeds max limit (100px)
    setShowTextareaScrollbar(scrollHeight > 100);
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
        let step = 5;
        if (diff > 120) step = 10;
        else if (diff > 60) step = 6;
        else if (diff > 20) step = 4;

        const nextText = targetText.substring(0, currentText.length + step);
        streamingTextRef.current = nextText;

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === copilotMsgId ? { ...msg, text: nextText } : msg
          )
        );

        typewriterTimeoutRef.current = setTimeout(tick, 30);
      } else {
        typewriterTimeoutRef.current = null;
      }
    };

    tick();
  };



  // Auto-scroll to bottom of chat when messages update
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, isThinking]);

  // Focus input on drawer open
  useEffect(() => {
    if (isOpen && textareaRef.current) {
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 300);
    }
  }, [isOpen]);

  // Load chat session when drawer opens or when temporary mode toggles
  useEffect(() => {
    if (isOpen) {
      if (!temporary) {
        loadActiveSession();
      } else {
        setActiveSessionId(null);
        setMessages([]);
      }
    }
  }, [isOpen, temporary]);

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
      console.error("Failed to clear history:", err);
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
      {/* Backdrop (mobile only) */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-zinc-950/45 md:hidden transition-opacity duration-300"
        />
      )}

      {/* Slide-out Panel container */}
      <div
        style={{
          width: typeof window !== "undefined" && window.innerWidth >= 768
            ? (isOpen ? `${width}px` : "0px")
            : undefined
        }}
        className={`fixed top-0 right-0 h-full z-50 bg-zinc-950 md:relative md:top-auto md:right-auto md:z-30 md:pt-16 md:transition-all md:duration-300 md:ease-in-out flex flex-col select-none overflow-hidden ${
          isOpen 
            ? "translate-x-0 w-full max-w-full sm:w-96 border-l border-zinc-850" 
            : "translate-x-full md:translate-x-0 w-0 border-l-0"
        }`}
      >
        {/* Stable width wrapper to prevent squishing and reflow during opening transition */}
        <div 
          style={{ width: typeof window !== "undefined" && window.innerWidth >= 768 ? `${width}px` : "100%" }}
          className="h-full flex flex-col min-w-[384px] md:min-w-0"
        >
          {/* Resize handle (Desktop only) */}
          <div
            onMouseDown={startResizing}
            className="hidden md:block absolute top-0 bottom-0 left-0 w-1.5 hover:w-2.5 cursor-ew-resize bg-zinc-850/40 hover:bg-indigo-500/50 transition-all z-50"
          />

          {/* Drawer Header */}
          <div className="px-4 h-14 flex items-center justify-between  bg-zinc-950 shrink-0 select-none relative z-50">
            {/* Leftside controls */}
            <div className="flex items-center gap-2">
              {/* Trash/Clear History Icon Button */}
              <button
                type="button"
                onClick={handleClearHistory}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-rose-450 hover:bg-rose-950/20 transition-colors cursor-pointer flex items-center justify-center"
                title="Clear chat history"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>

            {/* Rightside controls */}
            <div className="flex items-center gap-2">
              {/* Incognito icon switcher */}
              <button
                type="button"
                onClick={handleToggleIncognito}
                className={`p-1.5 rounded-lg transition-colors cursor-pointer flex items-center justify-center ${
                  temporary
                    ? "text-indigo-400 bg-indigo-950/40 border border-indigo-850/50"
                    : "text-zinc-400 hover:text-white hover:bg-zinc-900"
                }`}
                title={temporary ? "Incognito On" : "Incognito Off"}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {temporary ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  )}
                </svg>
              </button>

              {/* Cross icon */}
              <button
                type="button"
                onClick={onClose}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors cursor-pointer flex items-center justify-center"
                title="Close Chat"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>


          {/* Messages List Area */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4 select-text custom-scrollbar">
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
                      {temporary ? "Temporary mode" : "Ask NiveshIQ Copilot" }
                    </h5>
                    <p className="text-[11px] text-zinc-550 max-w-[200px] mx-auto mt-1 leading-normal">
                      {temporary ? "The chat history will not be saved" : "Inquire about market trends, discuss portfolio news, or any other query."}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              messages.map((msg) => {
                if (msg.sender === "copilot" && !msg.text.trim() && !msg.payload) {
                  return null;
                }

                return (
                  <div key={msg.id} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"} animate-fadeIn`}>
                    <div className={`${
                      msg.sender === "user" 
                        ? "max-w-[85%] md:max-w-[75%] px-4 py-3 bg-indigo-600 text-white rounded-2xl rounded-tr-none shadow-md shadow-indigo-650/10 font-medium"
                        : "w-full max-w-full pl-4 pr-12 md:pl-6 md:pr-16 py-2 bg-transparent text-zinc-200 border-0 shadow-none"
                    }`}>
                      {msg.sender === "user" ? (
                        <p className="leading-relaxed font-semibold whitespace-pre-wrap text-xs sm:text-sm">{msg.text}</p>
                      ) : (
                        <div className="space-y-3">
                          {/* Markdown-Rendered Main Answer */}
                          <div className="prose prose-xs dark:prose-invert prose-p:text-zinc-300 prose-strong:text-indigo-400 prose-a:text-indigo-400 prose-headings:text-zinc-200 prose-table:text-[10px] max-w-none [&_table]:border-collapse [&_th]:bg-zinc-800 [&_th]:px-2 [&_th]:py-1 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_td]:border [&_th]:border-zinc-700 [&_td]:border-zinc-700 [&_th]:text-left [&_p]:text-xs [&_li]:text-xs [&_h2]:text-sm [&_h3]:text-xs">
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

            {/* Typing Indicator with Progress Checklist */}
            {isThinking && (
              <div className="flex justify-start animate-fadeIn w-full">
                <div className="bg-transparent border-0 rounded-none px-0 py-2 flex flex-col gap-2.5 shadow-none w-full max-w-[260px]">
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
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-950/30 hover:bg-rose-900/40 text-rose-350 text-[10px] font-bold border border-rose-900/50 transition-colors cursor-pointer active:scale-95 shrink-0"
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

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend(query);
              }}
              className="flex items-end gap-1.5"
            >
              <textarea
                ref={textareaRef}
                rows={1}
                value={query}
                onChange={handleTextareaChange}
                onKeyDown={handleKeyDown}
                placeholder="Ask Copilot..."
                disabled={loading}
                className={`flex-1 bg-zinc-900 border border-zinc-800 focus:border-indigo-650 focus:outline-none rounded-xl px-3.5 py-2.5 text-xs text-zinc-200 focus:ring-1 focus:ring-indigo-650/40 transition-all font-semibold resize-none max-h-[100px] min-h-[38px] ${showTextareaScrollbar ? "overflow-y-auto" : "overflow-y-hidden"}`}
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
      </div>
    </>
  );
}
