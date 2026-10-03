"""Business logic for the sync endpoints, kept independent of FastAPI."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import messages, models, schemas, stock

log = logging.getLogger(__name__)


def _to_datetime(epoch_ms: int) -> datetime:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def push_transactions(
    db: Session, transactions: List[schemas.PendingTransaction]
) -> schemas.PushResponse:
    """Apply a batch of device transactions atomically.

    Invalid transactions (unknown item/user/action) are rejected individually
    with a Hebrew reason; everything else is committed in one DB transaction.
    Any database error rolls back the whole batch and propagates.
    """
    if not transactions:
        return schemas.PushResponse(
            success=True, message=messages.PUSH_EMPTY, accepted=[], rejected=[]
        )

    qr_ids = {tx.qr_id for tx in transactions}
    user_ids = {tx.user_id for tx in transactions}
    tx_ids = {tx.tx_id for tx in transactions}

    known_items: Set[str] = set(
        db.scalars(select(models.Item.qr_id).where(models.Item.qr_id.in_(qr_ids)))
    )
    known_users: Set[str] = set(
        db.scalars(select(models.User.user_id).where(models.User.user_id.in_(user_ids)))
    )
    seen_tx_ids: Set[str] = set(
        db.scalars(
            select(models.Transaction.tx_id).where(models.Transaction.tx_id.in_(tx_ids))
        )
    )

    accepted: List[str] = []
    rejected: List[schemas.TxResult] = []
    touched_items: Set[str] = set()

    try:
        for tx in sorted(transactions, key=lambda t: t.timestamp):
            reason = None
            if tx.tx_id in seen_tx_ids:
                # Already stored (e.g. the device lost the previous response).
                # Report as accepted so the device can drop it.
                accepted.append(tx.tx_id)
                continue
            if tx.action_type not in models.STATUS_BY_ACTION:
                reason = messages.TX_UNKNOWN_ACTION.format(action_type=tx.action_type)
            elif tx.qr_id not in known_items:
                reason = messages.TX_UNKNOWN_ITEM.format(qr_id=tx.qr_id)
            elif tx.user_id not in known_users:
                reason = messages.TX_UNKNOWN_USER.format(user_id=tx.user_id)

            if reason:
                rejected.append(
                    schemas.TxResult(tx_id=tx.tx_id, accepted=False, message=reason)
                )
                continue

            db.add(
                models.Transaction(
                    tx_id=tx.tx_id,
                    qr_id=tx.qr_id,
                    user_id=tx.user_id,
                    action_type=tx.action_type,
                    timestamp=_to_datetime(tx.timestamp),
                    quantity=tx.quantity,
                )
            )
            seen_tx_ids.add(tx.tx_id)
            accepted.append(tx.tx_id)
            touched_items.add(tx.qr_id)

        db.flush()
        _recompute_item_status(db, touched_items)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if rejected:
        message = messages.PUSH_PARTIAL.format(
            accepted=len(accepted), rejected=len(rejected)
        )
    else:
        message = messages.PUSH_ALL_OK.format(count=len(accepted))
    return schemas.PushResponse(
        success=not rejected, message=message, accepted=accepted, rejected=rejected
    )


def _recompute_item_status(db: Session, qr_ids: Set[str]) -> None:
    """Set each item's status from its replayed actions (see stock.py).

    Devices sync out of order, so an older action that arrives late is
    replayed in device-time order rather than applied on top.
    """
    if not qr_ids:
        return
    states = stock.item_states(db, qr_ids)
    for item in db.scalars(select(models.Item).where(models.Item.qr_id.in_(qr_ids))):
        item.current_status = states[item.qr_id].status


def _to_epoch_ms(value: datetime) -> int:
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


# Most recent actions sent to tablets for item history and soldier cards.
HISTORY_LIMIT = 3000


def pull_state(db: Session) -> schemas.PullResponse:
    items = db.scalars(select(models.Item).order_by(models.Item.name)).all()
    users = db.scalars(select(models.User).order_by(models.User.full_name)).all()
    categories = db.scalars(select(models.Category).order_by(models.Category.name))
    history = db.scalars(
        select(models.Transaction)
        .order_by(models.Transaction.timestamp.desc())
        .limit(HISTORY_LIMIT)
    )
    states = stock.item_states(db)
    return schemas.PullResponse(
        success=True,
        message=messages.PULL_OK,
        server_time=int(datetime.now(timezone.utc).timestamp() * 1000),
        items=[item_out(i, states[i.qr_id]) for i in items],
        users=[schemas.UserOut.model_validate(u) for u in users],
        categories=[
            schemas.CategoryOut(name=c.name, target_qty=c.target_qty)
            for c in categories
        ],
        history=[history_out(t) for t in history],
        holdings=[
            schemas.HoldingOut(
                qr_id=qr_id,
                user_id=user_id,
                borrowed=h.borrowed,
                issued=h.issued,
                since=_to_epoch_ms(h.since) if h.since else None,
            )
            for qr_id, state in states.items()
            for user_id, h in state.holders.items()
        ],
    )


def history_out(tx: models.Transaction) -> schemas.HistoryOut:
    return schemas.HistoryOut(
        tx_id=tx.tx_id,
        qr_id=tx.qr_id,
        user_id=tx.user_id,
        action_type=tx.action_type,
        timestamp=_to_epoch_ms(tx.timestamp),
        quantity=tx.quantity or 1,
    )


def item_out(item: models.Item, state: stock.ItemState) -> schemas.ItemOut:
    return schemas.ItemOut(
        qr_id=item.qr_id,
        name=item.name,
        current_status=state.status,
        category=item.category or "",
        quantity=state.quantity,
        available_qty=state.available,
        borrowed_qty=state.borrowed,
        issued_qty=state.issued,
        holder_user_id=state.latest_holder,
        last_action_at=_to_epoch_ms(state.last_action) if state.last_action else None,
    )


def upsert_users(db: Session, users: List[schemas.UserIn]) -> int:
    try:
        for user in users:
            db.merge(models.User(**user.model_dump()))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(users)


def upsert_items(db: Session, items: List[schemas.ItemIn]) -> int:
    try:
        for incoming in items:
            item = db.get(models.Item, incoming.qr_id)
            category = (incoming.category or "").strip()
            if item is None:
                db.add(
                    models.Item(
                        qr_id=incoming.qr_id,
                        name=incoming.name,
                        current_status=models.STATUS_AVAILABLE,
                        category=category,
                        quantity=incoming.quantity or 1,
                    )
                )
            else:
                item.name = incoming.name
                if incoming.category is not None:
                    item.category = category
                if incoming.quantity is not None:
                    item.quantity = incoming.quantity
        db.flush()
        # A new stock quantity can free up (or use up) units.
        _recompute_item_status(db, {i.qr_id for i in items if i.quantity is not None})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(items)
