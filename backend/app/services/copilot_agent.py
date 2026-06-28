import json
import logging
import uuid
import asyncio
import re
import concurrent.futures
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session

from langchain_core.language_models import BaseChatModel
from app.models.chat import ChatMessage
from app.utils.database import save_chat_to_db, record_chat_token_usage
from app.utils.parsing import extract_text, clean_and_parse_json, extract_token_usage
from app.services.prompts import AGENT_PROMPT, REFACTOR_PROMPT, INVESTMENT_ADVISOR_PROMPT
from app.services.tools import TOOLS

logger = logging.getLogger(__name__)

# ── PRE-BUILT TOOL MAP (avoid rebuilding on every request) ─────────────────
_TOOL_MAP: Dict[str, Any] = {t.name: t for t in TOOLS}


def _get_or_create_session(db: Session, user_id: str, session_id: Optional[str] = None) -> str:
    from app.models.chat import ChatSession
    if session_id:
        sess = db.query(ChatSession).filter(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        ).first()
    else:
        sess = db.query(ChatSession).filter(
            ChatSession.user_id == user_id
        ).order_by(ChatSession.created_at.desc()).first()

    if not sess:
        sess = ChatSession(
            id=session_id or str(uuid.uuid4()),
            user_id=user_id,
            created_at=datetime.now(timezone.utc),
            last_message_at=datetime.now(timezone.utc),
        )
        db.add(sess)
        db.commit()
    else:
        sess.last_message_at = datetime.now(timezone.utc)
        db.commit()
    return sess.id


def _format_history_for_refactor(history: List[Dict[str, str]], max_chars: int = 2000) -> str:
    """Format history as a simple text block for the refactoring prompt."""
    if not history:
        return "No prior turns."

    lines: list[str] = []
    total_chars = 0
    for msg in reversed(history):
        role = (msg.get("role") or "user").upper()
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        line = f"{role}: {content}"
        if total_chars + len(line) > max_chars:
            break
        lines.append(line)
        total_chars += len(line)

    lines.reverse()
    return "\n".join(lines) if lines else "No prior turns."


class ContextManager:
    """Specializes in formatting context blocks and prompt templating.
    History is consumed by the flash-lite refactoring layer _before_ reaching
    the main Flash/Pro model, so the main model always sees a clean, standalone query.
    """

    def __init__(self, agent_prompt: str):
        self.agent_prompt = agent_prompt

    # Cap each tool result at 8000 chars to prevent prompt bloat
    def merge_tool_results(self, tool_results: Dict[str, Any]) -> str:
        blocks = []
        for name, data in tool_results.items():
            serialized = json.dumps(data, indent=2)
            if len(serialized) > 8000:
                serialized = serialized[:8000] + "\n... [truncated for brevity]"
            blocks.append(f"=== TOOL RESULT: {name} ===\n{serialized}")
        return "\n\n".join(blocks)

    def build_prompt(self, refactored_query: str, tool_results: Dict[str, Any], history_str: Optional[str] = None, requires_tools: bool = False, prompt_override: Optional[str] = None) -> str:
        """Build the main agent prompt.

        Uses prompt_override (e.g. INVESTMENT_ADVISOR_PROMPT) if provided,
        otherwise falls back to self.agent_prompt (AGENT_PROMPT).

        For meta-queries (conversation-summary questions), pass history_str
        to give the model the chat history it needs. For normal content queries
        history_str should be None to prevent hallucination.

        When requires_tools=True, injects a hard directive telling the model
        it MUST call tools rather than answering from memory — used when the
        refactor layer detected this query needs live/current data.
        """
        effective_prompt = prompt_override or self.agent_prompt
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        context = self.merge_tool_results(tool_results)

        base = effective_prompt.format(
            current_time=now,
            refactored_query=refactored_query,
            intent="general",
        )

        # Inject hard tool-requirement directive when refactor layer flagged this
        tools_directive = ""
        if requires_tools:
            tools_directive = (
                "\n\n**MANDATORY TOOL USE:** This query was classified as needing current/live data.\n"
                "Your training data is stale for this. You MUST call the relevant tools to fetch\n"
                "up-to-date information before answering. Do NOT answer from memory."
            )

        history_block = ""
        if history_str:
            history_block = f"\n\n=== CHAT HISTORY (for context - answer only the current query) ===\n{history_str}"

        return f"{base}{tools_directive}\n\n=== GATHERED CONTEXT ===\n{context}{history_block}"


class CopilotAgent:
    """LangChain-based copilot agent with a query refactoring layer.

    Pipeline:
      1. Load chat history from DB.
      2. Use flash-lite model to refactor (current query + history) → standalone query.
      3. Pass standalone query (no raw history) into Flash/Pro pipeline for tool routing & answer synthesis.

    This prevents the main model from seeing previous-assistant answers, eliminating
    hallucination where Q2 reproduces Q1's answer.
    """

    def __init__(
        self,
        pro_model: BaseChatModel,
        flash_model: Optional[BaseChatModel] = None,
        flash_lite_model: Optional[BaseChatModel] = None,
        context_manager: Optional[ContextManager] = None,
    ):
        self._pro = pro_model

        # Use flash for tool-routing if provided; fall back to pro
        self._flash = flash_model or pro_model

        # Flash-lite for the cheap refactoring step
        self._flash_lite = flash_lite_model or flash_model or pro_model

        self.context_manager = context_manager or ContextManager(
            agent_prompt=AGENT_PROMPT,
        )

        # Cache bind_tools bindings once — never recreate per request
        self._flash_with_tools = self._flash.bind_tools(TOOLS)
        self._pro_no_tools = self._pro  # plain pro for final synthesis

    # ── QUERY REFACTORING (new layer) ──────────────────────────────────────

    def _refactor_query(self, message: str, history: List[Dict[str, str]]) -> str:
        """Use flash-lite to refactor the query + history into a standalone question.

        Returns the refactored query text.
        If the refactor layer classifies it as a meta/conversation-history query,
        the output starts with "META:" — the caller should detect this prefix
        and conditionally inject raw history into the main model prompt.
        """
        history_str = _format_history_for_refactor(history)
        prompt = REFACTOR_PROMPT.format(history=history_str, message=message)
        try:
            result = self._flash_lite.invoke(prompt)
            refactored = extract_text(result).strip()
            if not refactored:
                logger.warning("Refactoring returned empty, falling back to original query")
                return message
            # Safety: ensure we got a clean question, not meta-commentary
            # Remove any accidental JSON wrapping or markdown fences
            if refactored.startswith("```"):
                refactored = refactored.strip("`").strip()
                if refactored.startswith("json"):
                    refactored = refactored[4:].strip()
            return refactored
        except Exception as e:
            logger.error(f"Query refactoring failed: {e}, falling back to original query")
            return message

    # ── HISTORY ────────────────────────────────────────────────────────────

    def _load_history(self, db: Session, user_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        sess_id = _get_or_create_session(db, user_id, session_id)
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == sess_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(20)
            .all()
        )
        messages.reverse()
        history = [{"role": m.role, "content": m.content} for m in messages if m.content]
        return {"session_id": sess_id, "history": history}

    # ── TOOL EXECUTION ─────────────────────────────────────────────────────

    @staticmethod
    def _run_single_tool(tc: Dict, db: Session, user_id: str) -> tuple:
        """Execute one LangChain tool call and return (name, data)."""
        name = tc.get("name", "")
        args = dict(tc.get("args", {}))

        t_obj = _TOOL_MAP.get(name)
        if not t_obj:
            return (name, {"error": f"Tool '{name}' not found"})
        try:
            kwargs = {**args, "db": db, "user_id": user_id}
            envelope = t_obj.invoke(kwargs)
            if envelope.get("success", False):
                return (name, envelope.get("data", {}))
            else:
                return (name, {"error": envelope.get("data", {}).get("error", "Unknown error")})
        except Exception as e:
            logger.error(f"Tool {name} execution failed: {e}")
            return (name, {"error": str(e)})

    def _execute_tool_calls(self, tool_calls: List[Dict], db: Session, user_id: str) -> Dict[str, Any]:
        """Execute tool calls concurrently via thread pool."""
        # Log which tools are being dispatched
        for tc in tool_calls:
            logger.info(f"DISPATCH tool: {tc.get('name', '?')} args={tc.get('args', {})}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
            futures = {pool.submit(self._run_single_tool, tc, db, user_id): tc for tc in tool_calls}
            results = {}
            for future in concurrent.futures.as_completed(futures):
                name, data = future.result()
                logger.info(f"RESULT tool: {name} success={'error' not in data}")
                results[name] = data
        return results

    async def _execute_tool_calls_async(self, tool_calls: List[Dict], db: Session, user_id: str) -> Dict[str, Any]:
        """Async version of concurrent tool execution."""
        # Log which tools are being dispatched
        for tc in tool_calls:
            logger.info(f"DISPATCH tool: {tc.get('name', '?')} args={tc.get('args', {})}")
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
            futures = {
                loop.run_in_executor(pool, self._run_single_tool, tc, db, user_id): tc
                for tc in tool_calls
            }
            results = {}
            for coro in asyncio.as_completed(futures):
                name, data = await coro
                logger.info(f"RESULT tool: {name} success={'error' not in data}")
                results[name] = data
        return results

    # ── ANSWER GENERATION ──────────────────────────────────────────────────

    def _generate_answer(self, db: Session, user_id: str, message: str, history: List[Dict]) -> Dict[str, Any]:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        try:
            # Step 1: Refactor query into standalone question
            refactored_query = self._refactor_query(message, history)
            logger.info(f"Refactored query: '{message}' → '{refactored_query}'")

            # Detect prefix classifications from the refactor layer
            needs_history = False
            requires_tools = False
            prompt_override = None
            if refactored_query.startswith("META:"):
                refactored_query = refactored_query[5:].strip()
                needs_history = True
            elif refactored_query.startswith("HYBRID:"):
                refactored_query = refactored_query[7:].strip()
                needs_history = True
            elif refactored_query.startswith("TOOLS:"):
                refactored_query = refactored_query[6:].strip()
                requires_tools = True
            elif refactored_query.startswith("ADVISOR:"):
                refactored_query = refactored_query[8:].strip()
                requires_tools = True
                prompt_override = INVESTMENT_ADVISOR_PROMPT
            # For meta/hybrid queries, supply the raw history so the model can 
            # summarize/recap or replicate a previous analysis pattern
            history_for_prompt = _format_history_for_refactor(history) if needs_history else None

            tool_results: Dict[str, Any] = {}
            last_result = None
            max_iterations = 2

            # Step 2: Use cached flash_with_tools for routing pass
            for _ in range(max_iterations):
                prompt = self.context_manager.build_prompt(refactored_query, tool_results, history_for_prompt, requires_tools, prompt_override)
                result = self._flash_with_tools.invoke(prompt)
                usage = extract_token_usage(result)
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                total_tokens += usage.get("total_tokens", 0)

                tool_calls = getattr(result, "tool_calls", [])

                if not tool_calls:
                    # Flash produced a direct answer — use it as final result
                    last_result = result
                    break

                # Tool calls present — execute them and continue
                new_results = self._execute_tool_calls(tool_calls, db, user_id)
                tool_results.update(new_results)
                last_result = None  # loop ended on a tool-call, not a final answer

            # Step 3: Only call Pro if the loop exhausted without a final text answer
            if last_result is None and tool_results:
                prompt = self.context_manager.build_prompt(refactored_query, tool_results, history_for_prompt, requires_tools, prompt_override)
                last_result = self._pro_no_tools.invoke(prompt)
                usage = extract_token_usage(last_result)
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                total_tokens += usage.get("total_tokens", 0)
            elif last_result is None:
                # Edge case: loop hit max_iterations with no tools and no answer
                prompt = self.context_manager.build_prompt(refactored_query, {}, history_for_prompt, requires_tools, prompt_override)
                last_result = self._pro_no_tools.invoke(prompt)
                usage = extract_token_usage(last_result)
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                total_tokens += usage.get("total_tokens", 0)

            raw = extract_text(last_result)
            payload = clean_and_parse_json(raw)

        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            payload = {
                "answer": "I hit a temporary issue while assembling the analysis. Please try again.",
                "evidence": [],
                "next_steps": [],
            }

        payload.setdefault("answer", "")
        payload.setdefault("evidence", [])
        payload.setdefault("next_steps", [])
        payload.setdefault("prompt_tokens", prompt_tokens)
        payload.setdefault("completion_tokens", completion_tokens)
        payload.setdefault("total_tokens", total_tokens)
        return payload

    # ── PERSISTENCE ────────────────────────────────────────────────────────

    def _save_and_persist(self, db: Session, user_id: str, session_id: str, query: str, answer: str) -> None:
        try:
            save_chat_to_db(db, user_id, session_id, query, answer)
        except Exception as e:
            logger.error(f"Failed to persist chat data: {e}")

    # ── PUBLIC API: SYNC ───────────────────────────────────────────────────

    def ask_copilot(
        self,
        db: Session,
        user_id: str,
        query: str,
        temporary: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the full copilot pipeline synchronously."""
        try:
            hist = self._load_history(db, user_id, session_id)
            sid = hist["session_id"]
            payload = self._generate_answer(db, user_id, query, hist["history"])
            if not temporary:
                self._save_and_persist(db, user_id, sid, query, payload["answer"])
                record_chat_token_usage(
                    db, sid,
                    payload.get("prompt_tokens", 0),
                    payload.get("completion_tokens", 0),
                    payload.get("total_tokens", 0),
                )
            return payload
        except Exception as e:
            logger.error(f"Copilot failed: {e}")
            return {
                "answer": "## I hit a temporary issue while assembling the full analysis\n- Try asking the question again in a moment.",
                "evidence": [],
                "next_steps": [],
            }

    # ── PUBLIC API: ASYNC STREAM ───────────────────────────────────────────

    async def ask_copilot_stream(
        self,
        db: Session,
        user_id: str,
        query: str,
        temporary: bool = False,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream the copilot response as SSE events."""
        state = {"tool_results": {}, "full_raw": ""}

        def _send(event_type: str, **data) -> str:
            return f"data: {json.dumps({'type': event_type, **data})}\n\n"

        async def stream_raw_json(model_to_use: Any, prompt_str: str):
            buffer = ""
            state_search = "SEARCHING"
            escaped = False
            prefix_cleaned = False
            streamed_answer_buffer = ""
            full_raw = ""

            async for chunk in model_to_use.astream(prompt_str):
                text = extract_text(chunk, strip=False)
                if not text:
                    continue
                full_raw += text
                buffer += text

                if state_search == "SEARCHING":
                    match = re.search(r'"answer"\s*:\s*"', buffer)
                    if match:
                        state_search = "STREAMING"
                        buffer = buffer[match.end():]

                if state_search == "STREAMING":
                    chunk_out = ""
                    for char in buffer:
                        if state_search == "STREAMING":
                            if escaped:
                                if char == 'n':   chunk_out += '\n'
                                elif char == 't': chunk_out += '\t'
                                elif char == 'r': chunk_out += '\r'
                                elif char == 'b': chunk_out += '\b'
                                elif char == 'f': chunk_out += '\f'
                                elif char == '\\': chunk_out += '\\'
                                elif char == '"':  chunk_out += '"'
                                else:              chunk_out += '\\' + char
                                escaped = False
                            elif char == '\\':
                                escaped = True
                            elif char == '"':
                                state_search = "FINISHED"
                            else:
                                chunk_out += char
                    buffer = ""
                    if chunk_out:
                        if not prefix_cleaned:
                            streamed_answer_buffer += chunk_out
                            if len(streamed_answer_buffer) > 150 or "\n" in streamed_answer_buffer or state_search == "FINISHED":
                                yield streamed_answer_buffer
                                prefix_cleaned = True
                                streamed_answer_buffer = ""
                        else:
                            yield chunk_out

            if not prefix_cleaned and streamed_answer_buffer:
                yield streamed_answer_buffer

            state["full_raw"] = full_raw

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        try:
            hist = self._load_history(db, user_id, session_id)
            sid = hist["session_id"]

            # Step 1: Refactor query into standalone question using flash-lite
            yield _send("status", text="Analyzing your query...")
            refactored_query = self._refactor_query(query, hist["history"])
            logger.info(f"Refactored query: '{query}' → '{refactored_query}'")

            # Detect prefix classifications from the refactor layer
            needs_history = False
            requires_tools = False
            prompt_override = None
            if refactored_query.startswith("META:"):
                refactored_query = refactored_query[5:].strip()
                needs_history = True
            elif refactored_query.startswith("HYBRID:"):
                refactored_query = refactored_query[7:].strip()
                needs_history = True
            elif refactored_query.startswith("TOOLS:"):
                refactored_query = refactored_query[6:].strip()
                requires_tools = True
            elif refactored_query.startswith("ADVISOR:"):
                refactored_query = refactored_query[8:].strip()
                requires_tools = True
                prompt_override = INVESTMENT_ADVISOR_PROMPT
            # For meta/hybrid queries, supply the raw history so the model can 
            # summarize/recap or replicate a previous analysis pattern
            history_for_prompt = _format_history_for_refactor(hist["history"]) if needs_history else None

            # Step 2: Use cached flash_with_tools for routing; Pro only for final stream
            last_result = None
            max_iterations = 2

            for i in range(max_iterations):
                prompt = self.context_manager.build_prompt(refactored_query, state["tool_results"], history_for_prompt, requires_tools, prompt_override)
                result = await self._flash_with_tools.ainvoke(prompt)
                usage = extract_token_usage(result)
                prompt_tokens += usage.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0)
                total_tokens += usage.get("total_tokens", 0)

                tool_calls = getattr(result, "tool_calls", [])

                if not tool_calls:
                    last_result = result
                    break

                yield _send("status", text="Fetching data...")
                new_results = await self._execute_tool_calls_async(tool_calls, db, user_id)
                state["tool_results"].update(new_results)
                last_result = None

            # Step 3: Only invoke Pro for final synthesis when needed
            if last_result is None and state["tool_results"]:
                prompt = self.context_manager.build_prompt(refactored_query, state["tool_results"], history_for_prompt, requires_tools, prompt_override)
                yield _send("status", text="Generating analysis...")
                async for clean_chunk in stream_raw_json(self._pro_no_tools, prompt):
                    yield _send("content", text=clean_chunk)
                payload = clean_and_parse_json(state["full_raw"])
            else:
                # Direct answer from flash (no tools used), or fallback
                if last_result is None:
                    prompt = self.context_manager.build_prompt(refactored_query, {}, history_for_prompt, requires_tools, prompt_override)
                    last_result = await self._pro_no_tools.ainvoke(prompt)
                    usage = extract_token_usage(last_result)
                    prompt_tokens += usage.get("prompt_tokens", 0)
                    completion_tokens += usage.get("completion_tokens", 0)
                    total_tokens += usage.get("total_tokens", 0)
                text = extract_text(last_result)
                payload = clean_and_parse_json(text)
                if payload.get("answer"):
                    yield _send("content", text=payload["answer"])

            payload.setdefault("answer", "")
            payload.setdefault("evidence", [])
            payload.setdefault("next_steps", [])

            if not temporary:
                self._save_and_persist(db, user_id, sid, query, payload["answer"])
                record_chat_token_usage(
                    db, sid,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                )

            yield _send("done", payload=payload)

        except Exception as e:
            logger.error(f"Copilot stream failed: {e}")
            fallback = "I hit a temporary issue while assembling the analysis. Please try again."
            yield _send("content", text=fallback)
            yield _send("done", payload={"answer": fallback})