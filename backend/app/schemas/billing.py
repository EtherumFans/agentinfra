# Billing schemas — balance + transaction response validation
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class BalanceResponse(BaseModel):
    balance: float
    currency: str = "CNY"


class TransactionResponse(BaseModel):
    id: str
    amount: float
    type: str  # "credit" | "debit"
    description: str = ""
    balance_after: Optional[float] = None
    created_at: Optional[datetime] = None


class TransactionListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int


class CreditAddRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Credit amount to add")
    description: str = "Manual top-up"


class CreditAddResponse(BaseModel):
    status: str = "success"
    added: float
    new_balance: float
