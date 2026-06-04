from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timedelta
from typing import Optional

class TransactionBase(BaseModel):
    symbol: str = Field(..., description="Stock Ticker Symbol (e.g. INFY.NS, AAPL)")
    company_name: Optional[str] = Field(default=None, description="Company Name")
    transaction_type: str = Field(..., description="BUY or SELL")
    quantity: float = Field(..., gt=0, description="Number of shares")
    price: float = Field(..., gt=0, description="Price per share")
    fees: Optional[float] = Field(default=0.0, description="Brokerage / Transaction fees")
    executed_at: Optional[datetime] = Field(default=None, description="Date & Time of execution")

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None:
            now = datetime.now(v.tzinfo) if v.tzinfo else datetime.now()
            if v > now + timedelta(hours=24):
                raise ValueError("Transaction date cannot be in the future")
        return v

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(BaseModel):
    symbol: Optional[str] = None
    company_name: Optional[str] = None
    transaction_type: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    fees: Optional[float] = None
    executed_at: Optional[datetime] = None

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None:
            now = datetime.now(v.tzinfo) if v.tzinfo else datetime.now()
            if v > now + timedelta(hours=24):
                raise ValueError("Transaction date cannot be in the future")
        return v

class TransactionResponse(TransactionBase):
    id: int
    user_id: str
    executed_at: datetime

    class Config:
        from_attributes = True