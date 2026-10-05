from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

STATUS_AVAILABLE = "AVAILABLE"
STATUS_BORROWED = "BORROWED"
STATUS_ISSUED = "ISSUED"

ACTION_BORROW = "BORROW"
ACTION_RETURN = "RETURN"
# Permanent issue to a soldier (ניפוק), as opposed to a temporary loan.
ACTION_ISSUE = "ISSUE"

# How an item is handed out.
KIND_LOAN = "LOAN"  # מושאל: borrow and return only; stock does not shrink
KIND_CONSUMABLE = "CONSUMABLE"  # ניצרך: issue only; issued units leave the stock
KINDS = (KIND_LOAN, KIND_CONSUMABLE)
ACTIONS_BY_KIND = {
    KIND_LOAN: (ACTION_BORROW, ACTION_RETURN),
    KIND_CONSUMABLE: (ACTION_ISSUE,),
}

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

    # The serial number printed on the item's QR label.
    qr_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    current_status: Mapped[str] = mapped_column(String(32), default=STATUS_AVAILABLE)
    # Item type (e.g. "מכשיר קשר"); many serials share one type.
    category: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # Units in stock under this QR; actions take part of it (see stock.py).
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    kind: Mapped[str] = mapped_column(
        String(16), default=KIND_LOAN, server_default=KIND_LOAN
    )
    # Where the item is kept (e.g. "ארון 3, מדף 2").
    location: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # The department (מחלקה) the item belongs to.
    department: Mapped[str] = mapped_column(String(200), default="", server_default="")


class Category(Base):
    """An item type with an optional target quantity (תקן).

    Types also exist implicitly through Item.category; a row here is only
    needed to set the target quantity or to list a type before it has items.
    """

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(200), primary_key=True)
    target_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


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
    # Units borrowed / issued / returned by this action.
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Free text entered when issuing / borrowing.
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")


ALIAS_ITEM = "ITEM"
ALIAS_USER = "USER"


class IdAlias(Base):
    """An old serial / personal number that was changed to [new_id].

    Tablets that have not synced since the change still send the old id;
    their actions are moved to the new one.
    """

    __tablename__ = "id_aliases"

    kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    old_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    new_id: Mapped[str] = mapped_column(String(128))
