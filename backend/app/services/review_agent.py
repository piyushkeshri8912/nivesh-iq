import json
import logging
import concurrent.futures
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.portfolio_review import PortfolioReview
from app.services.tools import TOOLS
from app.utils.parsing import extract_text, clean_and_parse_json, extract_token_usage

logger = logging.getLogger(__name__)

_DEFAULT_CAVEAT = (
    "This is an automated analysis for informational purposes only, and does not constitute "
    "personalized investment advice from a registered investment adviser. Please consult a "
    "SEBI-registered adviser before acting."
)

class ReviewAgent:
    def __init__(self, app_context):
        self.app_context = app_context
        self._pro = app_context.pro_model
        self._flash_lite = app_context.flash_lite_model

    @staticmethod
    def _run_single_tool(tc: Dict, db: Session, user_id: str) -> tuple:
        """Execute one LangChain tool call and return (name, data)."""
        name = tc.get("name", "")
        args = dict(tc.get("args", {}))
        tool_map = {t.name: t for t in TOOLS}
        t_obj = tool_map.get(name)
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(tool_calls))) as pool:
            futures = {pool.submit(self._run_single_tool, tc, db, user_id): tc for tc in tool_calls}
            results = {}
            for future in concurrent.futures.as_completed(futures):
                name, data = future.result()
                results[name] = data
        return results

    def generate_review(self, db: Session, user_id: str) -> Dict[str, Any]:
        from app.services.prompts import ANALYST_PROMPT

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")

        # Build initial prompt
        prompt = ANALYST_PROMPT.format(current_time=now_str, user_id=user_id)


        tool_results = {}
        max_iterations = 3
        model = self._pro.bind_tools(TOOLS)
        
        # Token usage tracking
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        last_result = None
        for i in range(max_iterations):
            if tool_results:
                blocks = [f"=== TOOL RESULT: {name} ===\n{json.dumps(data, indent=2)}" for name, data in tool_results.items()]
                context = "\n\n".join(blocks)
                prompt_with_context = f"{prompt}\n\n=== GATHERED CONTEXT ===\n{context}"
            else:
                prompt_with_context = prompt

            last_result = model.invoke(prompt_with_context)
            
            usage = extract_token_usage(last_result)
            prompt_tokens += usage.get("prompt_tokens", 0)
            completion_tokens += usage.get("completion_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)

            tool_calls = getattr(last_result, "tool_calls", [])
            if not tool_calls:
                break
            
            new_results = self._execute_tool_calls(tool_calls, db, user_id)
            tool_results.update(new_results)

        else:
            blocks = [f"=== TOOL RESULT: {name} ===\n{json.dumps(data, indent=2)}" for name, data in tool_results.items()]
            context = "\n\n".join(blocks)
            prompt_with_context = f"{prompt}\n\n=== GATHERED CONTEXT ===\n{context}"
            last_result = self._pro.invoke(prompt_with_context)
            
            usage = extract_token_usage(last_result)
            prompt_tokens += usage.get("prompt_tokens", 0)
            completion_tokens += usage.get("completion_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)

        # Parse structured JSON output
        raw_text = extract_text(last_result)
        payload = clean_and_parse_json(raw_text)

        if not isinstance(payload, dict):
            logger.warning(f"Parsed payload is not a dict (type: {type(payload)}). Falling back to structured default.")
            payload = {}

        # Safe extraction with defaults
        portfolio_summary = payload.get("portfolio_summary", {})
        if not isinstance(portfolio_summary, dict):
            portfolio_summary = {}

        current_value = portfolio_summary.get("current_value", "N/A")
        total_pnl = portfolio_summary.get("total_pnl", "N/A")
        total_pnl_percent = portfolio_summary.get("total_pnl_percent", "N/A")
        analysis = portfolio_summary.get("analysis", "No strategic analysis available.")

        summary_stats = {
            "current_value": current_value,
            "total_pnl": total_pnl,
            "total_pnl_percent": total_pnl_percent
        }

        holdings_analysis = payload.get("holdings_analysis", [])
        if not isinstance(holdings_analysis, list):
            holdings_analysis = []

        rebalancing_plan = payload.get("rebalancing_plan", {})
        if not isinstance(rebalancing_plan, dict):
            rebalancing_plan = {}
        objective = rebalancing_plan.get("objective", "")
        steps = rebalancing_plan.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        rebalancing_ideas = []
        if objective:
            rebalancing_ideas.append({
                "action": "OBJECTIVE",
                "symbol": None,
                "details": objective
            })
        for step in steps:
            if isinstance(step, dict):
                rebalancing_ideas.append({
                    "action": step.get("action", "REINVEST"),
                    "symbol": step.get("symbol"),
                    "details": step.get("details", "")
                })

        future_scenarios = payload.get("future_scenarios", {})
        if not isinstance(future_scenarios, dict):
            future_scenarios = {}
        # Ensure all three keys exist
        future_scenarios.setdefault("bull_case", "")
        future_scenarios.setdefault("base_case", "")
        future_scenarios.setdefault("bear_case", "")

        news_updates = payload.get("news_updates", [])
        if not isinstance(news_updates, list):
            news_updates = []

        caveat = payload.get("caveat", _DEFAULT_CAVEAT)

        # Create model in DB
        review_obj = PortfolioReview(
            user_id=user_id,
            risk_summary=analysis,
            diversification_summary=json.dumps(summary_stats),
            rebalancing_ideas=rebalancing_ideas,
            potential_stock_picks=holdings_analysis,
            warnings=[],
            market_impact=json.dumps(future_scenarios),
            evidence={"news_updates": news_updates},
            disclaimers=caveat,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens
        )
        db.add(review_obj)
        db.commit()
        db.refresh(review_obj)

        return review_obj

    def generate_watchlist_recommendations(self, db: Session, user_id: str) -> List[Dict[str, Any]]:
        return []
