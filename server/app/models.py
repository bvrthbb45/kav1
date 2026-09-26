from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

STATUS_AVAILABLE = "AVAILABLE"
STATUS_BORROWED = "BORROWED"
STATUS_ISSUED = "ISSUED"

ACTION_BORROW = "BORROW"
ACTION_RETURN = "RETURN"
# Permanent issue to a soldier (ניפוק), as opposed to a temporary loan.
ACTION_ISSUE = "ISSUE"

STATUS_BY_ACTION = {
    ACTION_BORROW: STATUS_BORROWED,
    ACTION_RETURN: STATUS_AVAILABLE,
    ACTION_ISSUE: STATUS_ISSUED,
}


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(200), default="")


class Item(Base):
    __tablename__ = "items"

    qr_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    current_status: Mapped[str] = mapped_column(String(32), default=STATUS_AVAILABLE)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_qr_ts", "qr_id", "timestamp"),)

    # Generated on the device (UUID) so re-sent batches are idempotent.
    tx_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    qr_id: Mapped[str] = mapped_column(ForeignKey("items.qr_id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    action_type: Mapped[str] = mapped_column(String(16))
    # Time the action happened on the device (UTC), not the time it was synced.
    timestamp: Mapped[datetime] = mapped_column(DateTime)
