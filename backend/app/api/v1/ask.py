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
from app.services.insights_engine import insights_engine

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
        generator = insights_engine.ask_copilot_stream(
            db, current_user.id, request.query, temporary=request.temporary, session_id=request.session_id
        )
        return StreamingResponse(generator, media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Ask Copilot query failed for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ask Copilot query failed: {e}"
        )

@router.get("/sessions")
async def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve all chat sessions for the current user, generating a dynamic title from the first user message.
    """
    from app.models.chat import ChatSession, ChatMessage
    try:
        sessions = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == current_user.id)
            .order_by(ChatSession.last_message_at.desc())
            .all()
        )
        
        results = []
        for s in sessions:
            first_msg = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == s.id, ChatMessage.role == "user")
                .order_by(ChatMessage.created_at.asc())
                .first()
            )
            title = first_msg.content[:40] if first_msg else "New Chat"
            if first_msg and len(first_msg.content) > 40:
                title += "..."
            
            results.append({
                "id": s.id,
                "title": title,
                "created_at": s.created_at.isoformat(),
                "last_message_at": s.last_message_at.isoformat()
            })
        return results
    except Exception as e:
        logger.error(f"Failed to fetch chat sessions for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch chat sessions: {e}"
        )

@router.post("/sessions")
async def create_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Explicitly create a new chat session.
    """
    from app.models.chat import ChatSession
    try:
        new_session = ChatSession(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            created_at=datetime.now(timezone.utc),
            last_message_at=datetime.now(timezone.utc),
        )
        db.add(new_session)
        db.commit()
        logger.info(f"Created new chat session {new_session.id} for user {current_user.id}")
        return {"session_id": new_session.id}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create chat session for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create chat session: {e}"
        )

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve all messages in a specific chat session for the current user.
    """
    from app.models.chat import ChatSession, ChatMessage
    try:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        ).first()
        if not session:
            logger.warning(f"User {current_user.id} attempted to fetch non-existent session {session_id}")
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return [{
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat()
        } for m in messages]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch session messages for session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch session messages: {e}"
        )

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a specific chat session and all cascading messages.
    """
    from app.models.chat import ChatSession
    try:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        ).first()
        if not session:
            logger.warning(f"User {current_user.id} attempted to delete non-existent session {session_id}")
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        db.delete(session)
        db.commit()
        logger.info(f"Deleted chat session {session_id} for user {current_user.id}")
        return {"message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {e}"
        )
