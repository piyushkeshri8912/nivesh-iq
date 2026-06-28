"""
Trade Upload Service
--------------------
Parses an in-memory CSV or XLSX file (as bytes) using pandas
and uses the LLM (Gemini via langchain-google-genai) to intelligently
map arbitrary column names to the internal Transaction schema.

Handles broker exports that contain metadata rows before the real header
(e.g. Zerodha, Groww, ICICI Direct, Upstox order history files).

No file is persisted to disk at any point.
"""

import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column mapping prompt
# ---------------------------------------------------------------------------

_COLUMN_MAPPING_PROMPT = """\
You are a financial data parser for Indian stock brokers.

The user uploaded a trade ledger. Below are the actual column headers found in the file.
Map each schema field to the best-matching column from the file.

Transaction schema fields:
  - symbol            (string, required)  — stock ticker / scrip symbol, e.g. "INFY", "RELIANCE"
  - transaction_type  (string, required)  — "BUY" or "SELL"
  - quantity          (float,  required)  — number of shares / units traded
  - price             (float,  optional)  — price PER SHARE at execution (may not exist)
  - total_value       (float,  optional)  — TOTAL trade value (quantity × price). Use if per-share price column is absent.
  - executed_at       (string, optional)  — trade date (ISO-8601 or common date format)
  - fees              (float,  optional)  — brokerage / commission paid

File columns: {columns}

Return ONLY a JSON object mapping each schema field to the exact column name from the file
that best matches it, or null if no match exists.

Example output:
{{
  "symbol": "Symbol",
  "transaction_type": "Type",
  "quantity": "Quantity",
  "price": null,
  "total_value": "Value",
  "executed_at": "Execution date and time",
  "fees": null
}}

Important rules:
  - Use ONLY column names that appear verbatim in the provided list.
  - "Value" / "Amount" / "Trade Value" usually means total value, NOT per-share price — map to total_value.
  - "Price" / "Rate" / "Trade Price" / "NAV" means per-share price — map to price.
  - If both exist, prefer price over total_value.
  - Output valid JSON and nothing else.
"""

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_type(raw: Any) -> str:
    """Convert various buy/sell representations to 'BUY' or 'SELL'."""
    if raw is None:
        return "BUY"
    s = str(raw).strip().upper()
    if s in {"BUY", "B", "PURCHASE", "1"}:
        return "BUY"
    if s in {"SELL", "S", "SALE", "-1"}:
        return "SELL"
    return "BUY"


def _normalise_symbol(raw: Any) -> Optional[str]:
    """Strip whitespace and ensure symbol is uppercase."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip().upper()
    return s if s else None


def _normalise_date(raw: Any) -> Optional[str]:
    """
    Try to parse a date cell into an ISO-8601 datetime string (UTC).
    Returns None if parsing fails.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=timezone.utc).isoformat()
    s = str(raw).strip()
    for fmt in (
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
        "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y",
        "%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _normalise_float(raw: Any) -> Optional[float]:
    """Convert to float; strip currency symbols and commas."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).replace(",", "").replace("₹", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Smart header detection
# ---------------------------------------------------------------------------

# Keywords that reliably indicate the real data header row
_HEADER_KEYWORDS = {
    "symbol", "ticker", "scrip", "stock name", "instrument",
    "quantity", "qty", "type", "buy/sell", "side",
    "price", "value", "amount", "date", "trade date", "execution date",
    "isin", "order id", "status", "exchange",
}

def _find_header_row(df_raw: pd.DataFrame) -> int:
    """
    Scan rows top-down and return the index of the row that most likely
    contains the real column headers (i.e. it contains recognisable field
    names rather than metadata strings or NaN).

    Returns 0 (use the native header) if no better row is found.
    """
    for row_idx in range(min(15, len(df_raw))):
        row_vals = [
            str(v).strip().lower()
            for v in df_raw.iloc[row_idx].values
            if v is not None and not (isinstance(v, float) and pd.isna(v))
        ]
        if not row_vals:
            continue
        hits = sum(1 for v in row_vals if any(kw in v for kw in _HEADER_KEYWORDS))
        if hits >= 2:
            logger.info(f"Auto-detected real header at row index {row_idx} ({hits} keyword hits)")
            return row_idx
    return -1   # sentinel: native header is correct


def parse_trade_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """
    Read CSV or XLSX bytes into a normalised DataFrame.

    Automatically detects and skips broker metadata rows that appear
    before the real column header (common in ICICI, Zerodha, Groww exports).
    """
    buf = io.BytesIO(file_bytes)

    # --- Read raw without assuming any header ---
    if filename.lower().endswith((".xlsx", ".xls")):
        df_raw = pd.read_excel(buf, engine="openpyxl", header=None)
    else:
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                buf.seek(0)
                df_raw = pd.read_csv(buf, encoding=enc, header=None)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Unable to decode CSV file — try UTF-8 or Latin-1 encoding.")

    header_row = _find_header_row(df_raw)

    if header_row == -1:
        # Native header was already correct; re-read normally
        buf.seek(0)
        if filename.lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(buf, engine="openpyxl")
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                buf.seek(0)
                return pd.read_csv(buf, encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("Unable to re-read CSV file.")

    # Use detected header row; skip everything above it
    new_header = [str(v).strip() for v in df_raw.iloc[header_row].values]
    df = df_raw.iloc[header_row + 1:].copy()
    df.columns = new_header
    df = df.reset_index(drop=True)

    # Drop rows that are entirely NaN (common trailing blank rows in Excel)
    df = df.dropna(how="all")

    return df


# ---------------------------------------------------------------------------
# LLM column mapping
# ---------------------------------------------------------------------------

def _llm_map_columns(columns: list[str]) -> dict[str, Optional[str]]:
    """Ask the LLM to map file columns to schema fields."""
    try:
        from app.core.llm import flash_lite_model
        from langchain_core.messages import HumanMessage

        prompt = _COLUMN_MAPPING_PROMPT.format(columns=columns)
        response = flash_lite_model.invoke([HumanMessage(content=prompt)])
        text = response.content.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(l for l in lines if not l.startswith("```"))

        mapping = json.loads(text)
        logger.info(f"LLM column mapping: {mapping}")
        return mapping
    except Exception as e:
        logger.error(f"LLM column mapping failed: {e}", exc_info=True)
        return _fallback_map_columns(columns)


def _fallback_map_columns(columns: list[str]) -> dict[str, Optional[str]]:
    """
    Rule-based fallback column mapper (case-insensitive keyword matching).
    Used when the LLM call fails.
    """
    lower = {c.lower().strip(): c for c in columns}
    mapping: dict[str, Optional[str]] = {
        "symbol": None,
        "transaction_type": None,
        "quantity": None,
        "price": None,
        "total_value": None,
        "executed_at": None,
        "fees": None,
    }
    # symbol — prefer 'symbol' over 'stock name'
    for kw in ["symbol", "ticker", "scrip code", "scrip", "script", "instrument", "isin"]:
        if kw in lower:
            mapping["symbol"] = lower[kw]
            break
    # transaction_type
    for kw in ["type", "side", "action", "buy/sell", "buysell", "transaction type", "order type", "txn type"]:
        if kw in lower:
            mapping["transaction_type"] = lower[kw]
            break
    # quantity
    for kw in ["quantity", "qty", "shares", "units", "volume", "no. of shares", "no of shares"]:
        if kw in lower:
            mapping["quantity"] = lower[kw]
            break
    # per-share price (strict — do NOT pick 'value' / 'amount' here)
    for kw in ["price", "trade price", "avg price", "avg. price", "rate", "nav", "unit price"]:
        if kw in lower:
            mapping["price"] = lower[kw]
            break
    # total value (fallback when no per-share price exists)
    for kw in ["value", "trade value", "amount", "total amount", "net amount", "turnover"]:
        if kw in lower:
            mapping["total_value"] = lower[kw]
            break
    # date
    for kw in [
        "execution date and time", "execution date", "trade date",
        "transaction date", "executed_at", "order date", "date",
    ]:
        if kw in lower:
            mapping["executed_at"] = lower[kw]
            break
    # fees
    for kw in ["fees", "fee", "brokerage", "commission", "charges", "total charges"]:
        if kw in lower:
            mapping["fees"] = lower[kw]
            break
    return mapping


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_trades(
    file_bytes: bytes,
    filename: str,
    max_rows: int = 5000,
) -> tuple[list[dict], list[str]]:
    """
    Main entry point.

    1. Parse the file into a DataFrame (auto-detects metadata header rows).
    2. Ask LLM to map columns to schema fields (rule-based fallback on failure).
    3. Extract and normalise rows; derive price from total_value/quantity if needed.

    Returns:
        (valid_trades, errors)
        valid_trades — list of dicts ready for bulk DB insert
        errors       — list of human-readable row-level error strings
    """
    df = parse_trade_file(file_bytes, filename)
    logger.info(f"Parsed '{filename}': {len(df)} rows × {len(df.columns)} cols  |  columns: {list(df.columns)}")

    if len(df) == 0:
        return [], ["The uploaded file contains no data rows."]

    if len(df) > max_rows:
        df = df.iloc[:max_rows]
        logger.warning(f"Clamped to {max_rows} rows for safety.")

    columns = list(df.columns)
    col_map = _llm_map_columns(columns)

    # --- Validate minimum required fields ---
    has_symbol   = bool(col_map.get("symbol"))
    has_quantity = bool(col_map.get("quantity"))
    has_price    = bool(col_map.get("price"))
    has_value    = bool(col_map.get("total_value"))

    if not has_symbol or not has_quantity or not (has_price or has_value):
        # Try rule-based fallback
        fallback = _fallback_map_columns(columns)
        has_symbol   = bool(fallback.get("symbol"))
        has_quantity = bool(fallback.get("quantity"))
        has_price    = bool(fallback.get("price"))
        has_value    = bool(fallback.get("total_value"))

        if not has_symbol or not has_quantity or not (has_price or has_value):
            raise ValueError(
                "Could not identify required columns (symbol, quantity, price or total value) in the file. "
                f"Found columns: {columns}"
            )
        col_map = fallback
        logger.info(f"Using rule-based fallback mapping: {col_map}")

    valid_trades: list[dict] = []
    errors: list[str] = []

    for row_idx, row in df.iterrows():
        row_num = int(row_idx) + 2  # 1-indexed display; +1 for header

        # --- Symbol ---
        symbol = _normalise_symbol(row.get(col_map["symbol"]) if col_map.get("symbol") else None)
        if not symbol:
            errors.append(f"Row {row_num}: missing or empty symbol — skipped.")
            continue

        # --- Quantity ---
        qty = _normalise_float(row.get(col_map["quantity"]) if col_map.get("quantity") else None)
        if qty is None or qty <= 0:
            errors.append(f"Row {row_num} ({symbol}): invalid quantity — skipped.")
            continue

        # --- Price (per-share or derived from total value) ---
        price: Optional[float] = None
        if col_map.get("price"):
            price = _normalise_float(row.get(col_map["price"]))

        if (price is None or price <= 0) and col_map.get("total_value"):
            total_val = _normalise_float(row.get(col_map["total_value"]))
            if total_val and total_val > 0 and qty > 0:
                price = round(total_val / qty, 4)

        if price is None or price <= 0:
            errors.append(f"Row {row_num} ({symbol}): could not determine price — skipped.")
            continue

        # --- Transaction type ---
        tx_type = _normalise_type(
            row.get(col_map["transaction_type"]) if col_map.get("transaction_type") else None
        )

        # --- Date ---
        executed_at_raw = row.get(col_map["executed_at"]) if col_map.get("executed_at") else None
        executed_at = _normalise_date(executed_at_raw)

        # --- Fees ---
        fees_raw = row.get(col_map["fees"]) if col_map.get("fees") else None
        fees = _normalise_float(fees_raw) or 0.0

        valid_trades.append({
            "symbol": symbol,
            "transaction_type": tx_type,
            "quantity": qty,
            "price": price,
            "executed_at": executed_at,
            "fees": fees,
        })

    logger.info(
        f"Extracted {len(valid_trades)} valid trades, {len(errors)} errors from '{filename}'"
    )
    return valid_trades, errors
