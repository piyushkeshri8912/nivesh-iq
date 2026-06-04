import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from app.db.session import get_db
from app.models.user import User
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

import time
LAST_CLEANUP_TIME = 0.0

def cleanup_expired_guests(db: Session) -> None:
    from datetime import datetime, timedelta, timezone
    try:
        # Find guests created more than 24 hours ago
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        
        expired_guests = db.execute(text(
            "SELECT id, email FROM public.users WHERE email LIKE 'guest_%@niveshiq.guest' AND created_at < :cutoff"
        ), {"cutoff": cutoff}).fetchall()
        
        if not expired_guests:
            return
            
        logger.info(f"[CLEANUP] Found {len(expired_guests)} expired guest accounts to purge.")
        for guest in expired_guests:
            guest_id = guest[0]
            guest_email = guest[1]
            
            # Delete user memories
            db.execute(text("DELETE FROM public.user_memories WHERE user_id = :user_id"), {"user_id": guest_id})
            
            # Delete chat messages and sessions
            db.execute(text(
                "DELETE FROM public.chat_messages WHERE session_id IN (SELECT id FROM public.chat_sessions WHERE user_id = :user_id)"
            ), {"user_id": guest_id})
            db.execute(text("DELETE FROM public.chat_sessions WHERE user_id = :user_id"), {"user_id": guest_id})
            
            # Delete other user-related data
            db.execute(text("DELETE FROM public.transactions WHERE user_id = :user_id"), {"user_id": guest_id})
            db.execute(text("DELETE FROM public.watchlist_items WHERE user_id = :user_id"), {"user_id": guest_id})
            db.execute(text("DELETE FROM public.portfolio_reviews WHERE user_id = :user_id"), {"user_id": guest_id})
            db.execute(text("DELETE FROM public.user_profiles WHERE user_id = :user_id"), {"user_id": guest_id})
            
            # Delete local user record
            db.execute(text("DELETE FROM public.users WHERE id = :user_id"), {"user_id": guest_id})
            
            # Delete Neon Auth credentials if it's a valid UUID
            is_uuid = False
            try:
                import uuid
                uuid.UUID(guest_id)
                is_uuid = True
            except ValueError:
                pass
                
            if is_uuid:
                db.execute(text("DELETE FROM neon_auth.session WHERE \"userId\" = CAST(:user_id AS uuid)"), {"user_id": guest_id})
                db.execute(text("DELETE FROM neon_auth.account WHERE \"userId\" = CAST(:user_id AS uuid)"), {"user_id": guest_id})
                db.execute(text("DELETE FROM neon_auth.user WHERE id = CAST(:user_id AS uuid)"), {"user_id": guest_id})
            
            logger.info(f"[CLEANUP] Successfully purged expired guest: {guest_email}")
            
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[CLEANUP ERROR] Failed to delete expired guest accounts: {e}", exc_info=True)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    global LAST_CLEANUP_TIME
    
    # 1. Throttled cleanup of expired guest accounts (at most once every 10 mins)
    now_time = time.time()
    if now_time - LAST_CLEANUP_TIME > 600:
        LAST_CLEANUP_TIME = now_time
        cleanup_expired_guests(db)

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not credentials or not credentials.credentials:
        raise credentials_exception

    email = credentials.credentials

    # We just retrieve the user with this email from the database!
    user = db.query(User).filter(User.email == email).first()
    if not user:
        try:
            # Query neon_auth."user" by email to get the authentic Neon Auth UUID
            auth_user = db.execute(
                text('SELECT id FROM neon_auth."user" WHERE email = :email'),
                {"email": email}
            ).fetchone()
            
            # Fallback to email as ID if not found in neon_auth table (e.g. mock demo sessions)
            uuid_id = auth_user[0] if auth_user else email

            # Auto-create the user record in local tables if it doesn't exist
            user = User(
                id=uuid_id,
                email=email,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            profile = UserProfile(
                user_id=user.id,
                full_name=email.split("@")[0].capitalize(),
                risk_appetite="MODERATE",
                time_horizon="MEDIUM_TERM",
                investment_goal="BALANCED"
            )
            db.add(profile)
            db.commit()
            db.refresh(user)
            logger.info(f"[AUTH SYNC] Successfully auto-onboarded user: {email} (Local ID: {user.id})")
        except Exception as sync_err:
            db.rollback()
            logger.error(f"[AUTH SYNC ERROR] Failed to map user {email}: {sync_err}", exc_info=True)
            raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    return user
