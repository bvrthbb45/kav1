package com.kav1.warehouse.domain.stock

import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.HoldingEntity

/** Applies actions to the local item counters and holdings (call inside a DB transaction). */
class LocalStock(private val db: AppDatabase) {

    suspend fun apply(qrId: String, userId: String, actionType: String, units: Int, timestamp: Long) {
        val item = db.itemDao().getById(qrId) ?: return
        val holders = load(qrId)
        StockRules.apply(item.quantity, holders, actionType, userId, units, timestamp)
        save(qrId, item.quantity, holders)
        db.itemDao().setLastAction(qrId, timestamp)
    }

    /** Recomputes the counters after the stock quantity changed. */
    suspend fun refresh(qrId: String) {
        val item = db.itemDao().getById(qrId) ?: return
        save(qrId, item.quantity, load(qrId))
    }

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
