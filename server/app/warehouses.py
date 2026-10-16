"""Warehouses (מחסנים) and how each item's stock is split between them."""

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from . import messages, models, services, stock


class WarehouseError(Exception):
    """A warehouse request that cannot be done; the message is Hebrew."""


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def names(db: Session) -> List[str]:
    return list(
        db.scalars(select(models.Warehouse.name).order_by(models.Warehouse.name))
    )


def _movements(db: Session, qr_ids: Optional[Iterable[str]] = None) -> Dict:
    """Net units moved per (item, warehouse): + returned, - taken."""
    sign = {
        models.ACTION_RETURN: 1,
        models.ACTION_BORROW: -1,
        models.ACTION_ISSUE: -1,
    }
    query = (
        select(
            models.Transaction.qr_id,
            models.Transaction.warehouse,
            models.Transaction.action_type,
            func.sum(models.Transaction.quantity),
        )
        .where(models.Transaction.warehouse != "")
        .group_by(
            models.Transaction.qr_id,
            models.Transaction.warehouse,
            models.Transaction.action_type,
        )
    )
    if qr_ids is not None:
        query = query.where(models.Transaction.qr_id.in_(list(qr_ids)))
    net: Dict = Counter()
    for qr_id, warehouse, action, units in db.execute(query):
        net[(qr_id, warehouse)] += sign.get(action, 0) * (units or 0)
    return net


def levels(
    db: Session, qr_ids: Optional[Iterable[str]] = None
) -> Dict[str, Dict[str, int]]:
    """Units on the shelf now, per item and warehouse (items split only)."""
    query = select(models.ItemStock)
    if qr_ids is not None:
        qr_ids = list(qr_ids)
        query = query.where(models.ItemStock.qr_id.in_(qr_ids))
    rows = list(db.scalars(query))
    net = _movements(db, {r.qr_id for r in rows})
    result: Dict[str, Dict[str, int]] = defaultdict(dict)
    for r in sorted(rows, key=lambda r: r.warehouse):
        result[r.qr_id][r.warehouse] = max(
            (r.base or 0) + net.get((r.qr_id, r.warehouse), 0), 0
        )
    return dict(result)


def has_split(db: Session, qr_id: str) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(models.ItemStock)
            .where(models.ItemStock.qr_id == qr_id)
        )
        > 0
    )


# --- Warehouses ----------------------------------------------------------------


def save_warehouse(db: Session, name: str, old_name: Optional[str] = None) -> None:
    """Create a warehouse, or rename one (its stock and history follow)."""
    name, old_name = _clean(name), _clean(old_name)
    if not name:
        raise WarehouseError(messages.WAREHOUSE_NOT_FOUND.format(name=name))
    if old_name and old_name != name:
        if db.get(models.Warehouse, name) is not None:
            raise WarehouseError(messages.WAREHOUSE_EXISTS.format(name=name))
        if db.get(models.Warehouse, old_name) is None:
            raise WarehouseError(messages.WAREHOUSE_NOT_FOUND.format(name=old_name))
        db.add(models.Warehouse(name=name))
        db.flush()
        db.execute(
            update(models.ItemStock)
            .where(models.ItemStock.warehouse == old_name)
            .values(warehouse=name)
        )
        db.execute(
            update(models.Transaction)
            .where(models.Transaction.warehouse == old_name)
            .values(warehouse=name)
        )
        db.execute(delete(models.Warehouse).where(models.Warehouse.name == old_name))
    elif db.get(models.Warehouse, name) is None:
        db.add(models.Warehouse(name=name))
    db.commit()


def delete_warehouse(db: Session, name: str) -> None:
    if db.get(models.Warehouse, name) is None:
        raise WarehouseError(messages.WAREHOUSE_NOT_FOUND.format(name=name))
    units = sum(lv.get(name, 0) for lv in levels(db).values())
    if units:
        raise WarehouseError(
            messages.WAREHOUSE_NOT_EMPTY.format(name=name, units=units)
        )
    db.execute(delete(models.ItemStock).where(models.ItemStock.warehouse == name))
    db.execute(delete(models.Warehouse).where(models.Warehouse.name == name))
    db.commit()


# --- Splitting an item's stock -------------------------------------------------


def set_split(
    db: Session, qr_id: str, shelves: Dict[str, int], commit: bool = True
) -> int:
    """Set how many units of [qr_id] are on each warehouse's shelf now.

    The item's stock becomes the sum (plus loaned units still out). An
    empty [shelves] removes the split. Returns the total on the shelves.
    """
    item = db.get(models.Item, qr_id)
    if item is None:
        raise WarehouseError(messages.ITEM_NOT_FOUND.format(qr_id=qr_id))
    clean: Dict[str, int] = {}
    for name, units in shelves.items():
        name = _clean(name)
        if not name:
            continue
        if units is None or units < 0:
            raise WarehouseError(messages.STOCK_NEGATIVE.format(name=name))
        if db.get(models.Warehouse, name) is None:
            db.add(models.Warehouse(name=name))
            db.flush()
        clean[name] = clean.get(name, 0) + int(units)
    net = _movements(db, [qr_id])
    db.execute(delete(models.ItemStock).where(models.ItemStock.qr_id == qr_id))
    for name, units in clean.items():
        db.add(
            models.ItemStock(
                qr_id=qr_id, warehouse=name, base=units - net.get((qr_id, name), 0)
            )
        )
    total = sum(clean.values())
    if clean:
        state = stock.item_states(db, [qr_id])[qr_id]
        if item.kind == models.KIND_CONSUMABLE:
            item.quantity = services.stocked_quantity(db, item, total)
        else:
            # The stock is what is on the shelves plus what is out on loan.
            item.quantity = total + state.borrowed + state.issued
    db.flush()
    services._recompute_item_status(db, {qr_id})
    if commit:
        db.commit()
    return total


def summary(db: Session) -> List[Dict]:
    """Per warehouse: how many items and units are on its shelves."""
    per: Dict[str, Counter] = {n: Counter() for n in names(db)}
    for shelves in levels(db).values():
        for name, units in shelves.items():
            c = per.setdefault(name, Counter())
            c["items"] += 1
            c["units"] += units
    return [
        {"name": n, "items": c["items"], "units": c["units"]} for n, c in per.items()
    ]
