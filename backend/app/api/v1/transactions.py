import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionResponse, TransactionUpdate
from app.services.market_data_service import market_data_service
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("", response_model=List[TransactionResponse])
def get_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        from app.core.cache import cache_manager
        from fastapi.encoders import jsonable_encoder

        cache_key = f"user_cache:{current_user.id}:transactions"
        cached = cache_manager.get(cache_key)
        if cached is not None:
            return cached

        txs = (
            db.query(Transaction)
            .filter(Transaction.user_id == current_user.id)
            .order_by(Transaction.executed_at.desc())
            .all()
        )
        cache_manager.set(cache_key, jsonable_encoder(txs), ttl=300)
        return txs
    except Exception as e:
        logger.error(f"Failed to fetch transactions for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch transactions: {e}"
        )

@router.post("", response_model=TransactionResponse)
def create_transaction(
    tx_in: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        tx_data = tx_in.model_dump()
        symbol = tx_data["symbol"].upper().strip()
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
        tx_data["symbol"] = symbol
        
        # Auto-populate company name if missing
        if not tx_data.get("company_name"):
            tx_data["company_name"] = market_data_service.get_company_name(symbol)
            
        db_tx = Transaction(user_id=current_user.id, **tx_data)
        db.add(db_tx)
        db.commit()
        db.refresh(db_tx)
        
        # Chronological Rebuild Trigger
        
        from app.core.cache import cache_manager
        cache_manager.invalidate_user_cache(current_user.id)
        logger.info(f"Successfully created transaction for user {current_user.id}")
        
        return db_tx
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create transaction for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create transaction: {e}"
        )

@router.put("/{tx_id}", response_model=TransactionResponse)
def update_transaction(
    tx_id: int,
    tx_in: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        db_tx = (
            db.query(Transaction)
            .filter(Transaction.id == tx_id, Transaction.user_id == current_user.id)
            .first()
        )
        if not db_tx:
            logger.warning(f"Transaction {tx_id} not found for update by user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
            
        # Capture old execution date
        old_executed_at = db_tx.executed_at
        
        tx_data = tx_in.model_dump(exclude_unset=True)
        if "symbol" in tx_data:
            symbol = tx_data["symbol"].upper().strip()
            if not symbol.endswith(".NS"):
                symbol = f"{symbol}.NS"
            tx_data["symbol"] = symbol
            # Update company name as well if changed
            if not tx_data.get("company_name"):
                tx_data["company_name"] = market_data_service.get_company_name(symbol)
                
        for key, value in tx_data.items():
            setattr(db_tx, key, value)
            
        db.commit()
        db.refresh(db_tx)
        
        # Chronological Rebuild Trigger using the earliest target date
        from_date = min(db_tx.executed_at, old_executed_at)
        
        from app.core.cache import cache_manager
        cache_manager.invalidate_user_cache(current_user.id)
        logger.info(f"Successfully updated transaction {tx_id} for user {current_user.id}")
        
        return db_tx
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update transaction {tx_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update transaction: {e}"
        )

@router.delete("/{tx_id}")
def delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        db_tx = (
            db.query(Transaction)
            .filter(Transaction.id == tx_id, Transaction.user_id == current_user.id)
            .first()
        )
        if not db_tx:
            logger.warning(f"Transaction {tx_id} not found for deletion by user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
        
        old_executed_at = db_tx.executed_at
        
        db.delete(db_tx)
        db.commit()
        
        # Chronological Rebuild Trigger
        
        from app.core.cache import cache_manager
        cache_manager.invalidate_user_cache(current_user.id)
        logger.info(f"Successfully deleted transaction {tx_id} for user {current_user.id}")
        
        return {"message": "Transaction deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete transaction {tx_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete transaction: {e}"
        )
