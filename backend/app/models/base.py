# iCoDer - Base Model Mixins
import uuid
from datetime import datetime
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

class TimestampMixin:
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
