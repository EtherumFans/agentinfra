"""Billing endpoints with real database persistence"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.billing import Transaction

router = APIRouter(prefix="/api/billing", tags=["billing"])


async def _get_balance(user_id: str, db: AsyncSession) -> float:
    """Get current balance from latest transaction, or 0 if none."""
    result = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc()).limit(1)
    )
    last = result.scalar_one_or_none()
    return last.balance_after if last else 50.0  # default starting balance


@router.get("/balance")
async def get_balance(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get current credit balance"""
    balance = await _get_balance(user.id, db)
    return {"balance": round(balance, 2), "currency": "CNY"}


@router.get("/transactions")
async def get_transactions(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get transaction history"""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    transactions = result.scalars().all()
    return {
        "transactions": [
            {
                "id": t.id,
                "date": t.created_at.strftime("%Y-%m-%d"),
                "description": t.description,
                "amount": f"¥{t.amount:+.2f}",
                "type": t.type,
                "balance_after": t.balance_after,
            }
            for t in transactions
        ],
        "total": len(transactions),
    }


@router.post("/credits")
async def add_credits(
    amount: float = Query(50.0, gt=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add credits to account"""
    current = await _get_balance(user.id, db)
    new_balance = current + amount
    txn = Transaction(
        user_id=user.id,
        type="credit",
        amount=amount,
        balance_after=new_balance,
        description=f"Credit purchase",
        source="purchase",
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return {"status": "success", "added": amount, "new_balance": round(new_balance, 2)}
