package com.kav1.warehouse.domain.stock

import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.ItemKind
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.HoldingEntity

/** Applies actions to the local item counters and holdings (call inside a DB transaction). */
class LocalStock(private val db: AppDatabase) {

    suspend fun apply(qrId: String, userId: String, actionType: String, units: Int, timestamp: Long) {
        val item = db.itemDao().getById(qrId) ?: return
        if (item.kind == ItemKind.CONSUMABLE) {
            // Issued units leave the stock; nobody "holds" them.
            if (actionType == ActionType.ISSUE) {
                val left = (item.quantity - units.coerceAtLeast(1)).coerceAtLeast(0)
                val issued = item.issuedQty + units.coerceAtLeast(1)
                db.itemDao().updateConsumable(qrId, left, issued, consumableStatus(left))
                db.itemDao().setLastAction(qrId, timestamp)
            }
            return
        }
        val holders = load(qrId)
        StockRules.apply(item.quantity, holders, actionType, userId, units, timestamp)
        save(qrId, item.quantity, holders)
        db.itemDao().setLastAction(qrId, timestamp)
    }

    /** Recomputes the counters after the stock quantity changed. */
    suspend fun refresh(qrId: String) {
        val item = db.itemDao().getById(qrId) ?: return
        if (item.kind == ItemKind.CONSUMABLE) {
            db.itemDao().updateConsumable(qrId, item.quantity, item.issuedQty, consumableStatus(item.quantity))
        } else {
            save(qrId, item.quantity, load(qrId))
        }
    }

    private fun consumableStatus(left: Int) = if (left > 0) ItemStatus.AVAILABLE else ItemStatus.ISSUED

    private suspend fun load(qrId: String): MutableMap<String, StockRules.Holding> =
        db.holdingDao().getForItem(qrId)
            .associateTo(LinkedHashMap()) { it.userId to StockRules.Holding(it.borrowed, it.issued, it.since) }

    private suspend fun save(qrId: String, quantity: Int, holders: Map<String, StockRules.Holding>) {
        db.holdingDao().replaceForItem(
            qrId,
            holders.map { (userId, h) -> HoldingEntity(qrId, userId, h.borrowed, h.issued, h.since) },
        )
        val s = StockRules.summarize(quantity, holders)
        db.itemDao().updateStock(qrId, s.status, s.latestHolder, s.available, s.borrowed, s.issued)
    }
}
