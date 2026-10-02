"""Management and reporting queries used by the control panel."""

from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import messages, models, services


class CatalogError(Exception):
    """A management request that cannot be done; the message is Hebrew."""


def _epoch_ms(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


# --- Items -----------------------------------------------------------------


def save_item(db: Session, qr_id: str, name: str, category: str) -> bool:
    """Create or update an item; status is never touched. True if created."""
    qr_id, name, category = _clean(qr_id), _clean(name), _clean(category)
    item = db.get(models.Item, qr_id)
    created = item is None
    if created:
        db.add(
            models.Item(
                qr_id=qr_id,
                name=name,
                category=category,
                current_status=models.STATUS_AVAILABLE,
            )
        )
    else:
        item.name = name
        item.category = category
    db.commit()
    return created


def _count_transactions(db: Session, column, value: str) -> int:
    return db.scalar(
        select(func.count()).select_from(models.Transaction).where(column == value)
    )


def delete_item(db: Session, qr_id: str) -> None:
    item = db.get(models.Item, qr_id)
    if item is None:
        raise CatalogError(messages.ITEM_NOT_FOUND.format(qr_id=qr_id))
    if _count_transactions(db, models.Transaction.qr_id, qr_id):
        raise CatalogError(messages.ITEM_HAS_HISTORY.format(qr_id=qr_id))
    db.delete(item)
    db.commit()


# --- Users -----------------------------------------------------------------


def save_user(db: Session, user_id: str, full_name: str, unit: str) -> None:
    db.merge(
        models.User(
            user_id=_clean(user_id), full_name=_clean(full_name), unit=_clean(unit)
        )
    )
    db.commit()


def delete_user(db: Session, user_id: str) -> None:
    user = db.get(models.User, user_id)
    if user is None:
        raise CatalogError(messages.USER_NOT_FOUND.format(user_id=user_id))
    if _count_transactions(db, models.Transaction.user_id, user_id):
        raise CatalogError(messages.USER_HAS_HISTORY.format(user_id=user_id))
    db.delete(user)
    db.commit()


# --- Item types --------------------------------------------------------------


def save_category(
    db: Session, name: str, target_qty: Optional[int], old_name: Optional[str] = None
) -> None:
    """Create/update a type; renaming also moves its items to the new name."""
    name = _clean(name)
    old_name = _clean(old_name) or name
    if old_name != name:
        if db.get(models.Category, name) is not None:
            raise CatalogError(messages.CATEGORY_EXISTS.format(name=name))
        old = db.get(models.Category, old_name)
        if old is not None:
            db.delete(old)
            db.flush()
        for item in db.scalars(
            select(models.Item).where(models.Item.category == old_name)
        ):
            item.category = name
    category = db.get(models.Category, name)
    if category is None:
        db.add(models.Category(name=name, target_qty=target_qty))
    else:
        category.target_qty = target_qty
    db.commit()


def delete_category(db: Session, name: str) -> None:
    count = db.scalar(
        select(func.count())
        .select_from(models.Item)
        .where(models.Item.category == name)
    )
    if count:
        raise CatalogError(messages.CATEGORY_IN_USE.format(name=name, count=count))
    category = db.get(models.Category, name)
    if category is not None:
        db.delete(category)
        db.commit()


def category_summary(db: Session) -> List[Dict]:
    """Per type: target quantity and how many units are in each status."""
    counts: Dict[str, Counter] = {}
    for category, status, count in db.execute(
        select(models.Item.category, models.Item.current_status, func.count()).group_by(
            models.Item.category, models.Item.current_status
        )
    ):
        counts.setdefault(category or "", Counter())[status] += count
    targets = {c.name: c.target_qty for c in db.scalars(select(models.Category))}
    rows = []
    for name in sorted(set(counts) | set(targets), key=lambda n: (n == "", n)):
        c = counts.get(name, Counter())
        total = sum(c.values())
        target = targets.get(name)
        rows.append(
            {
                "name": name,
                "label": name or messages.NO_CATEGORY,
                "target_qty": target,
                "total": total,
                "available": c[models.STATUS_AVAILABLE],
                "borrowed": c[models.STATUS_BORROWED],
                "issued": c[models.STATUS_ISSUED],
                # Units still missing to reach the target (תקן).
                "missing": max(target - total, 0) if target is not None else None,
            }
        )
    return rows


# --- Cards and history -----------------------------------------------------


def _names(db: Session):
    items = {i.qr_id: i for i in db.scalars(select(models.Item))}
    users = {u.user_id: u for u in db.scalars(select(models.User))}
    return items, users


def _history_rows(db: Session, where, items, users, limit: Optional[int] = None):
    query = (
        select(models.Transaction)
        .where(where)
        .order_by(models.Transaction.timestamp.desc())
    )
    if limit:
        query = query.limit(limit)
    rows = []
    for tx in db.scalars(query):
        item, user = items.get(tx.qr_id), users.get(tx.user_id)
        rows.append(
            {
                "tx_id": tx.tx_id,
                "timestamp": _epoch_ms(tx.timestamp),
                "action_type": tx.action_type,
                "qr_id": tx.qr_id,
                "item_name": item.name if item else tx.qr_id,
                "category": item.category if item else "",
                "user_id": tx.user_id,
                "user_name": user.full_name if user else tx.user_id,
                "unit": user.unit if user else "",
            }
        )
    return rows


def holdings(db: Session, user_id: Optional[str] = None) -> List[Dict]:
    """Items currently held (borrowed or issued), with who holds them since when."""
    items, users = _names(db)
    latest = services._latest_actions(db)
    rows = []
    for qr_id, tx in latest.items():
        if tx.action_type == models.ACTION_RETURN:
            continue
        if user_id is not None and tx.user_id != user_id:
            continue
        item, user = items.get(qr_id), users.get(tx.user_id)
        if item is None:
            continue
        rows.append(
            {
                "qr_id": qr_id,
                "item_name": item.name,
                "category": item.category,
                "status": item.current_status,
                "user_id": tx.user_id,
                "user_name": user.full_name if user else tx.user_id,
                "unit": user.unit if user else "",
                "since": _epoch_ms(tx.timestamp),
            }
        )
    rows.sort(key=lambda r: (r["user_name"], r["category"], r["item_name"]))
    return rows


def user_card(db: Session, user_id: str) -> Dict:
    user = db.get(models.User, user_id)
    if user is None:
        raise CatalogError(messages.USER_NOT_FOUND.format(user_id=user_id))
    items, users = _names(db)
    return {
        "user": {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "unit": user.unit,
        },
        "holding": holdings(db, user_id),
        "history": _history_rows(
            db, models.Transaction.user_id == user_id, items, users
        ),
    }


def item_card(db: Session, qr_id: str) -> Dict:
    item = db.get(models.Item, qr_id)
    if item is None:
        raise CatalogError(messages.ITEM_NOT_FOUND.format(qr_id=qr_id))
    items, users = _names(db)
    history = _history_rows(db, models.Transaction.qr_id == qr_id, items, users)
    holder = None
    if history and history[0]["action_type"] != models.ACTION_RETURN:
        holder = {
            k: history[0][k] for k in ("user_id", "user_name", "unit", "timestamp")
        }
    return {
        "item": {
            "qr_id": item.qr_id,
            "name": item.name,
            "category": item.category,
            "current_status": item.current_status,
        },
        "holder": holder,
        "history": history,
    }


def transactions(
    db: Session, start_ms: Optional[int] = None, end_ms: Optional[int] = None
) -> List[Dict]:
    """Actions in [start_ms, end_ms) (epoch ms), newest first."""
    items, users = _names(db)
    where = models.Transaction.tx_id.isnot(None)
    if start_ms is not None:
        where = where & (
            models.Transaction.timestamp >= services._to_datetime(start_ms)
        )
    if end_ms is not None:
        where = where & (models.Transaction.timestamp < services._to_datetime(end_ms))
    return _history_rows(db, where, items, users)
