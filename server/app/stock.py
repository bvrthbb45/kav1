"""Stock of an item, replayed from its actions.

Every item (QR) is one of two kinds:

- LOAN (מושאל): only BORROW / RETURN. Units go to soldiers and come back;
  the stock does not shrink. ``Item.quantity`` is the stock.
- CONSUMABLE (ניצרך): only ISSUE. Issued units leave the warehouse for
  good. ``Item.quantity`` is everything ever stocked, so the current stock
  is ``quantity - issued`` (the panel converts when an operator types the
  current stock).

Tablets work offline and sync late, so the state is always recomputed by
replaying the item's actions in device-time order. For loans:

- BORROW n: if fewer than n units are free, the missing units are taken
  from the other holders (the soldier evidently has them now). With a
  quantity of 1 this is the old "latest action wins" behaviour.
- RETURN n: units come back from that soldier first, then from others, so
  a return is never lost.

ISSUE actions recorded on loan items before the kinds existed still count as
units held by the soldier. The Android app applies the same rules locally
(domain/stock/StockRules.kt).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional

from . import models


@dataclass
class Holding:
    borrowed: int = 0
    issued: int = 0
    since: Optional[datetime] = None

    @property
    def total(self) -> int:
        return self.borrowed + self.issued


@dataclass
class ItemState:
    kind: str
    # Loans: the stock. Consumables: everything ever stocked.
    received: int
    holders: Dict[str, Holding]
    # Consumables: units issued so far (ניפוקים).
    consumed: int = 0
    # Device time of the item's latest action.
    last_action: Optional[datetime] = None

    @property
    def consumable(self) -> bool:
        return self.kind == models.KIND_CONSUMABLE

    @property
    def quantity(self) -> int:
        """Units in the warehouse's books now."""
        if self.consumable:
            return max(self.received - self.consumed, 0)
        return self.received

    @property
    def borrowed(self) -> int:
        return sum(h.borrowed for h in self.holders.values())

    @property
    def issued(self) -> int:
        """Consumables: units issued so far. Loans: legacy issued units still out."""
        if self.consumable:
            return self.consumed
        return sum(h.issued for h in self.holders.values())

    @property
    def available(self) -> int:
        if self.consumable:
            return self.quantity
        held = sum(h.total for h in self.holders.values())
        return max(self.received - held, 0)

    @property
    def status(self) -> str:
        if self.consumable:
            return models.STATUS_AVAILABLE if self.available else models.STATUS_ISSUED
        if not self.holders or self.available > 0:
            return models.STATUS_AVAILABLE
        return models.STATUS_BORROWED if self.borrowed else models.STATUS_ISSUED

    @property
    def latest_holder(self) -> Optional[str]:
        """The soldier who most recently took units (for older tablets)."""
        if not self.holders:
            return None
        return max(self.holders.items(), key=lambda kv: kv[1].since or datetime.min)[0]


def _take(holding: Holding, n: int) -> int:
    """Remove up to n units (borrowed first); returns how many are still owed."""
    k = min(holding.borrowed, n)
    holding.borrowed -= k
    n -= k
    k = min(holding.issued, n)
    holding.issued -= k
    return n - k


def _take_from_others(holders: Dict[str, Holding], skip: str, n: int) -> None:
    # Oldest holders first: their units are the likeliest to have moved on.
    for user_id, holding in sorted(
        holders.items(), key=lambda kv: kv[1].since or datetime.min
    ):
        if n <= 0:
            break
        if user_id != skip:
            n = _take(holding, n)


def replay(
    quantity: int,
    transactions: Iterable[models.Transaction],
    kind: str = models.KIND_LOAN,
) -> ItemState:
    received = max(quantity or 0, 0)
    holders: Dict[str, Holding] = {}
    consumed = 0
    last_action = None
    for tx in sorted(transactions, key=lambda t: (t.timestamp, t.tx_id)):
        last_action = tx.timestamp
        n = max(tx.quantity or 1, 1)
        if kind == models.KIND_CONSUMABLE:
            if tx.action_type == models.ACTION_ISSUE:
                consumed += n
            continue
        if tx.action_type == models.ACTION_RETURN:
            owed = _take(holders.setdefault(tx.user_id, Holding()), n)
            _take_from_others(holders, tx.user_id, owed)
        elif tx.action_type in (models.ACTION_BORROW, models.ACTION_ISSUE):
            held = sum(h.total for h in holders.values())
            short = n - max(received - held, 0)
            if short > 0:
                _take_from_others(holders, tx.user_id, short)
            holding = holders.setdefault(tx.user_id, Holding())
            if tx.action_type == models.ACTION_BORROW:
                holding.borrowed += n
            else:
                holding.issued += n
            holding.since = tx.timestamp
        holders = {u: h for u, h in holders.items() if h.total > 0}
    return ItemState(
        kind=kind,
        received=received,
        holders=holders,
        consumed=consumed,
        last_action=last_action,
    )


def item_states(db, qr_ids=None) -> Dict[str, ItemState]:
    """Current state of the given items (all items when qr_ids is None)."""
    from sqlalchemy import select

    items = select(models.Item.qr_id, models.Item.quantity, models.Item.kind)
    txs = select(models.Transaction)
    if qr_ids is not None:
        items = items.where(models.Item.qr_id.in_(qr_ids))
        txs = txs.where(models.Transaction.qr_id.in_(qr_ids))
    by_item: Dict[str, list] = {}
    for tx in db.scalars(txs):
        by_item.setdefault(tx.qr_id, []).append(tx)
    return {
        qr_id: replay(quantity, by_item.get(qr_id, []), kind or models.KIND_LOAN)
        for qr_id, quantity, kind in db.execute(items)
    }


def consumed_units(db, qr_id: str) -> int:
    """Units of a consumable issued so far (to turn "stock now" into "received")."""
    from sqlalchemy import func, select

    return (
        db.scalar(
            select(func.coalesce(func.sum(models.Transaction.quantity), 0)).where(
                models.Transaction.qr_id == qr_id,
                models.Transaction.action_type == models.ACTION_ISSUE,
            )
        )
        or 0
    )
