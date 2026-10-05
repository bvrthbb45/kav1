package com.kav1.warehouse.domain.stock

import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.CatalogChangeEntity
import com.kav1.warehouse.data.local.CatalogOp

/**
 * Applies deletes and id changes to the local tables (call inside a DB
 * transaction). Mirrors server/app/catalog.py.
 */
class CatalogChanges(private val db: AppDatabase) {
    private val dao = db.catalogDao()

    suspend fun apply(change: CatalogChangeEntity) {
        when (change.op) {
            CatalogOp.DELETE_ITEM -> deleteItem(change.targetId)
            CatalogOp.DELETE_USER -> deleteUser(change.targetId)
            CatalogOp.RENAME_ITEM -> change.newId?.let { renameItem(change.targetId, it) }
            CatalogOp.RENAME_USER -> change.newId?.let { renameUser(change.targetId, it) }
        }
    }

    suspend fun deleteItem(qrId: String) {
        dao.deleteItemPending(qrId)
        dao.deleteItemHistory(qrId)
        dao.deleteItemHoldings(qrId)
        dao.deleteItemRow(qrId)
    }

    suspend fun renameItem(oldId: String, newId: String) {
        if (oldId == newId || dao.itemExists(oldId) == 0 || dao.itemExists(newId) > 0) return
        dao.renameItemRow(oldId, newId)
        dao.renameItemHoldings(oldId, newId)
        dao.renameItemHistory(oldId, newId)
        dao.renameItemPending(oldId, newId)
    }

    suspend fun deleteUser(userId: String) {
        val held = dao.itemsHeldBy(userId)
        dao.deleteUserPending(userId)
        dao.deleteUserHistory(userId)
        dao.deleteUserHoldings(userId)
        dao.deleteUserRow(userId)
        // What they had borrowed is back in stock. (Consumables keep their
        // stock: issued units stay issued.)
        val stock = LocalStock(db)
        held.forEach { stock.refresh(it) }
    }

    suspend fun renameUser(oldId: String, newId: String) {
        if (oldId == newId || dao.userExists(oldId) == 0 || dao.userExists(newId) > 0) return
        dao.renameUserRow(oldId, newId)
        dao.renameUserHoldings(oldId, newId)
        dao.renameUserHistory(oldId, newId)
        dao.renameUserPending(oldId, newId)
        dao.renameItemHolder(oldId, newId)
    }
}
