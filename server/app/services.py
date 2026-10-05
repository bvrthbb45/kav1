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

    # Tablets that missed a serial / personal number change still use the old one.
    item_aliases = _aliases(db, models.ALIAS_ITEM)
    user_aliases = _aliases(db, models.ALIAS_USER)
    qr_ids = {tx.qr_id for tx in transactions}
    user_ids = {tx.user_id for tx in transactions}
    qr_ids |= {item_aliases[q] for q in qr_ids if q in item_aliases}
    user_ids |= {user_aliases[u] for u in user_ids if u in user_aliases}
    tx_ids = {tx.tx_id for tx in transactions}

    known_items: Dict[str, str] = dict(
        db.execute(
            select(models.Item.qr_id, models.Item.kind).where(
                models.Item.qr_id.in_(qr_ids)
            )
        ).all()
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
            if tx.qr_id not in known_items and tx.qr_id in item_aliases:
                tx = tx.model_copy(update={"qr_id": item_aliases[tx.qr_id]})
            if tx.user_id not in known_users and tx.user_id in user_aliases:
                tx = tx.model_copy(update={"user_id": user_aliases[tx.user_id]})
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
            elif tx.action_type not in models.ACTIONS_BY_KIND.get(
                known_items[tx.qr_id], models.ACTIONS_BY_KIND[models.KIND_LOAN]
            ):
                reason = (
                    messages.TX_CONSUMABLE_ONLY_ISSUE
                    if known_items[tx.qr_id] == models.KIND_CONSUMABLE
                    else messages.TX_LOAN_ONLY_BORROW
                ).format(qr_id=tx.qr_id)

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
                    note=(tx.note or "").strip(),
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


def _aliases(db: Session, kind: str) -> Dict[str, str]:
    return dict(
        db.execute(
            select(models.IdAlias.old_id, models.IdAlias.new_id).where(
                models.IdAlias.kind == kind
            )
        ).all()
    )


CHANGE_DELETE_ITEM = "DELETE_ITEM"
CHANGE_DELETE_USER = "DELETE_USER"
CHANGE_RENAME_ITEM = "RENAME_ITEM"
CHANGE_RENAME_USER = "RENAME_USER"


def apply_changes(
    db: Session, changes: List[schemas.ChangeIn]
) -> schemas.ChangesResponse:
    """Apply deletes and id changes from a tablet, in order.

    Each change commits on its own. A change already done (the tablet lost
    the answer and sent it again) counts as applied.
    """
    from . import catalog  # catalog imports this module

    results: List[schemas.ChangeResult] = []
    for change in changes:
        target, new_id = change.target_id.strip(), (change.new_id or "").strip()
        try:
            if change.op == CHANGE_DELETE_ITEM:
                if db.get(models.Item, target) is not None:
                    catalog.delete_item(db, target)
                message = messages.ITEM_DELETED.format(qr_id=target)
            elif change.op == CHANGE_DELETE_USER:
                if db.get(models.User, target) is not None:
                    catalog.delete_user(db, target)
                message = messages.USER_DELETED.format(user_id=target)
            elif change.op in (CHANGE_RENAME_ITEM, CHANGE_RENAME_USER):
                if not new_id:
                    raise catalog.CatalogError(messages.CHANGE_NO_NEW_ID)
                is_item = change.op == CHANGE_RENAME_ITEM
                model = models.Item if is_item else models.User
                # Not on the server (created on the tablet, or already
                # renamed): the tablet uploads it under the new id.
                if db.get(model, target) is not None:
                    if is_item:
                        catalog.rename_item(db, target, new_id)
                    else:
                        catalog.rename_user(db, target, new_id)
                message = (
                    messages.ITEM_RENAMED if is_item else messages.USER_RENAMED
                ).format(old=target, new=new_id)
            else:
                raise catalog.CatalogError(messages.CHANGE_UNKNOWN.format(op=change.op))
            results.append(
                schemas.ChangeResult(op_id=change.op_id, applied=True, message=message)
            )
        except catalog.CatalogError as e:
            db.rollback()
            results.append(
                schemas.ChangeResult(op_id=change.op_id, applied=False, message=str(e))
            )
    applied = sum(r.applied for r in results)
    return schemas.ChangesResponse(
        success=applied == len(results),
        message=messages.UPSERT_OK.format(count=applied),
        results=results,
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
        note=tx.note or "",
    )


def item_out(item: models.Item, state: stock.ItemState) -> schemas.ItemOut:
    return schemas.ItemOut(
        qr_id=item.qr_id,
        name=item.name,
        current_status=state.status,
        category=item.category or "",
        kind=state.kind,
        quantity=state.quantity,
        available_qty=state.available,
        borrowed_qty=state.borrowed,
        issued_qty=state.issued,
        location=item.location or "",
        department=item.department or "",
        holder_user_id=state.latest_holder,
        last_action_at=_to_epoch_ms(state.last_action) if state.last_action else None,
    )


def stocked_quantity(db: Session, item: models.Item, stock_now: int) -> int:
    """What to store in Item.quantity when an operator enters the current stock.

    For consumables the column holds everything ever stocked (issued units are
    subtracted when reading), so add back what was already issued.
    """
    if item.kind == models.KIND_CONSUMABLE and item.qr_id:
        return stock_now + stock.consumed_units(db, item.qr_id)
    return stock_now


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
                item = models.Item(
                    qr_id=incoming.qr_id,
                    name=incoming.name,
                    current_status=models.STATUS_AVAILABLE,
                    category=category,
                    quantity=incoming.quantity or 1,
                    kind=incoming.kind or models.KIND_LOAN,
                    location=(incoming.location or "").strip(),
                    department=(incoming.department or "").strip(),
                )
                db.add(item)
            else:
                item.name = incoming.name
                if incoming.category is not None:
                    item.category = category
                if incoming.kind is not None:
                    item.kind = incoming.kind
                if incoming.location is not None:
                    item.location = incoming.location.strip()
                if incoming.department is not None:
                    item.department = incoming.department.strip()
                if incoming.quantity is not None:
                    item.quantity = stocked_quantity(db, item, incoming.quantity)
        db.flush()
        # A new stock quantity or kind can free up (or use up) units.
        _recompute_item_status(
            db, {i.qr_id for i in items if i.quantity is not None or i.kind is not None}
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(items)
