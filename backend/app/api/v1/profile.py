import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.profile import UserProfileCreate, UserProfileResponse
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("", response_model=UserProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        from app.core.cache import cache_manager
        from fastapi.encoders import jsonable_encoder

        cache_key = f"user_cache:{current_user.id}:profile"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
        if not profile:
            logger.warning(f"Profile not found for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        cache_manager.set(cache_key, jsonable_encoder(profile), ttl=600) # Profile changes rarely, 10 min cache
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch profile for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch profile: {e}"
        )

@router.post("", response_model=UserProfileResponse)
def upsert_profile(
    profile_in: UserProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
        profile_data = profile_in.model_dump()
        
        if profile:
            # Update existing profile
            for key, value in profile_data.items():
                setattr(profile, key, value)
        else:
            # Create new profile
            profile = UserProfile(user_id=current_user.id, **profile_data)
            db.add(profile)
            
        db.commit()
        db.refresh(profile)

        from app.core.cache import cache_manager
        cache_manager.invalidate_user_cache(current_user.id)
        logger.info(f"Successfully upserted profile for user {current_user.id}")

        return profile
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to upsert profile for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upsert profile: {e}"
        )


@router.delete("/delete-account")
def delete_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from sqlalchemy import text
    import uuid
    try:
        user_id = current_user.id
        email = current_user.email
        
        # 1. Delete user memories
        db.execute(text("DELETE FROM public.user_memories WHERE user_id = :user_id"), {"user_id": user_id})
        
        # 2. Delete chat messages and sessions
        db.execute(text(
            "DELETE FROM public.chat_messages WHERE session_id IN (SELECT id FROM public.chat_sessions WHERE user_id = :user_id)"
        ), {"user_id": user_id})
        db.execute(text("DELETE FROM public.chat_sessions WHERE user_id = :user_id"), {"user_id": user_id})
        
        # 3. Delete other user-related data
        db.execute(text("DELETE FROM public.transactions WHERE user_id = :user_id"), {"user_id": user_id})
        db.execute(text("DELETE FROM public.watchlist_items WHERE user_id = :user_id"), {"user_id": user_id})
        db.execute(text("DELETE FROM public.portfolio_reviews WHERE user_id = :user_id"), {"user_id": user_id})
        db.execute(text("DELETE FROM public.user_profiles WHERE user_id = :user_id"), {"user_id": user_id})
        
        # 4. Delete local user record
        db.execute(text("DELETE FROM public.users WHERE id = :user_id"), {"user_id": user_id})
        
        # 5. Delete Neon Auth credentials and session records if it's a valid UUID
        is_uuid = False
        try:
            uuid.UUID(user_id)
            is_uuid = True
        except ValueError:
            pass

        if is_uuid:
            db.execute(text("DELETE FROM neon_auth.session WHERE \"userId\" = CAST(:user_id AS uuid)"), {"user_id": user_id})
            db.execute(text("DELETE FROM neon_auth.account WHERE \"userId\" = CAST(:user_id AS uuid)"), {"user_id": user_id})
            db.execute(text("DELETE FROM neon_auth.user WHERE id = CAST(:user_id AS uuid)"), {"user_id": user_id})
        
        db.commit()
        logger.info(f"[ACCOUNT DELETE] Successfully deleted user: {email} (ID: {user_id}) and all associated data.")
        return {"message": "Account successfully deleted."}
    except Exception as e:
        db.rollback()
        logger.error(f"[ACCOUNT DELETE ERROR] Failed to delete user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )
