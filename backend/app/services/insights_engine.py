import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, TypedDict, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException
from langgraph.graph import StateGraph, START, END

from app.core.config import settings
from app.models.portfolio_review import PortfolioReview
from app.models.user_profile import UserProfile
from app.models.watchlist_item import WatchlistItem
from app.models.user import User
from app.models.transaction import Transaction
from app.models.user_memory import UserMemory
from app.services.holdings_service import holdings_service
from app.services.portfolio_history_service import portfolio_history_service
from app.services.market_data_service import market_data_service
from app.services.news_service import news_service
from app.analytics.exposure import (
    calculate_market_cap_exposure,
    calculate_sector_exposure,
    get_market_cap_bucket,
)

logger = logging.getLogger(__name__)

# LangGraph State definition
class ReviewState(TypedDict):
    db: Session
    user_id: str
    profile: Dict[str, Any]
    holdings: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    news: List[Dict[str, Any]]
    condensed_signals: str
    watchlist: List[Dict[str, Any]]
    draft_insights: Dict[str, Any]
    final_report: Dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class CopilotState(TypedDict, total=False):
    db: Session
    user_id: str
    session_id: str
    message: str
    temporary: bool
    history: List[Dict[str, str]]
    intent: Optional[str]
    required_context: List[str]
    relevant_symbols: List[str]
    max_holdings: int
    max_news_per_symbol: int
    user_profile: Optional[Dict[str, Any]]
    portfolio_snapshot: Optional[Dict[str, Any]]
    market_data: Optional[Dict[str, Any]]
    news_context: Optional[Dict[str, Any]]
    retrieved_memory: Optional[List[Dict[str, str]]]
    plan_draft: Optional[Dict[str, Any]]
    final_answer: Optional[str]
    final_response: Optional[Dict[str, Any]]
    tool_calls: Optional[List[Dict[str, Any]]]
    web_search_results: Optional[List[Dict[str, Any]]]
    calculator_results: Optional[Dict[str, Any]]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class InsightsEngine:
    def __init__(self):
        self.flash_lite_model = None
        self.flash_model = None
        self.pro_model = None
        self.embeddings_model = None
        self._chat_sessions: Dict[str, Dict[str, Any]] = {}
        self._init_models()
        self.copilot_graph = self._build_copilot_graph()

    def _init_models(self):
        """
        Initialize Google Vertex AI Chat models and Embeddings model.
        Low level tasks map to gemini-2.5-flash-lite. Tool-calling copilot uses gemini-2.5-flash.
        High level strategist reasoning uses gemini-2.5-pro.
        Embeddings use text-embedding-004 (768 dimensions) for memory storage and retrieval.
        """
        try:
            from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
            
            # Flash Lite tier for classifications and low-level parsing
            self.flash_lite_model = ChatVertexAI(
                model_name=getattr(settings, "VERTEX_FLASH_LITE_MODEL", "gemini-2.5-flash-lite"),
                project=settings.VERTEX_PROJECT_ID,
                location=settings.VERTEX_LOCATION,
                temperature=0.2,
                max_output_tokens=4096
            )
            # Flash tier for tool-calling copilot
            self.flash_model = ChatVertexAI(
                model_name=getattr(settings, "VERTEX_FLASH_MODEL", "gemini-2.5-flash"),
                project=settings.VERTEX_PROJECT_ID,
                location=settings.VERTEX_LOCATION,
                temperature=0.2,
                max_output_tokens=4096
            )
            
            # High level strategist reasoning
            self.pro_model = ChatVertexAI(
                model_name=getattr(settings, "VERTEX_PRO_MODEL", "gemini-2.5-pro"),
                project=settings.VERTEX_PROJECT_ID,
                location=settings.VERTEX_LOCATION,
                temperature=0.1,
                max_output_tokens=4096
            )
            
            # Vertex AI Embeddings for pgvector memory storage/retrieval
            self.embeddings_model = VertexAIEmbeddings(
                model_name=getattr(settings, "VERTEX_EMBEDDINGS_MODEL", "text-embedding-004"),
                project=settings.VERTEX_PROJECT_ID,
                location=settings.VERTEX_LOCATION,
            )
            
            logger.info("Successfully initialized Vertex AI (Chat + Embeddings)")
        except Exception as e:
            raise RuntimeError(
                f"Vertex AI model initialization failed: {e}"
            ) from e

    def _extract_token_usage(self, result) -> Dict[str, int]:
        """
        Safely extract prompt_tokens, completion_tokens, and total_tokens from any model response.
        Handles various key mappings across different LangChain/VertexAI versions.
        """
        usage = getattr(result, "response_metadata", {}).get("usage_metadata") or {}
        if not usage and isinstance(result, dict):
            usage = result.get("usage_metadata") or {}
            
        prompt = usage.get("prompt_tokens") or usage.get("prompt_token_count") or 0
        completion = (
            usage.get("completion_tokens") or 
            usage.get("candidates_tokens") or 
            usage.get("candidates_token_count") or 
            usage.get("output_tokens") or 
            0
        )
        total = usage.get("total_tokens") or usage.get("total_token_count") or (prompt + completion)
        
        return {
            "prompt_tokens": int(prompt),
            "completion_tokens": int(completion),
            "total_tokens": int(total)
        }

    def _record_chat_token_usage(self, db: Session, session_id: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        try:
            from app.models.chat import ChatSession
            db_session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if db_session:
                db_session.prompt_tokens = (db_session.prompt_tokens or 0) + prompt_tokens
                db_session.completion_tokens = (db_session.completion_tokens or 0) + completion_tokens
                db_session.total_tokens = (db_session.total_tokens or 0) + total_tokens
                db.commit()
                logger.info(f"Recorded {total_tokens} tokens for chat session {session_id}")
        except Exception as e:
            logger.error(f"Failed to record chat token usage: {e}")
            db.rollback()


    # ── Cross-Session pgvector Memory System ──────────────────────────────

    def _classify_memory_relevance(self, user_text: str) -> bool:
        """
        Step 1 of two-step memory extraction.
        Uses gemini-2.5-flash-lite to classify whether the user message contains
        storable information (goals, preferences, constraints, life events, philosophy).
        Returns True if the message has extractable memory-worthy content.
        """
        classify_prompt = f"""You are a classification agent. Analyze the following user message and determine if it contains ANY personally meaningful information worth remembering for future financial advice.

        Memory-worthy information includes:
        - Investment goals (e.g., "I want to retire by 50", "saving for a house", "investing for children's education")
        - Risk preferences (e.g., "I have high risk tolerance", "I prefer safe investments", "I have moderate risk appetite")
        - Financial constraints/budgets (e.g., "I can invest ₹1 lakh per month", "I have ₹50,000 to invest", "I have a budget of 1 lakh")
        - Life events (e.g., "I just had a baby", "I'm getting married next year")
        - Investment philosophy (e.g., "I believe in value investing", "I prefer technology sector")
        - Personal context (e.g., "I am 32 years old", "I live in Bangalore", "I am a student")

        NOT memory-worthy:
        - General market questions (e.g., "What is Nifty today?")
        - Portfolio queries (e.g., "Show my holdings", "What is my return?")
        - Stock lookups (e.g., "What is TCS price?")
        - Generic finance questions (e.g., "What is SIP?")

        USER MESSAGE:
        \"\"\"{user_text}\"\"\"

        Respond with ONLY one word: STORE or DISCARD"""
        try:
            result = self.flash_lite_model.invoke(classify_prompt)
            logger.info("FLASH LITE TOKEN USAGE:", getattr(result, "response_metadata", {}).get("usage_metadata"))
            classification = self._extract_text(result).strip().upper()
            return "STORE" in classification
        except Exception as e:
            logger.error(f"Memory classification failed: {e}")
            return False

    def extract_and_store_memory(self, db: Session, user_id: str, user_text: str) -> None:
        """
        Step 2 of two-step memory extraction.

        - Classify relevance.
        - Extract structured facts via LLM.
        - Soft-deduplicate by semantic similarity (pgvector cosine distance).
        - Store only genuinely new facts.
        """
        if not self._classify_memory_relevance(user_text):
            logger.info("Memory classification: DISCARD (no facts to store)")
            return

        logger.info("Memory classification: STORE (extracting facts...)")

        extract_prompt = f"""
        You are a fact extraction agent for a financial advisory AI.
        Extract all personally meaningful facts from the user message below.

        For each fact, output:
        - "type": one of ["goal", "preference", "constraint", "life_event", "philosophy", "personal_context"]
        - "text": a concise, standalone sentence capturing the fact

        Rules:
        - Each fact must be self-contained (understandable without the original message)
        - Do not extract general questions or market queries
        - Merge redundant facts
        - Output ONLY a valid JSON array

        USER MESSAGE:
        \"\"\"{user_text}\"\"\"

        Output JSON array:
        [{{
        "type": "goal",
        "text": "Wants to retire by age 50"
        }}]
        """.strip()

        try:
            result = self.flash_lite_model.invoke(extract_prompt)
            logger.info("FLASH LITE TOKEN USAGE:", getattr(result, "response_metadata", {}).get("usage_metadata"))
            raw = self._extract_text(result)
            facts = self._clean_and_parse_json(raw)

            if not isinstance(facts, list) or not facts:
                logger.info("Memory extraction: No facts extracted")
                return

            # Normalize facts and tolerate alternate keys like "fact" or "value"
            normalized_facts = []
            for f in facts:
                if not isinstance(f, dict):
                    continue
                text_val = (f.get("text") or f.get("fact") or f.get("value") or "").strip()
                if text_val:
                    f["text"] = text_val
                    normalized_facts.append(f)

            if not normalized_facts:
                logger.info("Memory extraction: No non-empty fact texts")
                return

            # Embed candidate facts once
            candidate_texts = [f["text"] for f in normalized_facts]
            candidate_embeddings = self.embeddings_model.embed_documents(candidate_texts)

            # Check semantic duplication using pgvector cosine distance
            new_facts: list[dict[str, Any]] = []
            for fact, emb in zip(normalized_facts, candidate_embeddings):
                fact_text = fact["text"]

                # Query for any very similar existing memory
                existing = (
                    db.query(UserMemory)
                    .filter(UserMemory.user_id == user_id)
                    .order_by(UserMemory.embedding.cosine_distance(emb))
                    .limit(1)
                    .all()
                )

                if existing and existing[0].embedding.cosine_distance(emb) < 0.15:
                    # Semantically duplicate → skip
                    continue

                new_facts.append((fact, emb))

            if not new_facts:
                logger.info("Memory extraction: All facts are semantically similar to existing memories (skipping)")
                return

            for fact, embedding_vector in new_facts:
                memory = UserMemory(
                    user_id=user_id,
                    type=fact.get("type", "preference"),
                    text=fact["text"].strip(),
                    embedding=embedding_vector,
                )
                db.add(memory)

            db.commit()
            logger.info(f"Memory extraction: Stored {len(new_facts)} new facts")

        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.error(f"Memory extraction rollback failed: {rollback_err}")

    def retrieve_relevant_memories(self, db: Session, user_id: str, query: str, top_k: int = 5) -> List[Dict[str, str]]:
        """
        Retrieve the top-K most relevant memories for a user query using
        pgvector cosine distance similarity search directly in PostgreSQL.
        """
        try:
            # Embed the query
            query_embedding = self.embeddings_model.embed_query(query)

            # SQL cosine similarity search using pgvector operators
            results = (
                db.query(UserMemory)
                .filter(UserMemory.user_id == user_id)
                .order_by(UserMemory.embedding.cosine_distance(query_embedding))
                .limit(top_k)
                .all()
            )

            memories = []
            for mem in results:
                memories.append({
                    "type": mem.type,
                    "text": mem.text,
                })

            logger.info(f"Memory retrieval: Found {len(memories)} relevant memories")
            return memories

        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.error(f"Memory retrieval rollback failed: {rollback_err}")
            return []
    
    def _extract_text(self, result) -> str:
        """
        Safely extract text from model responses regardless of model tier.
        """
        try:
            content = getattr(result, "content", result)
            if isinstance(content, list):
                return "".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ).strip()
            if isinstance(content, dict):
                return content.get("text", str(content)).strip()
            return str(content).strip()
        except Exception:
            return ""

    def _clean_and_parse_json(self, raw_text: str) -> Any:
        """
        Safely clean and deserialize JSON content from the raw text, 
        stripping markdown code blocks (```json ... ```) and extra surrounding text if present.
        """
        cleaned = raw_text.strip()
        if not cleaned:
            return {}
        
        # Proactively find the first JSON array or object
        first_bracket = cleaned.find('[')
        last_bracket = cleaned.rfind(']')
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            candidate = cleaned[first_bracket:last_bracket+1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        first_brace = cleaned.find('{')
        last_brace = cleaned.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidate = cleaned[first_brace:last_brace+1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        # If no JSON structures are present, avoid throwing JSONDecodeError on plain text
        if first_bracket == -1 and first_brace == -1:
            if cleaned.lower() in {"true", "false", "null"} or cleaned.isdigit():
                try:
                    return json.loads(cleaned)
                except Exception:
                    pass
            return {}

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n|```$", "", cleaned, flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return {}


    def _get_strategist_prompt_and_model(self, intent: str, state: Dict[str, Any]):
        if intent == "DIRECT":
            prompt = f"""
            You are NiveshIQ, a professional portfolio analyst copilot.
            Answer the user's general query, greeting, thank you, or basic financial concept question directly.
            Provide a helpful, educational, premium, and concise explanation in clean Markdown.
            
            Do NOT start your response with phrases like "Based on our previous conversation...".
            Always use double newlines (\\n\\n) to separate paragraphs.
            Use subtle, natural emojis and icons where appropriate (e.g. 📊, 💡, 🎯, 📈).
            
            Return ONLY valid JSON with this schema:
            {{
              "answer": "Markdown-formatted direct answer.",
              "caveat": "One short compliance caveat.",
              "evidence": [],
              "next_steps": [],
              "plan_draft": {{
                "intent": "DIRECT",
                "summary": "Direct response to greeting or educational query.",
                "risk_flags": []
              }}
            }}
            
            USER QUERY:
            {state["message"]}
            """
            model = self.flash_model
        else:
            prompt = f"""
            You are NiveshIQ, a professional portfolio analyst copilot.
            Give directional but non-prescriptive guidance. Use suitability, scenarios, trade-offs, and risk language instead of direct BUY/SELL orders.
            Consider the user's profile, current portfolio, market/macro context, relevant news, retrieved memory, web search, calculator math, and the recent chat history.

            CRITICAL NEGATIVE CONSTRAINTS:
            - DO NOT start your response with phrases like "Based on our previous conversation about...", "As mentioned earlier...", "Following our earlier discussion...", or similar repetitive introductory statements referencing prior turns. Dive directly into the current analysis or answer the user's query naturally.
            - Always use double newlines (\\n\\n) to separate paragraphs and list items. Do not use single line breaks (\\n) for paragraph spacing.
            - Use subtle, natural emojis and icons in your response (e.g. 📊, 💡, 🎯, ⚠️, 📈, 📉) to make the conversation feel engaging, premium, and natural.

            Return ONLY valid JSON with this schema:
            {{
              "answer": "Markdown-formatted answer.",
              "caveat": "One short compliance caveat.",
              "evidence": ["flat evidence bullet", "another evidence bullet"],
              "next_steps": ["actionable next step", "another next step"],
              "plan_draft": {{
                "intent": "{intent}",
                "summary": "One paragraph internal summary of the recommendation.",
                "risk_flags": ["flag1", "flag2"]
              }}
            }}

            USER MESSAGE:
            {state["message"]}

            RECENT HISTORY:
            {self._format_history_for_prompt(state.get("history", []))}

            USER PROFILE:
            {json.dumps(state.get("user_profile") or {}, indent=2)}

            PORTFOLIO SNAPSHOT:
            {json.dumps(state.get("portfolio_snapshot") or {}, indent=2)}

            MARKET DATA:
            {json.dumps(state.get("market_data") or {}, indent=2)}

            NEWS CONTEXT:
            {json.dumps(state.get("news_context") or {}, indent=2)}

            RETRIEVED MEMORY:
            {json.dumps(state.get("retrieved_memory") or [], indent=2)}

            WEB SEARCH RESULTS:
            {json.dumps(state.get("web_search_results") or [], indent=2)}

            CALCULATOR RESULTS:
            {json.dumps(state.get("calculator_results") or {}, indent=2)}
            """
            model = self.pro_model if intent in {"invest_plan", "portfolio_review", "what_if"} else self.flash_model
            
        return prompt, model

    def _build_copilot_graph(self):
        workflow = StateGraph(CopilotState)

        workflow.add_node("load_history", self.load_history_node)
        workflow.add_node("router", self.router_node)
        workflow.add_node("context_orchestrator", self.context_orchestrator_node)
        workflow.add_node("strategist", self.strategist_node)
        workflow.add_node("compliance", self.compliance_node)
        workflow.add_node("save_and_reply", self.save_and_reply_node)

        workflow.add_edge(START, "load_history")
        workflow.add_edge("load_history", "router")
        workflow.add_edge("router", "context_orchestrator")
        workflow.add_edge("context_orchestrator", "strategist")
        workflow.add_edge("strategist", "compliance")
        workflow.add_edge("compliance", "save_and_reply")
        workflow.add_edge("save_and_reply", END)

        return workflow.compile()

    def _ensure_runtime_session( self, db: Session, user_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Ensure a chat session exists in the database and return a lightweight dict view.

        This replaces in-memory _chat_sessions to be multi-worker-safe and persistent.
        """
        cache_key = session_id or f"default::{user_id}"

        # Optional: small in-memory cache to reduce DB hits, with simple TTL if desired
        session_meta = self._chat_sessions.get(cache_key)

        if session_meta is None:
            from app.models.chat import ChatSession  # adjust import path

            if session_id:
                db_session = (
                    db.query(ChatSession)
                    .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
                    .first()
                )
            else:
                db_session = (
                    db.query(ChatSession)
                    .filter(ChatSession.user_id == user_id)
                    .order_by(ChatSession.created_at.desc())
                    .first()
                )

            if db_session is None:
                db_session = ChatSession(
                    id=session_id or str(uuid.uuid4()),
                    user_id=user_id,
                    created_at=datetime.now(timezone.utc),
                    last_message_at=datetime.now(timezone.utc),
                )
                db.add(db_session)
                db.commit()

            session_meta = {
                "session_id": db_session.id,
                "user_id": db_session.user_id,
                "created_at": db_session.created_at,
                "last_message_at": db_session.last_message_at,
            }
            self._chat_sessions[cache_key] = session_meta

        # Always bump last_message_at in DB
        from app.models.chat import ChatSession  # adjust import path
        db_session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_meta["session_id"])
            .first()
        )
        if db_session:
            db_session.last_message_at = datetime.now(timezone.utc)
            db.commit()

        session_meta["last_message_at"] = db_session.last_message_at if db_session else datetime.now(
            timezone.utc
        )
        return session_meta


    def _format_history_for_prompt( self, history: List[Dict[str, str]], limit: int = 6, max_chars: int = 4000) -> str:
        """
        Format recent history for inclusion into prompts.

        - Validates role/content keys.
        - Trims by number of turns and total characters to avoid token blow-ups.
        """
        if not history:
            return "No prior turns in this active session."

        trimmed = history[-limit:]

        lines: list[str] = []
        total_chars = 0

        for msg in trimmed:
            role = (msg.get("role") or "user").upper()
            content = (msg.get("content") or "").strip()
            if not content:
                continue

            line = f"{role}: {content}"
            if total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        if not lines:
            return "No prior turns in this active session."

        return "\n".join(lines)

    def _default_caveat(self) -> str:
        return (
            "This response is for educational purposes only and does not constitute "
            "personalized investment advice. Please consult a SEBI-registered "
            "investment adviser before making decisions."
        )

    def _soften_investment_language(self, text: str) -> str:
        if not text:
            return ""

        softened = text
        softened = re.sub(r"\bbuy\b", "consider accumulating", softened, flags=re.IGNORECASE)
        softened = re.sub(r"\bsell\b", "consider trimming or rebalancing", softened, flags=re.IGNORECASE)
        softened = re.sub(r"\bstrong buy\b", "potentially attractive for further review", softened, flags=re.IGNORECASE)
        softened = re.sub(r"\bmust invest\b", "could review allocations for", softened, flags=re.IGNORECASE)
        softened = re.sub(r"\bguaranteed\b", "not guaranteed", softened, flags=re.IGNORECASE)
        softened = re.sub(r"\bsure-shot\b", "higher-conviction but still uncertain", softened, flags=re.IGNORECASE)
        return softened

    def _clean_response_prefix(self, text: str) -> str:
        if not text:
            return ""
        pattern = r"^\s*(Based on our (previous|earlier) (conversation|discussion|chat|messages?)( about [^,\.\n]+)?[,\.\s]*|Following up on our (previous|earlier) (conversation|discussion|chat|messages?)[,\.\s]*|As (mentioned|discussed) (earlier|previously)[,\.\s]*|Following our (previous|earlier) discussion[,\.\s]*)\s*"
        cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE)
        if cleaned and cleaned[0].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned

    def _ddg_web_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                return [
                    {
                        "title": r.get("title", ""),
                        "summary": r.get("body", ""),
                        "url": r.get("href", "")
                    }
                    for r in results
                ]
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []

    def _evaluate_math(self, expression: str) -> str:
        try:
            clean = re.sub(r"[^0-9\+\-\*\/\(\)\.\s]", "", expression)
            if not clean.strip() or "__" in clean:
                return "Error: unsafe expression"
            val = eval(clean, {"__builtins__": {}})
            return str(val)
        except Exception as e:
            return f"Error: {e}"

    def calculator(self, expression: str) -> str:
        """
        Safe evaluation of mathematical and financial arithmetic expressions.
        """
        return self._evaluate_math(expression)

    def _execute_tool(self, tool_name: str, args: Dict[str, Any], db: Session, user_id: str) -> Dict[str, Any]:
        """
        Executes a single tool dynamically based on tool name and returns its state updates.
        """
        try:
            if tool_name == "get_portfolio":
                snapshot = self._load_portfolio_snapshot(db, user_id)
                return {"portfolio_snapshot": snapshot}

            elif tool_name == "get_user_profile":
                profile = self._load_user_profile(db, user_id)
                profile_memories = self.retrieve_relevant_memories(
                    db, user_id, "user risk profile investment preferences budget time horizon", top_k=5
                )
                if profile_memories:
                    profile["memory_notes"] = [item["text"] for item in profile_memories]
                return {"user_profile": profile}

            elif tool_name == "search_memory":
                query = args.get("query", "")
                memories = self.retrieve_relevant_memories(db, user_id, query, top_k=8)
                return {"retrieved_memory": memories}

            elif tool_name == "get_market_data":
                symbol = args.get("symbol", "").upper().strip()
                if not symbol:
                    return {"market_data": {}}
                if "." not in symbol:
                    symbol = f"{symbol}.NS"
                market_data = self._fetch_market_macro_snapshot([symbol])
                return {"market_data": market_data}

            elif tool_name == "search_news":
                query = args.get("query", "")
                news = news_service.search_news(query, max_results=8)
                return {"news_context": {"news_items": news, "query": query}}

            elif tool_name == "get_portfolio_news":
                snapshot = self._load_portfolio_snapshot(db, user_id)
                watchlist_symbols = [
                    row.symbol
                    for row in db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
                ]
                news_context = self._build_news_context(
                    snapshot,
                    watchlist_symbols,
                    max_news_per_symbol=2
                )
                return {"news_context": news_context}

            elif tool_name == "web_search":
                query = args.get("query", "")
                results = self._ddg_web_search(query)
                return {"web_search_results": results}

            elif tool_name == "calculator":
                expression = args.get("expression", "")
                result = self.calculator(expression)
                return {"calculator_results": {"expression": expression, "result": result}}

        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name} with args {args}: {e}")
            return {f"{tool_name}_error": str(e)}

        return {}

    def _build_portfolio_stub(self, db: Session, user_id: str) -> Dict[str, Any]:
        holdings_res = holdings_service.calculate_holdings(db, user_id)
        top_holdings = [
            {
                "symbol": holding.symbol,
                "allocation_percent": round(holding.allocation_percent, 2),
            }
            for holding in holdings_res.holdings[:5]
        ]

        watchlist_symbols = [
            row.symbol
            for row in db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
        ]

        return {
            "portfolio_value": round(holdings_res.summary.total_value, 2),
            "portfolio_cost": round(holdings_res.summary.total_cost, 2),
            "top_holdings": top_holdings,
            "watchlist_symbols": watchlist_symbols[:8],
        }

    def _normalize_route_plan(self, plan: Dict[str, Any], temporary: bool) -> Dict[str, Any]:
        topic = (plan.get("primary_topic") or "").upper()
        intent_map = {
            "PORTFOLIO": "portfolio_review",
            "STOCK": "stock_question",
            "WATCHLIST": "stock_question",
            "MARKET_SENTIMENT": "news_impact",
            "MACRO_ECONOMY": "macro_fact",
            "POLICY_SEBI_RBI": "education",
            "TRADING_CONCEPT": "education",
            "GENERAL_FINANCE": "education",
        }
        intent = intent_map.get(topic, "education")

        required_context: List[str] = []
        if plan.get("needs_portfolio_context"):
            required_context.append("portfolio")
        if plan.get("needs_market_snapshot"):
            required_context.append("macro")
        if plan.get("needs_macro_snapshot"):
            required_context.append("macro")
        if plan.get("needs_news"):
            required_context.append("news")
        if not temporary:
            required_context.append("memory")

        if intent in {"invest_plan", "portfolio_review", "stock_question", "what_if"}:
            required_context.append("profile")
        if intent == "invest_plan":
            required_context.append("portfolio")
        if intent == "stock_question":
            required_context.extend(["portfolio", "news", "macro"])

        normalized = {
            "intent": intent,
            "required_context": list(dict.fromkeys(required_context)),
            "relevant_symbols": plan.get("relevant_symbols", []) or [],
            "max_holdings": max(3, min(int(plan.get("max_holdings", 5) or 5), 8)),
            "max_news_per_symbol": max(1, min(int(plan.get("max_news_per_symbol", 2) or 2), 3)),
        }
        return normalized

    def _heuristic_route_context(
        self,
        query: str,
        temporary: bool,
        portfolio_stub: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        q = query.lower()
        intent = "education"

        if any(token in q for token in ["what if", "if i add", "if i invest", "if i sell", "scenario"]):
            intent = "what_if"
        elif any(token in q for token in ["plan", "allocate", "allocation", "invest ", "sip", "1 lakh", "100000"]):
            intent = "invest_plan"
        elif any(token in q for token in ["portfolio review", "rebalance", "rebalancing", "concentrated", "my portfolio", "my holdings", "allocation"]):
            intent = "portfolio_review"
        elif any(token in q for token in ["latest news", "headline", "news impact", "sentiment", "market scenario"]):
            intent = "news_impact"
        elif any(token in q for token in ["inflation", "repo", "rbi", "sebi", "gdp", "crude", "usd", "macro"]):
            intent = "macro_fact"
        elif any(token in q for token in ["stock", "ticker", ".ns", ".bo", "share price"]):
            intent = "stock_question"

        required_context: List[str] = []
        if intent in {"invest_plan", "portfolio_review", "what_if", "stock_question"}:
            required_context.extend(["profile", "portfolio"])
        if intent in {"stock_question", "news_impact"}:
            required_context.extend(["news", "macro"])
        if intent == "macro_fact":
            required_context.append("macro")
        if not temporary:
            required_context.append("memory")

        normalized = {
            "intent": intent,
            "required_context": list(dict.fromkeys(required_context)),
            "relevant_symbols": self._extract_relevant_symbols(
                query,
                portfolio_snapshot=portfolio_stub,
                watchlist_data=None,
            ),
            "max_holdings": 5,
            "max_news_per_symbol": 2,
        }
        return normalized

    def _load_user_profile(self, db: Session, user_id: str) -> Dict[str, Any]:
        profile_obj = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        profile_data = {
            "full_name": getattr(profile_obj, "full_name", None),
            "profession": getattr(profile_obj, "profession", None),
            "risk_appetite": getattr(profile_obj, "risk_appetite", None),
            "time_horizon": getattr(profile_obj, "time_horizon", None),
            "investment_goal": getattr(profile_obj, "investment_goal", None),
            "monthly_investment_budget": getattr(profile_obj, "monthly_investment_budget", None),
        }

        missing_fields = [
            field
            for field in ["risk_appetite", "time_horizon", "investment_goal", "monthly_investment_budget"]
            if not profile_data.get(field)
        ]
        profile_data["missing_fields"] = missing_fields
        return profile_data

    def _load_portfolio_snapshot(self, db: Session, user_id: str, max_holdings: int = 5) -> Dict[str, Any]:
        holdings_res = holdings_service.calculate_holdings(db, user_id)
        top_holdings_raw = holdings_res.holdings[:max_holdings]

        # Batch sector lookup to avoid N+1 calls
        symbols = [h.symbol for h in top_holdings_raw]
        try:
            sectors_by_symbol = market_data_service.get_sectors_bulk(symbols)
        except Exception as e:
            logger.error(f"Bulk sector fetch failed, falling back to per-symbol: {e}")
            sectors_by_symbol = {}

        top_holdings: list[Dict[str, Any]] = []
        sector_labels: set[str] = set()
        concentration_warnings: list[str] = []

        for holding in top_holdings_raw:
            sector = sectors_by_symbol.get(holding.symbol)
            if sector is None:
                try:
                    sector = market_data_service.get_sector(holding.symbol)
                except Exception as e:
                    logger.error(f"Sector fetch failed for {holding.symbol}: {e}")
                    sector = "Unknown"

            sector_labels.add(sector)

            top_holdings.append(
                {
                    "symbol": holding.symbol,
                    "company_name": holding.company_name,
                    "quantity": round(holding.quantity, 4),
                    "average_buy_price": round(holding.average_buy_price, 2),
                    "market_price": round(holding.market_price, 2),
                    "market_value": round(holding.market_value, 2),
                    "allocation_percent": round(holding.allocation_percent, 2),
                    "unrealized_pnl": round(holding.unrealized_pnl, 2),
                    "sector": sector,
                }
            )
            if holding.allocation_percent > 20:
                concentration_warnings.append(
                    f"{holding.symbol} is {holding.allocation_percent:.1f}% of the portfolio."
                )

        watchlist_rows = db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
        watchlist_symbols = [row.symbol for row in watchlist_rows]
        watchlist_prices = market_data_service.get_prices_bulk(watchlist_symbols)
        watchlist = [
            {
                "symbol": row.symbol,
                "company_name": row.company_name or row.symbol,
                "return_since_added": round(row.calculate_return(watchlist_prices.get(row.symbol, 100.0)), 2),
            }
            for row in watchlist_rows
        ]

        try:
            history_summary = portfolio_history_service.get_historical_summary(db, user_id)
        except Exception as e:
            logger.error(f"History summary fetch failed: {e}")
            history_summary = None

        return {
            "summary": holdings_res.summary.model_dump(),
            "top_holdings": top_holdings,
            "holdings_count": len(holdings_res.holdings),
            "top_tickers": [holding["symbol"] for holding in top_holdings],
            "sectors": sorted(sector_labels),
            "watchlist": watchlist,
            "watchlist_symbols": [row["symbol"] for row in watchlist],
            "sector_exposure": calculate_sector_exposure(db, user_id),
            "market_cap_exposure": calculate_market_cap_exposure(db, user_id),
            "history_summary": history_summary,
            "warnings": concentration_warnings,
        }

    def _extract_relevant_symbols(
        self,
        query: str,
        portfolio_snapshot: Optional[Dict[str, Any]],
        watchlist_data: Optional[List[Dict[str, Any]]],
    ) -> List[str]:
        symbols: List[str] = []
        seen = set()

        def add_symbol(symbol: Optional[str]):
            if not symbol:
                return
            normalized = symbol.upper().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                symbols.append(normalized)

        for token in re.findall(r"\b[A-Z]{2,10}(?:\.(?:NS|BO))?\b", query.upper()):
            add_symbol(token)

        lookup_rows: List[Dict[str, Any]] = []
        if portfolio_snapshot:
            lookup_rows.extend(portfolio_snapshot.get("top_holdings", []))
            lookup_rows.extend(portfolio_snapshot.get("watchlist", []))
        if watchlist_data:
            lookup_rows.extend(watchlist_data)

        query_lower = query.lower()
        for row in lookup_rows:
            symbol = row.get("symbol")
            company_name = (row.get("company_name") or "").lower()
            bare_symbol = (symbol or "").split(".")[0].lower()
            if company_name and company_name in query_lower:
                add_symbol(symbol)
            elif bare_symbol and re.search(rf"\b{re.escape(bare_symbol)}\b", query_lower):
                add_symbol(symbol)

        return symbols[:5]

    def _fetch_market_macro_snapshot(self, relevant_symbols: List[str]) -> Dict[str, Any]:
        macro_map = {
            "NIFTY_50": "^NSEI",
            "SENSEX": "^BSESN",
            "BANK_NIFTY": "^NSEBANK",
            "USDINR": "USDINR=X",
            "CRUDE_OIL": "CL=F",
            "GOLD": "GC=F",
        }
        macro_prices = market_data_service.get_prices_bulk(list(macro_map.values()))
        macro = {
            label: {
                "symbol": ticker,
                "price": round(macro_prices.get(ticker, 0.0), 2),
            }
            for label, ticker in macro_map.items()
        }

        instruments = {}
        for symbol in relevant_symbols[:5]:
            instruments[symbol] = {
                "symbol": symbol,
                "company_name": market_data_service.get_company_name(symbol),
                "sector": market_data_service.get_sector(symbol),
                "market_cap": market_data_service.get_market_cap(symbol),
                "price": round(market_data_service.get_price(symbol), 2),
            }

        return {
            "macro": macro,
            "instruments": instruments,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def _build_news_context( self, portfolio_snapshot: Optional[Dict[str, Any]], relevant_symbols: List[str], max_news_per_symbol: int) -> Dict[str, Any]:
        symbols_map: Dict[str, str] = {}

        if portfolio_snapshot:
            holdings_by_symbol = {
                row["symbol"]: row.get("company_name") or row["symbol"]
                for row in portfolio_snapshot.get("top_holdings", [])
            }
            watchlist_by_symbol = {
                row["symbol"]: row.get("company_name") or row["symbol"]
                for row in portfolio_snapshot.get("watchlist", [])
            }
            symbols_map.update(holdings_by_symbol)
            symbols_map.update(watchlist_by_symbol)

        if relevant_symbols:
            for symbol in relevant_symbols:
                symbols_map[symbol] = symbols_map.get(symbol) or market_data_service.get_company_name(symbol)

        # Prefer symbols mentioned explicitly in the query (relevant_symbols) first
        ordered_symbols: list[str] = []
        for s in relevant_symbols:
            if s in symbols_map and s not in ordered_symbols:
                ordered_symbols.append(s)
        for s in symbols_map:
            if s not in ordered_symbols:
                ordered_symbols.append(s)

        limited_map = {s: symbols_map[s] for s in ordered_symbols[:5]}
        if not limited_map:
            return {
                "items": [],
                "summary": "No recent news signals or macro indicators available.",
            }

        try:
            # Ideally, news_service should have its own timeout internally
            bulk_news = news_service.fetch_news_bulk(limited_map)
        except Exception as e:
            logger.error(f"News fetch failed: {e}")
            return {
                "items": [],
                "summary": "News service is temporarily unavailable. Using portfolio and macro context only.",
            }

        items: list[Dict[str, Any]] = []
        for symbol, articles in bulk_news.items():
            for article in articles[:max_news_per_symbol]:
                items.append(
                    {
                        "symbol": symbol,
                        "title": article.get("title", ""),
                        "link": article.get("link", ""),
                        "source": article.get("source", ""),
                        "published_at": article.get("published_at", ""),
                    }
                )

        items.sort(key=lambda item: item.get("published_at") or "", reverse=True)

        summary = "No recent news signals or macro indicators available."
        if items:
            try:
                # Make news_filter optional / defensive
                if hasattr(self, "news_filter") and callable(getattr(self, "news_filter")):
                    summary = self.news_filter({"news": items})
                else:
                    summary = "Recent news items fetched for relevant symbols."
            except Exception as e:
                logger.error(f"News summary generation failed: {e}")
                summary = "Recent news items fetched for relevant symbols."

        return {
            "items": items,
            "summary": summary,
        }

    def load_history_node(self, state: CopilotState) -> Dict[str, Any]:
        if state.get("temporary", False):
            return {"history": []}
        db = state["db"]
        user_id = state["user_id"]
        session_id = state.get("session_id")

        session_meta = self._ensure_runtime_session(db, user_id, session_id)
        effective_session_id = session_meta["session_id"]

        from app.models.chat import ChatMessage  # adjust import path

        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == effective_session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(40)  # load more, will trim per prompt later
            .all()
        )

        history = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.content
        ]

        return {
            "session_id": effective_session_id,
            "history": history,
        }

    def router_node(self, state: CopilotState) -> Dict[str, Any]:
        message = state["message"]
        
        # 1. Classify retrieval necessity (DIRECT, MEMORY, PORTFOLIO, TOOLS)
        routing_prompt = f"""
        Analyze the user's latest query and classify it into exactly one category:
        
        - DIRECT: General greetings, thank yous, small talk, and basic financial concepts/educational questions that can be answered immediately using general knowledge with NO database lookup, profile lookup, portfolio holdings, news, or external tool search needed (e.g. "hello", "hi", "thanks", "who are you", "what can you do", "explain mutual funds", "what is CAGR", "what is diversification").
        - MEMORY: Questions asking specifically about the user's own profile, preferences, budget, or past chat facts (e.g. "what is my risk appetite", "how much can I invest", "what is my budget", "what did I tell you earlier").
        - PORTFOLIO: Questions asking about the user's active holdings, asset allocations, portfolio-level analysis, or portfolio diversification/risk reviews (e.g. "review my portfolio", "am I too concentrated", "am I diversified", "show my holdings").
        - TOOLS: Financial analysis queries requiring recent market data, stock pricing updates, calculator calculations, macroeconomic updates, or web search comparison/explanations (e.g. "why did Nvidia fall today", "latest AI news", "compare Zerodha and Groww", "USDINR rate", "calculate standard deviation of 10, 20").
        
        USER QUERY:
        "{message}"
        
        Return ONLY one word: DIRECT, MEMORY, PORTFOLIO, or TOOLS.
        """
        total_p = 0
        total_c = 0
        total_t = 0
        try:
            route_res = self.flash_lite_model.invoke(routing_prompt)
            logger.info("FLASH LITE TOKEN USAGE:", getattr(route_res, "response_metadata", {}).get("usage_metadata"))
            tokens = self._extract_token_usage(route_res)
            total_p += tokens["prompt_tokens"]
            total_c += tokens["completion_tokens"]
            total_t += tokens["total_tokens"]
            route_category = self._extract_text(route_res).strip().upper()
            route_category = re.sub(r"[^A-Z]", "", route_category)
            if route_category not in ["DIRECT", "MEMORY", "PORTFOLIO", "TOOLS"]:
                route_category = "TOOLS"  # Safe default fallback
        except Exception as e:
            logger.error(f"Router category classification failed: {e}")
            route_category = "TOOLS"
            
        logger.info(f"Retrieval Necessity Router classified category: {route_category}")
        
        # 2. If category is TOOLS, call the LLM planner to select specific tool calls
        tool_calls = []
        if route_category == "TOOLS":
            tools_description = """
            - tool: search_news
              args: {"query": string}
              description: Search for general market events, sector updates, macroeconomic news, or specific stock news using a custom search query string (e.g. "rbi interest rate decisions markets", "tata motors earnings release").
            
            - tool: get_market_data
              args: {"symbol": string}
              description: Returns latest price, company name, sector, and market cap for a specific stock ticker symbol (e.g. "TCS.NS", "RELIANCE.NS", "NVDA"). Resolves plain tickers (e.g. "TCS") to their full symbols.
            
            - tool: web_search
              args: {"query": string}
              description: Perform general internet searches for non-news queries, such as comparisons between brokers, educational finance definitions, or general business concepts (e.g. "Zerodha vs Groww comparison", "what is standard deviation in portfolio risk").
            
            - tool: calculator
              args: {"expression": string}
              description: Evaluate mathematical expressions safely. Use for portfolio return calculations, percentage changes, or compound interest formulas.
            """
            planner_prompt = f"""
            You are NiveshIQ's routing and planning assistant.
            Select the most appropriate tools from the toolset below to answer the user query. You can select multiple tools if needed.
            
            AVAILABLE TOOLS:
            {tools_description}
            
            Return ONLY valid JSON with this schema:
            {{
              "tool_calls": [
                {{
                  "tool": "tool_name",
                  "args": {{"arg_name": "value"}}
                }}
              ]
            }}
            
            USER MESSAGE:
            {message}
            
            RECENT HISTORY:
            {self._format_history_for_prompt(state.get("history", []), limit=5)}
            """
            try:
                plan_res = self.flash_model.invoke(planner_prompt)
                logger.info("FLASH TOKEN USAGE:", getattr(plan_res, "response_metadata", {}).get("usage_metadata"))
                tokens = self._extract_token_usage(plan_res)
                total_p += tokens["prompt_tokens"]
                total_c += tokens["completion_tokens"]
                total_t += tokens["total_tokens"]
                plan_raw = self._extract_text(plan_res)
                plan_parsed = self._clean_and_parse_json(plan_raw)
                if isinstance(plan_parsed, dict):
                    tool_calls = plan_parsed.get("tool_calls", [])
                elif isinstance(plan_parsed, list):
                    tool_calls = plan_parsed
                else:
                    tool_calls = []
            except Exception as e:
                logger.error(f"Tool planner failed: {e}")
                symbol_match = re.search(r"\b([A-Z]{2,10})\b", message)
                if symbol_match:
                    tool_calls = [
                        {"tool": "get_market_data", "args": {"symbol": symbol_match.group(1)}},
                        {"tool": "search_news", "args": {"query": f"{symbol_match.group(1)} stock news"}}
                    ]
                else:
                    tool_calls = [{"tool": "web_search", "args": {"query": message}}]
                    
        return {
            "intent": route_category,  # DIRECT, MEMORY, PORTFOLIO, TOOLS
            "tool_calls": tool_calls,
            "prompt_tokens": state.get("prompt_tokens", 0) + total_p,
            "completion_tokens": state.get("completion_tokens", 0) + total_c,
            "total_tokens": state.get("total_tokens", 0) + total_t,
        }

    def profile_node(self, state: CopilotState) -> Dict[str, Any]:
        if state.get("temporary", False):
            return {"user_profile": {"risk_appetite": "MODERATE", "time_horizon": "MEDIUM_TERM", "investment_goal": "BALANCED", "monthly_investment_budget": 0, "missing_fields": []}}
        profile = self._load_user_profile(state["db"], state["user_id"])
        if not state.get("temporary", False):
            profile_memories = self.retrieve_relevant_memories(
                state["db"],
                state["user_id"],
                "user risk profile investment preferences budget time horizon",
                top_k=5,
            )
            if profile_memories:
                profile["memory_notes"] = [item["text"] for item in profile_memories]
        return {"user_profile": profile}

    def portfolio_node(self, state: CopilotState) -> Dict[str, Any]:
        if state.get("temporary", False):
            return {"portfolio_snapshot": None}
        snapshot = self._load_portfolio_snapshot(
            state["db"],
            state["user_id"],
            max_holdings=state.get("max_holdings", 5),
        )
        return {"portfolio_snapshot": snapshot}

    def market_node(self, state: CopilotState) -> Dict[str, Any]:
        relevant_symbols = list(state.get("relevant_symbols", []))
        if not relevant_symbols and state.get("portfolio_snapshot"):
            relevant_symbols = state["portfolio_snapshot"].get("top_tickers", [])[:3]
        return {
            "market_data": self._fetch_market_macro_snapshot(relevant_symbols),
            "relevant_symbols": relevant_symbols,
        }

    def news_node(self, state: CopilotState) -> Dict[str, Any]:
        news_context = self._build_news_context(
            state.get("portfolio_snapshot"),
            state.get("relevant_symbols", []),
            state.get("max_news_per_symbol", 2),
        )
        return {"news_context": news_context}

    def memory_node(self, state: CopilotState) -> Dict[str, Any]:
        if state.get("temporary", False):
            return {"retrieved_memory": []}

        query = f"{state.get('intent', 'education')}: {state['message']}"
        memories = self.retrieve_relevant_memories(
            state["db"],
            state["user_id"],
            query,
            top_k=8,
        )
        return {"retrieved_memory": memories}

    def context_orchestrator_node(self, state: CopilotState) -> Dict[str, Any]:
        intent = state.get("intent", "TOOLS")
        working_state = dict(state)
        updates: Dict[str, Any] = {}

        if intent == "DIRECT":
            return {}

        elif intent == "MEMORY":
            # Execute profile and memory lookups
            p_res = self.profile_node(working_state)
            updates.update(p_res)
            working_state.update(p_res)
            
            m_res = self.memory_node(working_state)
            updates.update(m_res)

        elif intent == "PORTFOLIO":
            # Execute portfolio snapshot and portfolio-specific news
            p_res = self.portfolio_node(working_state)
            updates.update(p_res)
            working_state.update(p_res)
            
            n_res = self._execute_tool("get_portfolio_news", {}, working_state["db"], working_state["user_id"])
            updates.update(n_res)

        elif intent == "TOOLS":
            # Execute selected tools sequentially
            tool_calls = state.get("tool_calls", [])
            for tc in tool_calls:
                res = self._execute_tool(tc["tool"], tc.get("args", {}), working_state["db"], working_state["user_id"])
                updates.update(res)
                working_state.update(res)

        return updates

    def strategist_node(self, state: CopilotState) -> Dict[str, Any]:
        intent = state.get("intent", "TOOLS")

        strategist_prompt, model = self._get_strategist_prompt_and_model(intent, state)

        try:
            result = model.invoke(strategist_prompt)
            payload = self._clean_and_parse_json(self._extract_text(result))
        except Exception as err:
            logger.error(f"Strategist node generation failed: {err}")
            fallback_answer = (
                "## Context-aware view\n"
                "I could not complete the full reasoning pass just now, but I can still help you narrow the question.\n\n"
                "- Ask about **allocation**, **risk concentration**, **watchlist fit**, or **recent market/news impact**.\n"
                "- If you want a planning answer, include your intended amount and time horizon."
            )
            payload = {
                "answer": fallback_answer,
                "caveat": self._default_caveat(),
                "evidence": [],
                "next_steps": [
                    "Tell me the exact amount or ticker you want reviewed.",
                    "Mention whether your priority is growth, income, or risk reduction.",
                ],
                "plan_draft": {
                    "intent": intent,
                    "summary": "Fallback response due to strategist generation issue.",
                    "risk_flags": [],
                },
            }

        payload["answer"] = payload.get("answer") or ""
        payload["caveat"] = payload.get("caveat") or self._default_caveat()
        payload["evidence"] = payload.get("evidence") or []
        payload["next_steps"] = payload.get("next_steps") or []
        payload["plan_draft"] = payload.get("plan_draft") or {
            "intent": intent,
            "summary": "",
            "risk_flags": [],
        }

        return {
            "plan_draft": payload["plan_draft"],
            "final_answer": payload["answer"],
            "final_response": {
                "answer": payload["answer"],
                "caveat": payload["caveat"],
                "evidence": payload["evidence"],
                "next_steps": payload["next_steps"],
            },
        }

    def compliance_node(self, state: CopilotState) -> Dict[str, Any]:
        payload = dict(state.get("final_response") or {})
        payload["answer"] = self._clean_response_prefix(self._soften_investment_language(payload.get("answer") or ""))
        payload["caveat"] = self._soften_investment_language(payload.get("caveat") or self._default_caveat())
        payload["evidence"] = [
            self._soften_investment_language(item)
            for item in (payload.get("evidence") or [])
        ]
        payload["next_steps"] = [
            self._soften_investment_language(item)
            for item in (payload.get("next_steps") or [])
        ]
        return {
            "final_answer": payload.get("answer") or "",
            "final_response": payload,
        }

    def save_and_reply_node(self, state: CopilotState) -> Dict[str, Any]:
        db = state["db"]
        user_id = state["user_id"]
        session_id = state.get("session_id")

        session_meta = self._ensure_runtime_session(db, user_id, session_id)
        effective_session_id = session_meta["session_id"]

        from app.models.chat import ChatMessage  # adjust import path

        now = datetime.now(timezone.utc)

        # Persist messages to DB
        user_msg = ChatMessage(
            session_id=effective_session_id,
            role="user",
            content=state["message"],
            created_at=now,
        )
        assistant_msg = ChatMessage(
            session_id=effective_session_id,
            role="assistant",
            content=state.get("final_answer", ""),
            created_at=now,
        )

        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()

        # Reload last N messages for in-graph use
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == effective_session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(40)
            .all()
        )
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.content
        ]

        # Memory extraction should ideally be offloaded to a background worker;
        # here, we just make failure non-fatal.
        if not state.get("temporary", False):
            try:
                # You can enqueue a background job instead of direct call
                self.extract_and_store_memory(db, user_id, state["message"])
            except Exception as mem_err:
                logger.error(f"Background memory extraction error (non-fatal): {mem_err}")

        final_response = state.get(
            "final_response",
            {
                "answer": state.get("final_answer", ""),
                "caveat": self._default_caveat(),
                "evidence": [],
                "next_steps": [],
            },
        )

        return {
            "history": history,
            "final_response": final_response,
        }

    # LangGraph Node 1: Gather Portfolio and Context Data
    def gather_data(self, state: ReviewState) -> Dict[str, Any]:
        db = state["db"]
        user_id = state["user_id"]
        
        # 1. Fetch User Profile
        profile_obj = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        profile_data = {
            "risk_appetite": profile_obj.risk_appetite if profile_obj else "MODERATE",
            "time_horizon": profile_obj.time_horizon if profile_obj else "MEDIUM_TERM",
            "investment_goal": profile_obj.investment_goal if profile_obj else "WEALTH_ACCUMULATION",
        }
        
        # 2. Fetch Holdings & Metrics
        holdings_res = holdings_service.calculate_holdings(db, user_id)
        holdings_data = []
        for h in holdings_res.holdings:
            sector = market_data_service.get_sector(h.symbol)
            mkt_cap = market_data_service.get_market_cap(h.symbol)
            cap_bucket = get_market_cap_bucket(h.symbol, mkt_cap)
            
            holdings_data.append({
                "symbol": h.symbol,
                "company_name": h.company_name,
                "quantity": h.quantity,
                "market_value": round(h.market_value, 2) if h.market_value else 0.0,
                "allocation_percent": round(h.allocation_percent, 2) if h.allocation_percent else 0.0,
                "sector": sector,
                "market_cap_bucket": cap_bucket
            })
            
        warnings = []
        for h in holdings_data:
            if h["allocation_percent"] > 20.0:
                warnings.append({
                    "type": "CONCENTRATION",
                    "symbol": h["symbol"],
                    "message": f"{h['symbol']} constitutes {h['allocation_percent']:.1f}% of your portfolio, exceeding recommended single-asset concentration guidelines."
                })

        metrics_data = {
            "total_value": round(holdings_res.summary.total_value, 2) if holdings_res.summary.total_value else 0.0,
            "total_cost": round(holdings_res.summary.total_cost, 2) if holdings_res.summary.total_cost else 0.0,
            "warnings": warnings
        }
        
        # 3. Fetch Watchlist
        watchlist_obj = db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
        watchlist_symbols = [w.symbol for w in watchlist_obj]
        watchlist_prices = market_data_service.get_prices_bulk(watchlist_symbols)
        watchlist_data = []
        for w in watchlist_obj:
            sector = market_data_service.get_sector(w.symbol)
            mkt_cap = market_data_service.get_market_cap(w.symbol)
            cap_bucket = get_market_cap_bucket(w.symbol, mkt_cap)
            mkt_price = watchlist_prices.get(w.symbol, 100.0)
            watchlist_data.append({
                "symbol": w.symbol,
                "company_name": w.company_name or w.symbol,
                "return_since_added": round(w.calculate_return(mkt_price), 2),
                "sector": sector,
                "market_cap_bucket": cap_bucket
            })
            
        # 4. Fetch News Context
        symbols_map = {h["symbol"]: h["company_name"] for h in holdings_data}
        for w in watchlist_data:
            symbols_map[w["symbol"]] = w["company_name"]
            
        bulk_news = news_service.fetch_news_bulk(symbols_map)
        news_data = []
        for symbol, articles in bulk_news.items():
            for art in articles:
                news_data.append({
                    "symbol": symbol,
                    "title": art["title"],
                    "link": art["link"],
                    "source": art["source"],
                    "published_at": art["published_at"]
                })
                
        condensed_signals = self.news_filter({
            "news": news_data
        })

        return {
            "profile": profile_data,
            "holdings": holdings_data,
            "metrics": metrics_data,
            "watchlist": watchlist_data,
            "news": news_data,
            "condensed_signals": condensed_signals,
        }
    def news_filter(self, state: ReviewState) -> str:
        news = state["news"]
        
        recent_news = sorted(news, key=lambda x: x["published_at"] or "", reverse=True)[:6]
        
        # Upstream news pre-filtering using the cheaper flash_model
        condensed_signals = ""
        if recent_news:
            flash_prompt = f"""
            You are NiveshIQ's AI Market Intelligence Parser. Convert this raw news feed into a highly compact, numbered list of market/macro signals.
            For each article, summarize it in one-two line. Keep it short. Include the ticker/symbol or company name.
            
            Example format:
            [1] Ticker: HDFCBANK.NS - Governance questions raised, stock fell 3% today.
            [2] Ticker: RELIANCE.NS - Trading ex-dividend this week with high expectations.
            [3] Ticker: TCS.NS - Q4 earnings beat estimates, stock rose 2% today.
            [4] Macro: USDINR - INR weakened against USD by 0.5% amid global dollar strength.
            [5] Macro: NIFTY50 - Nifty50 down 1.2% as banking and IT stocks dragged the index lower.
            [6] Macro: RBI - RBI hints at possible rate cut in upcoming policy review, markets react positively.
            
            RAW NEWS ARTICLES:
            {json.dumps(recent_news, indent=2)}
            
            Return ONLY the numbered list. No extra explanations, headers, or markdown formatting.
            """
            try:
                flash_result = self.flash_model.invoke(flash_prompt)
                logger.info("FLASH TOKEN USAGE:", getattr(flash_result, "response_metadata", {}).get("usage_metadata"))
                tokens = self._extract_token_usage(flash_result)
                state["prompt_tokens"] = state.get("prompt_tokens", 0) + tokens["prompt_tokens"]
                state["completion_tokens"] = state.get("completion_tokens", 0) + tokens["completion_tokens"]
                state["total_tokens"] = state.get("total_tokens", 0) + tokens["total_tokens"]
                condensed_signals = self._extract_text(flash_result)
                logger.info("--- FLASH CONDENSED NEWS ---")
                logger.info(condensed_signals)
                logger.info("----------------------------")
                return condensed_signals
            except Exception as e:
                logger.error(f"Flash model news pre-filtering failed: {e}")
                # Fallback to serializing raw news (with links stripped to save tokens)
                condensed_signals = "\n".join(
                    f"[{i+1}] Ticker: {art['symbol']} - {art['title']} (Source: {art['source']})"
                    for i, art in enumerate(recent_news)
                )
        else:
            condensed_signals = "No recent news signals or macro indicators available."
        return condensed_signals

    def generate_insights(self, state: ReviewState) -> Dict[str, Any]:
        profile = state["profile"]
        holdings = state["holdings"]
        metrics = state["metrics"]
        watchlist = state["watchlist"]
        condensed_signals = state["condensed_signals"]
        
        prompt = f"""
        You are NiveshIQ, a premium AI Portfolio Strategist. Review this user's investment portfolio and watchlist to draft a comprehensive report.
        
        USER PROFILE:
        - Risk Appetite: {profile["risk_appetite"]}
        - Time Horizon: {profile["time_horizon"]}
        - Investment Goal: {profile["investment_goal"]}
        - Portfolio Value: {metrics["total_value"]}
        
        ACTIVE ASSETS:
        {json.dumps(holdings, indent=2)}
        
        WATCHLIST CANDIDATES:
        {json.dumps(watchlist, indent=2)}
        
        RECENT SIGNALS & NEWS:
        {condensed_signals}
        
        Write a structural, explainable review in strict JSON format. 
        You MUST provide:
        - "risk_summary": A detailed analysis of their major risk parameters (like high single-asset concentration or tech overexposure).
        - "diversification_summary": A review of their sector diversity.
        - "rebalancing_ideas": Actionable recommended actions (e.g. "trim 5% from pharma sector", "add in SIP style", "avoid adding more", "rebalancing"). Fields: "sector", "action" (ADD/TRIM/SIP/AVOID_ADDING/REBALANCE), "explanation", "target_change_percent".
        - "potential_stock_picks": Suggested stock picks based on the market situation and user profile. Strongly prefer stock picks from the user's Watchlist, or recommend similar highly suitable stocks. Fields: "symbol", "company_name", "compatibility" (EXCELLENT/GOOD/NEUTRAL/AVOID), "reasoning", "score" (out of 10).
        - "warnings": A list of warning objects with fields "symbol", "warning_level" (YELLOW for medium warning / RED for strong warning), and "message".
        - "market_impact": Expected future scenario listing the portfolio's expected future performance (e.g., "HDFCBANK may fall more in the short term but global investment firms retain a BUY rating", or "The overall portfolio may experience short-term volatility but can yield solid long-term returns").
        - "news_insights": A list of bullet point strings summarizing the most important news related to the portfolio and watchlist (e.g., "TCS Q4 earnings raised by 3% [1]", "HDFCBANK is facing short term volatility [2]"). Each bullet point MUST cite a news item from RECENT SIGNALS & NEWS using citations [1], [2], etc.

        IMPORTANT: In the texts, insert citation numbers [1], [2], etc., corresponding to the indices of the signals/news items they refer to.
        
        Format output strictly as raw JSON matching this structure without any markdown blocks:
        {{
          "risk_summary": "Detailed risk summary text.",
          "diversification_summary": "Detailed sector diversification text.",
          "rebalancing_ideas": [
            {{
              "sector": "Sector Name",
              "action": "ADD/TRIM/SIP/AVOID_ADDING/REBALANCE",
              "explanation": "Explanation text.",
              "target_change_percent": -5
            }}
          ],
          "potential_stock_picks": [
            {{
              "symbol": "TCS",
              "company_name": "Tata Consultancy Services",
              "compatibility": "EXCELLENT",
              "reasoning": "Reasoning text.",
              "score": 9
            }}
          ],
          "warnings": [
            {{
              "symbol": "Ticker/PORTFOLIO",
              "warning_level": "RED/YELLOW",
              "message": "Warning text."
            }}
          ],
          "market_impact": "Expected future performance scenario text.",
          "news_insights": [
            "TCS Q4 earnings raised by 3% [1]",
            "HDFCBANK is facing short term volatility [2]"
          ]
        }}
        """
        
        try:
            result = self.pro_model.invoke(prompt)
            logger.info("PRO MODEL TOKEN USAGE:", getattr(result, "response_metadata", {}).get("usage_metadata"))
            tokens = self._extract_token_usage(result)
            state["prompt_tokens"] = state.get("prompt_tokens", 0) + tokens["prompt_tokens"]
            state["completion_tokens"] = state.get("completion_tokens", 0) + tokens["completion_tokens"]
            state["total_tokens"] = state.get("total_tokens", 0) + tokens["total_tokens"]
            raw_text = self._extract_text(result)
            data = self._clean_and_parse_json(raw_text)
            return {"draft_insights": data}
        except Exception as e:
            logger.error(f"Vertex AI strategic generation failed: {e}")
            raise Exception("We are facing some difficulties please try again later") from e


    # LangGraph Node 3: Safety Guardrail Node
    def safety_guardrail(self, state: ReviewState) -> Dict[str, Any]:
        draft = state["draft_insights"]
        
        prompt = f"""
        You are a strict compliance reviewer for an AI financial assistant. 
        Your task is to review the following JSON portfolio report and contextually soften any definitive, prescriptive, or guaranteed language to make it educational and SEBI-compliant.

        Instructions:
        - Replace direct commands like "buy" or "sell" with suggestive terms like "consider accumulating" or "consider trimming".
        - Remove words like "guaranteed", "sure-shot", or "must invest".
        - Ensure the tone remains objective and analytical.
        - Do NOT change the JSON keys, structure, or array lengths.
        - Return ONLY the compliant JSON.

        Example :
        "Reliance is a strong buy" (needs softening) and "Foreign institutional buyers continue to buy Indian equities" (factual reporting, does not need softening)

        REPORT: Reliance is a strong buy given its robust financials and market position. HDFCBANK is facing short-term volatility but can be considered for accumulation. TCS has an excellent compatibility score of 9/10 and can be a good addition to the portfolio. However, the overall portfolio may experience short-term volatility but can yield solid long-term returns.

        DRAFT JSON:
        {json.dumps(draft, indent=2)}
        """
        
        try:
            result = self.flash_lite_model.invoke(prompt)
            logger.info("FLASH LITE TOKEN USAGE:", getattr(result, "response_metadata", {}).get("usage_metadata"))
            tokens = self._extract_token_usage(result)
            state["prompt_tokens"] = state.get("prompt_tokens", 0) + tokens["prompt_tokens"]
            state["completion_tokens"] = state.get("completion_tokens", 0) + tokens["completion_tokens"]
            state["total_tokens"] = state.get("total_tokens", 0) + tokens["total_tokens"]
            raw_text = self._extract_text(result)
            compliant_draft = self._clean_and_parse_json(raw_text)
            
            # Ensure the LLM didn't break the JSON structure before adopting it
            if isinstance(compliant_draft, dict) and "risk_summary" in compliant_draft:
                draft = compliant_draft
            else:
                raise ValueError("LLM returned invalid JSON structure.")
        except Exception as e:
            logger.warning(f"LLM safety guardrail failed, falling back to rule-based softening: {e}")
            
            # Fallback to the class-level regex method (which is richer than the previous inline one)
            draft["risk_summary"] = self._soften_investment_language(draft.get("risk_summary") or "")
            draft["diversification_summary"] = self._soften_investment_language(draft.get("diversification_summary") or "")
            draft["market_impact"] = self._soften_investment_language(draft.get("market_impact") or "")
            
            draft["news_insights"] = [self._soften_investment_language(b) for b in (draft.get("news_insights") or [])]
            for w in (draft.get("warnings") or []):
                w["message"] = self._soften_investment_language(w.get("message") or "")
            for r in (draft.get("rebalancing_ideas") or []):
                r["explanation"] = self._soften_investment_language(r.get("explanation") or "")
            for p in (draft.get("potential_stock_picks") or []):
                p["reasoning"] = self._soften_investment_language(p.get("reasoning") or "")
            
        draft["disclaimers"] = "Educational analysis only: Not SEBI-registered financial advice. All investments carry risk."
        
        return {"draft_insights": draft}

    # LangGraph Node 4: Save & Assemble Report
    def assemble_report(self, state: ReviewState) -> Dict[str, Any]:
        db = state["db"]
        user_id = state["user_id"]
        draft = state["draft_insights"]
        metrics = state["metrics"]
        holdings = state["holdings"]
        news = state["news"]
        
        evidence = {
            "holdings": holdings,
            "references": sorted(news, key=lambda x: x["published_at"], reverse=True)[:6],
            "news_insights": draft.get("news_insights", [])
        }
        
        db.query(PortfolioReview).filter(PortfolioReview.user_id == user_id).delete()
        
        db_review = PortfolioReview(
            user_id=user_id,
            risk_summary=draft.get("risk_summary", "Review under compile."),
            diversification_summary=draft.get("diversification_summary", "Review under compile."),
            rebalancing_ideas=draft.get("rebalancing_ideas", []),
            potential_stock_picks=draft.get("potential_stock_picks", []),
            warnings=draft.get("warnings", []),
            market_impact=draft.get("market_impact", "Market impact analysis pending."),
            evidence=evidence,
            disclaimers=draft.get("disclaimers", ""),
            prompt_tokens=state.get("prompt_tokens", 0),
            completion_tokens=state.get("completion_tokens", 0),
            total_tokens=state.get("total_tokens", 0)
        )
        
        db.add(db_review)
        db.commit()
        db.refresh(db_review)
        
        try:
            if db_review.created_at.tzinfo is not None:
                created_at_str = db_review.created_at.isoformat()
            else:
                created_at_str = db_review.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        except Exception:
            created_at_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

        report = {
            "id": db_review.id,
            "user_id": db_review.user_id,
            "created_at": created_at_str,
            "risk_summary": db_review.risk_summary,
            "diversification_summary": db_review.diversification_summary,
            "rebalancing_ideas": db_review.rebalancing_ideas,
            "potential_stock_picks": db_review.potential_stock_picks,
            "warnings": db_review.warnings,
            "market_impact": db_review.market_impact,
            "evidence": db_review.evidence,
            "disclaimers": db_review.disclaimers
        }
        return {"final_report": report}

    def generate_review(self, db: Session, user_id: str) -> Dict[str, Any]:
        """
        Orchestrate the portfolio review generation using a modern LangGraph workflow.
        """
        workflow = StateGraph(ReviewState)
        
        workflow.add_node("gather_data", self.gather_data)
        workflow.add_node("generate_insights", self.generate_insights)
        workflow.add_node("safety_guardrail", self.safety_guardrail)
        workflow.add_node("assemble_report", self.assemble_report)
        
        workflow.add_edge(START, "gather_data")
        workflow.add_edge("gather_data", "generate_insights")
        workflow.add_edge("generate_insights", "safety_guardrail")
        workflow.add_edge("safety_guardrail", "assemble_report")
        workflow.add_edge("assemble_report", END)
        
        graph = workflow.compile()
        
        initial_state = {
            "db": db,
            "user_id": user_id,
            "profile": {},
            "holdings": [],
            "metrics": {},
            "news": [],
            "watchlist": [],
            "draft_insights": {},
            "final_report": {},
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
        
        result = graph.invoke(initial_state)
        return result["final_report"]

    def generate_watchlist_recommendations(self, db: Session, user_id: str) -> List[Dict[str, Any]]:
        """
        Analyze watchlist assets based on geocoded news sentiment, history, and profile.
        Uses gemini-2.5-pro for high level strategist suggestions.
        """
        # Fetch risk profile
        profile_obj = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        profile_data = {
            "risk_appetite": profile_obj.risk_appetite if profile_obj else "MODERATE",
            "time_horizon": profile_obj.time_horizon if profile_obj else "MEDIUM_TERM",
            "investment_goal": profile_obj.investment_goal if profile_obj else "WEALTH_ACCUMULATION"
        }
        
        # Fetch watchlist items
        watchlist_obj = db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
        if not watchlist_obj:
            return []
            
        watchlist_symbols = [w.symbol for w in watchlist_obj]
        watchlist_prices = market_data_service.get_prices_bulk(watchlist_symbols)
            
        holdings_res = holdings_service.calculate_holdings(db, user_id)
        sector_alloc = {}
        for h in holdings_res.holdings:
            sec = market_data_service.get_sector(h.symbol)
            sector_alloc[sec] = sector_alloc.get(sec, 0.0) + h.allocation_percent
            
        watchlist_data = []
        for w in watchlist_obj:
            price = watchlist_prices.get(w.symbol, 100.0)
            sector = market_data_service.get_sector(w.symbol)
            mkt_cap = market_data_service.get_market_cap(w.symbol)
            cap_bucket = get_market_cap_bucket(w.symbol, mkt_cap)
            
            watchlist_data.append({
                "symbol": w.symbol,
                "company_name": w.company_name or w.symbol,
                "current_price": price,
                "sector": sector,
                "market_cap_bucket": cap_bucket,
                "return_since_added": round(w.calculate_return(price), 2)
            })
            
        symbols_map = {w["symbol"]: w["company_name"] for w in watchlist_data}
        bulk_news = news_service.fetch_news_bulk(symbols_map)
        
        news_list = []
        for symbol, articles in bulk_news.items():
            for art in articles[:3]:
                news_list.append({
                    "symbol": symbol,
                    "title": art["title"],
                    "source": art["source"],
                    "published_at": art.get("published_at")
                })
        
        condensed_signals = self.news_filter({
            "news": news_list
        })
                
            
        prompt = f"""
        You are NiveshIQ, a premium AI Portfolio Strategist specializing in Indian equities, ETFs, and long-term portfolio construction.

        Analyze the user's risk profile, current sector allocations, watchlist assets, and recent news signals to determine how suitable each watchlist asset is for the user.

        USER PROFILE:
        {json.dumps(profile_data, indent=2)}

        PORTFOLIO SECTOR ALLOCATIONS:
        {json.dumps(sector_alloc, indent=2)}

        WATCHLIST CANDIDATES:
        {json.dumps(watchlist_data, indent=2)}

        NEWS SIGNALS:
        {json.dumps(condensed_signals, indent=2)}

        TASK:

        For EACH watchlist asset:

        1. Evaluate recent performance trends (if available).
        2. Analyze market sentiment using the supplied news signals.
        3. Consider macroeconomic and sector-specific factors.
        4. Check whether adding the asset would improve or worsen portfolio diversification.
        5. Evaluate compatibility with the user's:

        * Risk tolerance
        * Investment horizon
        * Existing sector exposures
        * Portfolio concentration

        Generate a detailed recommendation of 40-50 words.

        The recommendation must:

        * Explain WHY the asset is attractive or unattractive.
        * Mention relevant news signals using citations [1], [2], etc. corresponding to NEWS SIGNALS indices.
        * Explain diversification impact.
        * Explain risk considerations.
        * End with a clear portfolio action view.

        Compatibility labels:

        * EXCELLENT = Strong fit for profile and diversification needs.
        * GOOD = Positive fit with manageable risks.
        * NEUTRAL = Mixed outlook or limited portfolio benefit.
        * AVOID = Poor fit, excessive risk, or negative outlook.

        Example recommendation:

        "GOLDBEES has declined 8.17% over the last three months amid a stronger US dollar and changing import duty expectations [2]. However, ongoing geopolitical uncertainty and inflation concerns continue to support demand for gold as a defensive asset [1]. For this investor, GOLDBEES can improve portfolio diversification because the current allocation is heavily tilted toward equities. While short-term returns may remain volatile, gold can provide downside protection during periods of market stress. Recommendation: Maintain a moderate allocation as a portfolio hedge."

        Return ONLY valid JSON.

        Schema:

        [
        {{
        "symbol": "TCS",
        "recommendation": "Detailed recommendation text with citations.",
        "compatibility": "EXCELLENT"
        }}
        ]

        Do not return markdown.
        Do not return explanations outside JSON.
        Do not return additional fields.
        """

        
        try:
            result = self.pro_model.invoke(prompt)
            logger.info("PRO MODEL TOKEN USAGE:", getattr(result, "response_metadata", {}).get("usage_metadata"))
            raw_text = self._extract_text(result)
            data = self._clean_and_parse_json(raw_text)
            
            # Soften recommendations for SEBI compliance
            for item in data:
                t = item.get("recommendation", "")
                t = re.sub(r"\bbuy\b", "consider accumulating", t, flags=re.IGNORECASE)
                t = re.sub(r"\bsell\b", "consider trimming/rebalancing", t, flags=re.IGNORECASE)
                item["recommendation"] = t
                
            return data
        except Exception as e:
            logger.error(f"Vertex AI watchlist recommendations failed: {e}")
            raise HTTPException(
                status_code=500,
                detail="We are facing some difficulties please try again later"
            )

    def _plan_context(self, query: str, portfolio_stub: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses a cheap Gemini 2.5 flash_lite model to decide what context
        is needed for this query and how much to include.
        """
        planner_prompt = f"""
        You are NiveshIQ's Finance Context Planner.

        Your job is to decide what dynamic context the system should fetch BEFORE answering the user's question.

        You must analyze the USER QUESTION and the PORTFOLIO_STUB and output a JSON plan describing:
        - primary_topic: one of ["PORTFOLIO", "STOCK", "WATCHLIST", "MARKET_SENTIMENT", "MACRO_ECONOMY", "POLICY_SEBI_RBI", "TRADING_CONCEPT", "GENERAL_FINANCE"]
        - needs_portfolio_context: boolean
        - needs_market_snapshot: boolean
        - needs_macro_snapshot: boolean
        - needs_policy_docs: boolean
        - needs_news: boolean
        - relevant_symbols: list of tickers (if question is about specific stocks; else empty)
        - max_holdings: integer (how many top holdings to include if portfolio is needed)
        - max_news_per_symbol: integer (0-3 for news density)

        USER QUESTION:
        \"\"\"{query}\"\"\"


        PORTFOLIO_STUB:
        {json.dumps(portfolio_stub, indent=2)}

        Rules:
        - If the user mentions "my portfolio", "my holdings", "my allocation", etc., needs_portfolio_context is almost always true.
        - If the user mentions "current market", "market scenario", "market sentiment", today's or recent dates, set needs_market_snapshot true.
        - If the user mentions inflation, repo rate, RBI, interest rates, GDP, macro, set needs_macro_snapshot true.
        - If the user asks about SEBI, RBI circulars, regulations, rules, set needs_policy_docs true.
        - If the user mentions specific stock symbols or company names, include them in relevant_symbols.
        - Keep max_holdings small (3-8) to preserve tokens.
        - Return ONLY valid JSON. No markdown, no commentary.

        Output JSON schema example:
        {{
        "primary_topic": "MARKET_SENTIMENT",
        "needs_portfolio_context": true,
        "needs_market_snapshot": true,
        "needs_macro_snapshot": false,
        "needs_policy_docs": false,
        "needs_news": true,
        "relevant_symbols": ["RELIANCE", "HDFCBANK"],
        "max_holdings": 5,
        "max_news_per_symbol": 2
        }}
        """

        result = self.flash_lite_model.invoke(planner_prompt)
        logger.info("FLASH LITE TOKEN USAGE:", getattr(result, "response_metadata", {}).get("usage_metadata"))
        raw = self._extract_text(result)
        plan = self._clean_and_parse_json(raw)
        return plan

    def ask_copilot(self, db: Session, user_id: str, query: str, temporary: bool = False) -> Dict[str, Any]:
        """
        Ask the NiveshIQ finance copilot a question using the graph-based flow:
        load_history -> router -> context_orchestrator -> strategist -> compliance -> save_and_reply.

        Temporary mode keeps the interaction stateless with respect to vector memory.
        """
        try:
            initial_state: CopilotState = {
                "db": db,
                "user_id": user_id,
                "message": query,
                "temporary": temporary,
            }
            result = self.copilot_graph.invoke(initial_state)
            response = dict(result.get("final_response") or {})
            response.setdefault("answer", "")
            response.setdefault("caveat", self._default_caveat())
            response.setdefault("evidence", [])
            response.setdefault("next_steps", [])
            return response
        except Exception as e:
            logger.error(f"Copilot graph execution failed: {e}")
            return {
                "answer": (
                    "## I hit a temporary issue while assembling the full analysis\n"
                    "- Try asking the question again in a moment.\n"
                    "- If you want, make the prompt narrower: a single ticker, allocation question, or portfolio risk question."
                ),
                "caveat": self._default_caveat(),
                "evidence": [],
                "next_steps": [
                    "Retry the same question once.",
                    "If it still fails, ask a narrower follow-up focused on one symbol or one portfolio concern.",
                ],
            }

    def _check_and_update_profile_from_chat(self, db: Session, user_id: str, query: str, missing_fields: List[str]) -> None:
        if not missing_fields:
            return
            
        prompt = f"""
        You are a profile extraction assistant.
        The user has missing profile fields: {missing_fields}.
        Analyze the user's latest response:
        \"\"\"{query}\"\"\"

        Extract any information that answers the missing fields.
        Values must match:
        - risk_appetite: 'CONSERVATIVE', 'MODERATE', or 'AGGRESSIVE'
        - time_horizon: 'SHORT_TERM', 'MEDIUM_TERM', or 'LONG_TERM'
        - investment_goal: 'WEALTH_ACCUMULATION', 'RETIREMENT', 'INCOME', or 'BALANCED'
        - monthly_investment_budget: float/integer number

        Return ONLY a JSON object containing the extracted fields, or empty JSON {{}} if no fields are answered.
        Example:
        {{
          "monthly_investment_budget": 10000
        }}
        """
        try:
            result = self.flash_lite_model.invoke(prompt)
            logger.info("FLASH LITE TOKEN USAGE:", getattr(result, "response_metadata", {}).get("usage_metadata"))
            raw = self._extract_text(result)
            extracted = self._clean_and_parse_json(raw)
            if extracted:
                profile_obj = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
                if not profile_obj:
                    profile_obj = UserProfile(
                        user_id=user_id,
                        risk_appetite="MODERATE",
                        time_horizon="MEDIUM_TERM",
                        investment_goal="WEALTH_ACCUMULATION"
                    )
                    db.add(profile_obj)
                
                updated = False
                for k, v in extracted.items():
                    if k in missing_fields and v is not None:
                        if k == "risk_appetite" and v in ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]:
                            profile_obj.risk_appetite = v
                            updated = True
                        elif k == "time_horizon" and v in ["SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"]:
                            profile_obj.time_horizon = v
                            updated = True
                        elif k == "investment_goal" and v in ["WEALTH_ACCUMULATION", "RETIREMENT", "INCOME", "BALANCED"]:
                            profile_obj.investment_goal = v
                            updated = True
                        elif k == "monthly_investment_budget":
                            try:
                                profile_obj.monthly_investment_budget = float(v)
                                updated = True
                            except (ValueError, TypeError):
                                pass
                if updated:
                    db.commit()
                    logger.info(f"Profile updated from chat: {extracted}")
        except Exception as e:
            logger.error(f"Failed to check/update profile from chat: {e}")
            try:
                db.rollback()
            except Exception:
                pass

    async def ask_copilot_stream(self, db: Session, user_id: str, query: str, temporary: bool = False, session_id: Optional[str] = None):
        """
        Stream the copilot response using Server-Sent Events (SSE) asynchronously.
        """
        state: CopilotState = {
            "db": db,
            "user_id": user_id,
            "message": query,
            "temporary": temporary,
            "session_id": session_id,
        }
        
        try:
            # Check for profile updates from the user's query first
            profile = self._load_user_profile(db, user_id)
            missing_fields = profile.get("missing_fields", [])
            if missing_fields and not temporary:
                self._check_and_update_profile_from_chat(db, user_id, query, missing_fields)

            # Let frontend know we are starting the analysis
            yield f"data: {json.dumps({'type': 'status', 'text': 'Thinking...'})}\n\n"

            state.update(self.load_history_node(state))
            state.update(self.router_node(state))

            intent = state.get("intent", "TOOLS")

            import asyncio
            from app.db.session import SessionLocal

            async def run_node_in_thread(node_name, node_fn, node_state):
                loop = asyncio.get_running_loop()
                def wrapper():
                    new_db = SessionLocal()
                    try:
                        thread_state = dict(node_state)
                        thread_state["db"] = new_db
                        return node_fn(thread_state)
                    finally:
                        new_db.close()
                res = await loop.run_in_executor(None, wrapper)
                return node_name, res

            async def run_tool_in_thread(tool_name, args):
                loop = asyncio.get_running_loop()
                def wrapper():
                    new_db = SessionLocal()
                    try:
                        return self._execute_tool(tool_name, args, new_db, user_id)
                    finally:
                        new_db.close()
                res = await loop.run_in_executor(None, wrapper)
                return tool_name, res

            if intent == "DIRECT":
                pass

            elif intent == "MEMORY":
                tasks = [
                    run_node_in_thread("profile", self.profile_node, state),
                    run_node_in_thread("memory", self.memory_node, state)
                ]
                for future in asyncio.as_completed(tasks):
                    name, res = await future
                    state.update(res)
                    if name == "profile":
                        yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved user profile'})}\n\n"
                    elif name == "memory":
                        yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved memory'})}\n\n"

            elif intent == "PORTFOLIO":
                tasks = [
                    run_node_in_thread("portfolio", self.portfolio_node, state),
                    run_tool_in_thread("get_portfolio_news", {})
                ]
                for future in asyncio.as_completed(tasks):
                    name, res = await future
                    state.update(res)
                    if name == "portfolio":
                        yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved portfolio'})}\n\n"
                    elif name == "get_portfolio_news":
                        yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved portfolio news'})}\n\n"

            elif intent == "TOOLS":
                tool_calls = state.get("tool_calls", [])
                tasks = [run_tool_in_thread(tc["tool"], tc.get("args", {})) for tc in tool_calls]
                if tasks:
                    for future in asyncio.as_completed(tasks):
                        tool_name, res = await future
                        state.update(res)
                        if tool_name == "get_portfolio":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved portfolio'})}\n\n"
                        elif tool_name == "get_user_profile":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved user profile'})}\n\n"
                        elif tool_name == "search_memory":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved memory'})}\n\n"
                        elif tool_name == "get_market_data":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved market data'})}\n\n"
                        elif tool_name == "search_news":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Searched news'})}\n\n"
                        elif tool_name == "get_portfolio_news":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Retrieved portfolio news'})}\n\n"
                        elif tool_name == "web_search":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Searched the web'})}\n\n"
                        elif tool_name == "calculator":
                            yield f"data: {json.dumps({'type': 'status', 'text': '✓ Computed math expression'})}\n\n"

        except Exception as e:
            logger.error(f"Error gathering context for stream: {e}")
            fallback_answer = (
                "## I hit a temporary issue while assembling the full analysis\n"
                "- Try asking the question again in a moment."
            )
            yield f"data: {json.dumps({'type': 'content', 'text': fallback_answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'payload': {'answer': fallback_answer, 'caveat': self._default_caveat()}})}\n\n"
            return

        profile = state.get("user_profile") or {}
        missing_fields = profile.get("missing_fields", [])
        intent = state.get("intent", "education")
        session_id = state.get("session_id") or f"default::{user_id}"

        if intent == "invest_plan" and missing_fields:
            questions = []
            if "risk_appetite" in missing_fields:
                questions.append("What is your risk appetite: conservative, moderate, or aggressive?")
            if "time_horizon" in missing_fields:
                questions.append("What is your investment horizon: short term, medium term, or long term?")
            if "investment_goal" in missing_fields:
                questions.append("What is the main goal for this investment: wealth creation, retirement, income, or balanced growth?")
            if "monthly_investment_budget" in missing_fields:
                questions.append("What budget should I anchor the plan around?")

            answer = "## Before I draft a portfolio plan\n"
            answer += "I need a little more context so the allocation is suitable rather than generic.\n\n"
            answer += "\n".join(f"{idx + 1}. {question}" for idx, question in enumerate(questions[:3]))
            
            payload = {
                "answer": answer,
                "caveat": self._default_caveat(),
                "evidence": [],
                "next_steps": questions[:3],
            }
            yield f"data: {json.dumps({'type': 'content', 'text': answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'payload': payload})}\n\n"
            
            if not temporary:
                try:
                    self._save_chat_to_db(db, user_id, session_id, query, answer)
                    self._record_chat_token_usage(
                        db,
                        session_id,
                        state.get("prompt_tokens", 0),
                        state.get("completion_tokens", 0),
                        state.get("total_tokens", 0)
                    )
                except Exception as save_err:
                    logger.error(f"Failed to save clarification to DB: {save_err}")
            return

        strategist_prompt, model = self._get_strategist_prompt_and_model(intent, state)

        try:
            response_stream = model.astream(strategist_prompt)
            
            buffer = ""
            state_search = "SEARCHING"
            escaped = False
            yielded_any = False
            full_raw = ""
            streamed_answer_buffer = ""
            prefix_cleaned = False

            stream_usage = None
            async for chunk in response_stream:
                text = self._extract_text(chunk)
                if not text:
                    continue
                
                # Check for usage metadata
                chunk_usage = getattr(chunk, "response_metadata", {}).get("usage_metadata")
                if chunk_usage:
                    stream_usage = chunk_usage
                
                full_raw += text
                buffer += text
                
                if state_search == "SEARCHING":
                    match = re.search(r'"answer"\s*:\s*"', buffer)
                    if match:
                        start_idx = match.end()
                        state_search = "STREAMING"
                        remaining = buffer[start_idx:]
                        
                        chunk_out = ""
                        for char in remaining:
                            if state_search == "STREAMING":
                                if escaped:
                                    if char == 'n': chunk_out += '\n'
                                    elif char == 't': chunk_out += '\t'
                                    elif char == 'r': chunk_out += '\r'
                                    elif char == 'b': chunk_out += '\b'
                                    elif char == 'f': chunk_out += '\f'
                                    elif char == '\\': chunk_out += '\\'
                                    elif char == '"': chunk_out += '"'
                                    else: chunk_out += '\\' + char
                                    escaped = False
                                elif char == '\\':
                                    escaped = True
                                elif char == '"':
                                    state_search = "FINISHED"
                                else:
                                    chunk_out += char
                        if chunk_out:
                            yielded_any = True
                            softened_chunk = self._soften_investment_language(chunk_out)
                            if not prefix_cleaned:
                                streamed_answer_buffer += softened_chunk
                                if len(streamed_answer_buffer) > 150 or "\n" in streamed_answer_buffer or state_search == "FINISHED":
                                    cleaned = self._clean_response_prefix(streamed_answer_buffer)
                                    yield f"data: {json.dumps({'type': 'content', 'text': cleaned})}\n\n"
                                    prefix_cleaned = True
                                    streamed_answer_buffer = ""
                            else:
                                yield f"data: {json.dumps({'type': 'content', 'text': softened_chunk})}\n\n"
                
                elif state_search == "STREAMING":
                    chunk_out = ""
                    for char in text:
                        if state_search == "STREAMING":
                            if escaped:
                                if char == 'n': chunk_out += '\n'
                                elif char == 't': chunk_out += '\t'
                                elif char == 'r': chunk_out += '\r'
                                elif char == 'b': chunk_out += '\b'
                                elif char == 'f': chunk_out += '\f'
                                elif char == '\\': chunk_out += '\\'
                                elif char == '"': chunk_out += '"'
                                else: chunk_out += '\\' + char
                                escaped = False
                            elif char == '\\':
                                escaped = True
                            elif char == '"':
                                state_search = "FINISHED"
                            else:
                                chunk_out += char
                    if chunk_out:
                        yielded_any = True
                        softened_chunk = self._soften_investment_language(chunk_out)
                        if not prefix_cleaned:
                            streamed_answer_buffer += softened_chunk
                            if len(streamed_answer_buffer) > 150 or "\n" in streamed_answer_buffer or state_search == "FINISHED":
                                cleaned = self._clean_response_prefix(streamed_answer_buffer)
                                yield f"data: {json.dumps({'type': 'content', 'text': cleaned})}\n\n"
                                prefix_cleaned = True
                                streamed_answer_buffer = ""
                        else:
                            yield f"data: {json.dumps({'type': 'content', 'text': softened_chunk})}\n\n"

            if not prefix_cleaned and streamed_answer_buffer:
                cleaned = self._clean_response_prefix(streamed_answer_buffer)
                yield f"data: {json.dumps({'type': 'content', 'text': cleaned})}\n\n"
                prefix_cleaned = True

            payload = {}
            try:
                payload = self._clean_and_parse_json(full_raw)
            except Exception as parse_err:
                logger.error(f"Failed to parse streamed response to JSON: {parse_err}")
                cleaned_raw = full_raw.strip()
                if cleaned_raw.startswith("```"):
                    cleaned_raw = re.sub(r"^```[a-zA-Z]*\n|```$", "", cleaned_raw, flags=re.MULTILINE).strip()
                
                # Proactively try to extract the "answer" field using regex to avoid leaking JSON format to users
                answer_match = re.search(r'"answer"\s*:\s*"(.*?)"(?=\s*,\s*"\w+"\s*:|\s*\})', cleaned_raw, re.DOTALL)
                extracted_answer = ""
                if answer_match:
                    escaped_str = answer_match.group(1)
                    try:
                        extracted_answer = json.loads(f'"{escaped_str}"')
                    except Exception:
                        extracted_answer = escaped_str.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                
                if not extracted_answer:
                    # Simple fallback match
                    answer_match_simple = re.search(r'"answer"\s*:\s*"(.*)"', cleaned_raw, re.DOTALL)
                    if answer_match_simple:
                        val = answer_match_simple.group(1)
                        metadata_start = val.find('",\n')
                        if metadata_start == -1:
                            metadata_start = val.find('",')
                        if metadata_start != -1:
                            val = val[:metadata_start]
                        try:
                            extracted_answer = json.loads(f'"{val}"')
                        except Exception:
                            extracted_answer = val.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                
                payload = {
                    "answer": extracted_answer or cleaned_raw,
                    "caveat": self._default_caveat(),
                    "evidence": [],
                    "next_steps": [],
                }

            payload.setdefault("answer", "")
            payload.setdefault("caveat", self._default_caveat())
            payload.setdefault("evidence", [])
            payload.setdefault("next_steps", [])

            payload["answer"] = self._clean_response_prefix(self._soften_investment_language(payload["answer"]))
            payload["caveat"] = self._soften_investment_language(payload["caveat"])
            payload["evidence"] = [self._soften_investment_language(item) for item in payload["evidence"]]
            payload["next_steps"] = [self._soften_investment_language(item) for item in payload["next_steps"]]

            if not yielded_any:
                yield f"data: {json.dumps({'type': 'content', 'text': payload['answer']})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'payload': payload})}\n\n"

            # Calculate stream tokens
            if not stream_usage:
                est_prompt = len(str(strategist_prompt)) // 4
                est_completion = len(full_raw) // 4
                stream_tokens = {
                    "prompt_tokens": est_prompt,
                    "completion_tokens": est_completion,
                    "total_tokens": est_prompt + est_completion
                }
            else:
                stream_tokens = self._extract_token_usage(stream_usage)

            # Total tokens for this turn
            total_prompt = state.get("prompt_tokens", 0) + stream_tokens["prompt_tokens"]
            total_completion = state.get("completion_tokens", 0) + stream_tokens["completion_tokens"]
            total_total = state.get("total_tokens", 0) + stream_tokens["total_tokens"]

            if not temporary:
                try:
                    self._save_chat_to_db(db, user_id, session_id, query, payload["answer"])
                    self._record_chat_token_usage(db, session_id, total_prompt, total_completion, total_total)
                    self.extract_and_store_memory(db, user_id, query)
                except Exception as db_err:
                    logger.error(f"Failed to save streamed chat message to DB: {db_err}")

        except Exception as err:
            logger.error(f"Strategist streaming failed: {err}")
            fallback_answer = "I hit a temporary issue while assembling the full analysis. Please try again."
            yield f"data: {json.dumps({'type': 'content', 'text': fallback_answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'payload': {'answer': fallback_answer, 'caveat': self._default_caveat()}})}\n\n"

    def _save_chat_to_db(self, db: Session, user_id: str, session_id: str, query: str, answer: str) -> None:
        from app.models.chat import ChatMessage
        now = datetime.now(timezone.utc)
        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            content=query,
            created_at=now,
        )
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=answer,
            created_at=now,
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()

insights_engine = InsightsEngine()
