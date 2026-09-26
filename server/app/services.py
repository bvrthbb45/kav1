"""Business logic for the sync endpoints, kept independent of FastAPI."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import messages, models, schemas

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


def _latest_actions(db: Session, qr_ids=None) -> Dict[str, models.Transaction]:
    """Most recent transaction (by device time) per item."""
    latest = select(
        models.Transaction.qr_id,
        func.max(models.Transaction.timestamp).label("ts"),
    ).group_by(models.Transaction.qr_id)
    if qr_ids is not None:
        latest = latest.where(models.Transaction.qr_id.in_(qr_ids))
    latest = latest.subquery()
    rows = db.scalars(
        select(models.Transaction)
        .join(
            latest,
            (models.Transaction.qr_id == latest.c.qr_id)
            & (models.Transaction.timestamp == latest.c.ts),
        )
        .order_by(models.Transaction.tx_id)
    ).all()
    # Ties on timestamp: the last tx_id wins, deterministically.
    return {tx.qr_id: tx for tx in rows}


def _recompute_item_status(db: Session, qr_ids: Set[str]) -> None:
    """Set each item's status from its most recent action (by device time).

    Devices sync out of order, so an older action that arrives late must not
    override a newer one that was already synced by another device.
    """
    if not qr_ids:
        return
    latest = _latest_actions(db, qr_ids)
    for item in db.scalars(select(models.Item).where(models.Item.qr_id.in_(latest))):
        item.current_status = models.STATUS_BY_ACTION[latest[item.qr_id].action_type]


def _to_epoch_ms(value: datetime) -> int:
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


def pull_state(db: Session) -> schemas.PullResponse:
    items = db.scalars(select(models.Item).order_by(models.Item.name)).all()
    users = db.scalars(select(models.User).order_by(models.User.full_name)).all()
    latest = _latest_actions(db)
    return schemas.PullResponse(
        success=True,
        message=messages.PULL_OK,
        server_time=int(datetime.now(timezone.utc).timestamp() * 1000),
        items=[_item_out(i, latest.get(i.qr_id)) for i in items],
        users=[schemas.UserOut.model_validate(u) for u in users],
    )


def _item_out(item: models.Item, last_tx) -> schemas.ItemOut:
    holder = None
    if last_tx is not None and last_tx.action_type != models.ACTION_RETURN:
        holder = last_tx.user_id
    return schemas.ItemOut(
        qr_id=item.qr_id,
        name=item.name,
        current_status=item.current_status,
        holder_user_id=holder,
        last_action_at=_to_epoch_ms(last_tx.timestamp) if last_tx else None,
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
            if item is None:
                db.add(
                    models.Item(
                        qr_id=incoming.qr_id,
                        name=incoming.name,
                        current_status=models.STATUS_AVAILABLE,
                    )
                )
            else:
                item.name = incoming.name
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(items)
