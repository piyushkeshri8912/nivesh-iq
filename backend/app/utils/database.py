import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def record_chat_token_usage(
    db: Session,
    session_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int
) -> None:
    """
    Log token metrics for a chat session into the database.
    """
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


def save_chat_to_db(
    db: Session,
    user_id: str,
    session_id: str,
    query: str,
    answer: str
) -> None:
    """
    Save chat history user/assistant messages to database.
    """
    try:
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
        logger.info(f"Saved query and answer to database for chat session {session_id}")
    except Exception as e:
        logger.error(f"Failed to save chat message history: {e}")
        db.rollback()
