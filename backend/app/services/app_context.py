import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.llm import flash_lite_model, flash_model, pro_model
from app.utils.parsing import extract_text, clean_and_parse_json, extract_token_usage
from app.services.review_agent import ReviewAgent
from app.services.copilot_agent import CopilotAgent

logger = logging.getLogger(__name__)


class AppContext:
    """Composition root that wires models, services, and agents together."""

    def __init__(self):
        # Models
        self.flash_lite_model = flash_lite_model
        self.flash_model = flash_model
        self.pro_model = pro_model

        # FIX: Pass flash_lite_model for query refactoring, flash_model for cheap
        # tool-routing passes. Pro model is still used for final answer synthesis.
        self.copilot_agent = CopilotAgent(
            pro_model=self.pro_model,
            flash_model=self.flash_model,
            flash_lite_model=self.flash_lite_model,
        )

        # ReviewAgent still receives self for backward compatibility
        self.review_agent = ReviewAgent(self)

    # ── Utility pass-throughs (used by ReviewAgent) ────────────────────────

    def _extract_text(self, result: Any) -> str:
        return extract_text(result)

    def _clean_and_parse_json(self, raw_text: str) -> Any:
        return clean_and_parse_json(raw_text)

    def _extract_token_usage(self, result: Any) -> Dict[str, int]:
        return extract_token_usage(result)

    # ── Public API ─────────────────────────────────────────────────────────

    def generate_review(self, db: Session, user_id: str) -> Dict[str, Any]:
        return self.review_agent.generate_review(db, user_id)

    def generate_watchlist_recommendations(self, db: Session, user_id: str) -> List[Dict[str, Any]]:
        return self.review_agent.generate_watchlist_recommendations(db, user_id)

    def ask_copilot(
        self,
        db: Session,
        user_id: str,
        query: str,
        temporary: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.copilot_agent.ask_copilot(db, user_id, query, temporary, session_id)

    async def ask_copilot_stream(
        self,
        db: Session,
        user_id: str,
        query: str,
        temporary: bool = False,
        session_id: Optional[str] = None,
    ):
        async for chunk in self.copilot_agent.ask_copilot_stream(
            db, user_id, query, temporary, session_id
        ):
            yield chunk


app_context = AppContext()