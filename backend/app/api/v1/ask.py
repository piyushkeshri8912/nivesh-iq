import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user, check_guest_token_limit
from app.schemas.ask import AskRequest
from app.services.app_context import app_context

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("")
async def ask_copilot(
    request: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute conversational portfolio copilot queries grounded in real context and stream response back.
    Supports temporary (incognito) mode where no memories are saved.
    """
    # Enforce guest user token limit
    check_guest_token_limit(db, current_user)

    try:
        generator = app_context.ask_copilot_stream(
            db, current_user.id, request.query, temporary=request.temporary, session_id=request.session_id
        )
        return StreamingResponse(generator, media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Ask Copilot query failed for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ask Copilot query failed: {e}"
        )

@router.get("/session")
async def get_or_create_active_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the single active chat session for the current user.
    Creates one automatically if it does not exist.
    """
    from app.models.chat import ChatSession, ChatMessage
    try:
        session = db.query(ChatSession).filter(ChatSession.user_id == current_user.id).first()
        if not session:
            session = ChatSession(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                created_at=datetime.now(timezone.utc),
                last_message_at=datetime.now(timezone.utc),
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            logger.info(f"Auto-created single chat session {session.id} for user {current_user.id}")

        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return {
            "session_id": session.id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat()
                } for m in messages
            ]
        }
    except Exception as e:
        logger.error(f"Failed to fetch active chat session for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch active chat session: {e}"
        )

@router.delete("/session/clear")
async def clear_active_session_messages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Clear all message history in the single active session for the current user.
    """
    from app.models.chat import ChatSession, ChatMessage
    try:
        session = db.query(ChatSession).filter(ChatSession.user_id == current_user.id).first()
        if session:
            db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
            db.commit()
            logger.info(f"Cleared chat messages for user {current_user.id} session {session.id}")
        return {"message": "Chat history cleared successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear active session for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear chat history: {e}"
        )
