import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
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
        from app.services.portfolio_history_service import portfolio_history_service
        try:
            portfolio_history_service.rebuild_history(db, current_user.id, from_date=db_tx.executed_at, force=True)
        except Exception as rebuild_err:
            logger.error(f"Failed to rebuild portfolio history on creation: {rebuild_err}")
        
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
        from app.services.portfolio_history_service import portfolio_history_service
        try:
            portfolio_history_service.rebuild_history(db, current_user.id, from_date=from_date, force=True)
        except Exception as rebuild_err:
            logger.error(f"Failed to rebuild portfolio history on update: {rebuild_err}")
        
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
        from app.services.portfolio_history_service import portfolio_history_service
        try:
            portfolio_history_service.rebuild_history(db, current_user.id, from_date=old_executed_at, force=True)
        except Exception as rebuild_err:
            logger.error(f"Failed to rebuild portfolio history on deletion: {rebuild_err}")
        
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


# ---------------------------------------------------------------------------
# Bulk Upload via CSV / XLSX
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

@router.post("/upload")
async def upload_trades(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Parse and bulk-import trades from a CSV or XLSX file.

    - Accepts files up to 10 MB.
    - Columns are mapped automatically using the LLM (with rule-based fallback).
    - No file is persisted to disk.
    - Returns a summary: { imported, skipped, errors }.
    """
    # --- Validate MIME type ---
    allowed_types = {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",  # some browsers use this for xlsx
    }
    content_type = (file.content_type or "").lower()
    filename = file.filename or ""
    if not (
        content_type in allowed_types
        or filename.lower().endswith((".csv", ".xlsx", ".xls"))
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and XLSX files are accepted.",
        )

    # --- Read file bytes ---
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 10 MB limit ({len(file_bytes) // (1024*1024)} MB received).",
        )

    # --- Parse & extract trades using LLM-assisted column mapping ---
    try:
        from app.services.trade_upload_service import extract_trades
        valid_trades, parse_errors = extract_trades(file_bytes, filename)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except Exception as e:
        logger.error(f"Trade file parsing failed for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse trade file: {e}",
        )

    if not valid_trades:
        return {
            "imported": 0,
            "skipped": len(parse_errors),
            "duplicates": 0,
            "errors": parse_errors,
            "message": "No valid trades found in file.",
        }

    # --- Pre-build fingerprint set from existing transactions (single query) ---
    # Fingerprint: (symbol, transaction_type, quantity, price, date_str)
    # Using date-only string for the comparison to tolerate minor time-of-day differences
    existing_txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .all()
    )

    def _tx_fingerprint(symbol: str, tx_type: str, qty: float, price: float, executed_at) -> str:
        date_str = executed_at.strftime("%Y-%m-%d") if executed_at else "no-date"
        return f"{symbol}|{tx_type}|{qty}|{round(price, 2)}|{date_str}"

    existing_fingerprints: set[str] = set()
    for ex in existing_txs:
        existing_fingerprints.add(
            _tx_fingerprint(ex.symbol, ex.transaction_type, ex.quantity, ex.price, ex.executed_at)
        )

    # --- Bulk insert with duplicate detection ---
    imported = 0
    duplicates = 0
    insert_errors: list[str] = []
    earliest_date = None
    # Track fingerprints we're about to insert (handles duplicate rows within the same file)
    staged_fingerprints: set[str] = set()

    for trade in valid_trades:
        try:
            symbol = trade["symbol"].upper().strip()
            if not symbol.endswith(".NS") and "." not in symbol:
                symbol = f"{symbol}.NS"

            executed_at = None
            if trade.get("executed_at"):
                try:
                    executed_at = datetime.fromisoformat(trade["executed_at"])
                except Exception:
                    executed_at = None

            fp = _tx_fingerprint(symbol, trade["transaction_type"], trade["quantity"], trade["price"], executed_at)

            # Skip if already in DB or already staged in this batch
            if fp in existing_fingerprints or fp in staged_fingerprints:
                duplicates += 1
                logger.debug(f"Skipping duplicate trade: {fp}")
                continue

            company_name = market_data_service.get_company_name(symbol)

            db_tx = Transaction(
                user_id=current_user.id,
                symbol=symbol,
                company_name=company_name,
                transaction_type=trade["transaction_type"],
                quantity=trade["quantity"],
                price=trade["price"],
                fees=trade.get("fees", 0.0),
                executed_at=executed_at,
            )
            db.add(db_tx)
            staged_fingerprints.add(fp)

            if executed_at:
                if earliest_date is None or executed_at < earliest_date:
                    earliest_date = executed_at

            imported += 1
        except Exception as row_err:
            insert_errors.append(
                f"Failed to stage {trade.get('symbol', '?')}: {row_err}"
            )

    try:
        db.commit()
    except Exception as commit_err:
        db.rollback()
        logger.error(f"Bulk commit failed for user {current_user.id}: {commit_err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database commit failed: {commit_err}",
        )

    # --- Rebuild portfolio history from the earliest imported trade ---
    if imported > 0:
        from app.services.portfolio_history_service import portfolio_history_service
        try:
            rebuild_from = earliest_date or datetime.now(timezone.utc)
            portfolio_history_service.rebuild_history(
                db, current_user.id, from_date=rebuild_from, force=True
            )
        except Exception as rebuild_err:
            logger.error(f"History rebuild failed after bulk upload: {rebuild_err}")

        from app.core.cache import cache_manager
        cache_manager.invalidate_user_cache(current_user.id)

    all_errors = parse_errors + insert_errors

    if imported == 0 and duplicates > 0:
        message = f"All {duplicates} trade(s) already exist — nothing new was imported."
    elif duplicates > 0:
        message = f"Imported {imported} new trade(s). Skipped {duplicates} duplicate(s) already in your ledger."
    else:
        message = f"Successfully imported {imported} trade(s)."

    logger.info(
        f"Bulk upload for user {current_user.id}: {imported} imported, "
        f"{duplicates} duplicates, {len(all_errors)} errors from '{filename}'"
    )

    return {
        "imported": imported,
        "duplicates": duplicates,
        "skipped": len(parse_errors) + len(insert_errors),
        "errors": all_errors[:50],
        "message": message,
    }
