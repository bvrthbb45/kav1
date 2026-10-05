package com.kav1.warehouse.data.repository

import androidx.room.withTransaction
import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.CatalogChangeEntity
import com.kav1.warehouse.data.local.CatalogOp
import com.kav1.warehouse.data.local.CategorySummary
import com.kav1.warehouse.data.local.HeldItemRow
import com.kav1.warehouse.data.local.HistoryRow
import com.kav1.warehouse.data.local.HoldingEntity
import com.kav1.warehouse.data.local.ItemHolderRow
import com.kav1.warehouse.data.local.UnitTotals
import com.kav1.warehouse.data.local.ItemEntity
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.ItemWithHolder
import com.kav1.warehouse.data.local.PendingTransactionEntity
import com.kav1.warehouse.data.local.UserEntity
import com.kav1.warehouse.domain.stock.CatalogChanges
import com.kav1.warehouse.domain.stock.LocalStock
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import java.util.UUID

/** Local-only operations used by the UI. Network work lives in SyncManager. */
class InventoryRepository(private val db: AppDatabase) {

    suspend fun getItem(qrId: String): ItemEntity? = db.itemDao().getById(qrId)

    suspend fun getUsers(): List<UserEntity> = db.userDao().getAll()

    suspend fun getUser(userId: String): UserEntity? = db.userDao().getById(userId)

    /**
     * Records a borrow/issue/return of [quantity] units in the outbox and
     * optimistically updates the local stock, atomically.
     */
    suspend fun recordAction(qrId: String, userId: String, actionType: String, quantity: Int = 1, note: String = "") {
        val tx = PendingTransactionEntity(
            txId = UUID.randomUUID().toString(),
            qrId = qrId,
            userId = userId,
            actionType = actionType,
            timestamp = System.currentTimeMillis(),
            quantity = quantity.coerceAtLeast(1),
            note = note.trim().take(MAX_NOTE),
        )
        db.withTransaction {
            db.pendingTransactionDao().insert(tx)
            LocalStock(db).apply(qrId, userId, actionType, tx.quantity, tx.timestamp)
        }
    }

    suspend fun getHoldingsForItem(qrId: String): List<HoldingEntity> = db.holdingDao().getForItem(qrId)

    // --- Management (queued for upload on the next sync) ---

    /** Adds a new item, or edits an existing one; who holds what is kept. */
    suspend fun saveItem(
        qrId: String,
        name: String,
        category: String,
        quantity: Int,
        kind: String,
        location: String = "",
        department: String = "",
    ) {
        db.withTransaction {
            if (db.itemDao().updateLocal(qrId, name, category, quantity, kind, location, department) == 0) {
                db.itemDao().insert(
                    ItemEntity(
                        qrId,
                        name,
                        ItemStatus.AVAILABLE,
                        pendingUpload = true,
                        category = category,
                        quantity = quantity,
                        availableQty = quantity,
                        kind = kind,
                        location = location,
                        department = department,
                    ),
                )
            }
            LocalStock(db).refresh(qrId)
        }
    }

    /** True if [qrId] can be used for an item now named [currentQrId] (or a new one). */
    suspend fun isItemIdFree(qrId: String, currentQrId: String?): Boolean =
        qrId == currentQrId || db.catalogDao().itemExists(qrId) == 0

    suspend fun isUserIdFree(userId: String, currentUserId: String?): Boolean =
        userId == currentUserId || db.catalogDao().userExists(userId) == 0

    /** Changes an item's serial (QR); its history and holders move with it. */
    suspend fun renameItem(oldQrId: String, newQrId: String) {
        if (oldQrId == newQrId) return
        db.withTransaction {
            CatalogChanges(db).renameItem(oldQrId, newQrId)
            queue(CatalogOp.RENAME_ITEM, oldQrId, newQrId)
        }
    }

    /** Deletes an item and its history (also on the server, on the next sync). */
    suspend fun deleteItem(qrId: String) {
        db.withTransaction {
            CatalogChanges(db).deleteItem(qrId)
            queue(CatalogOp.DELETE_ITEM, qrId, null)
        }
    }

    suspend fun renameUser(oldUserId: String, newUserId: String) {
        if (oldUserId == newUserId) return
        db.withTransaction {
            CatalogChanges(db).renameUser(oldUserId, newUserId)
            queue(CatalogOp.RENAME_USER, oldUserId, newUserId)
        }
    }

    /** Deletes a soldier and their history; loaned units they held count as returned. */
    suspend fun deleteUser(userId: String) {
        db.withTransaction {
            CatalogChanges(db).deleteUser(userId)
            queue(CatalogOp.DELETE_USER, userId, null)
        }
    }

    private suspend fun queue(op: String, targetId: String, newId: String?) {
        db.catalogDao().queue(
            CatalogChangeEntity(UUID.randomUUID().toString(), op, targetId, newId, System.currentTimeMillis()),
        )
    }

    suspend fun getDepartmentNames(): List<String> = db.itemDao().getDepartmentNames()

    /** Known item types: from the server plus any typed on this device. */
    suspend fun getCategoryNames(): List<String> =
        (db.categoryDao().getNames() + db.itemDao().getCategoryNames()).distinct().sorted()

    suspend fun saveUser(userId: String, fullName: String, unit: String) {
        db.userDao().insert(UserEntity(userId, fullName, unit, pendingUpload = true))
    }

    // --- Observers ---

    fun observeUnsyncedCount(): Flow<Int> = db.pendingTransactionDao().observeUnsyncedCount()

    fun observeFailedCount(): Flow<Int> = db.pendingTransactionDao().observeFailedCount()

    fun observeItemCount(): Flow<Int> = db.itemDao().observeCount()

    fun observeUserCount(): Flow<Int> = db.userDao().observeCount()

    fun observePendingItemEdits(): Flow<Int> = db.itemDao().observePendingUploadCount()

    fun observePendingUserEdits(): Flow<Int> = db.userDao().observePendingUploadCount()

    fun observeQueuedChanges(): Flow<Int> = db.catalogDao().observeQueuedCount()

    /** Units (not item rows) per status, over all items. */
    fun observeUnitTotals(): Flow<UnitTotals> = db.itemDao().observeUnitTotals()

    fun observeItems(status: String?, query: String, category: String? = null): Flow<List<ItemWithHolder>> =
        db.itemDao().observeWithHolder(status, category, query.trim(), null)

    fun observeHeldBy(userId: String): Flow<List<HeldItemRow>> = db.holdingDao().observeForUser(userId)

    fun observeItemHolders(qrId: String): Flow<List<ItemHolderRow>> = db.holdingDao().observeForItem(qrId)

    fun observeUsers(query: String): Flow<List<UserEntity>> = db.userDao().observeFiltered(query.trim())

    fun observeItemHistory(qrId: String, limit: Int = 50): Flow<List<HistoryRow>> =
        db.historyDao().observe(qrId, null, limit)

    fun observeUserHistory(userId: String, limit: Int = 300): Flow<List<HistoryRow>> =
        db.historyDao().observe(null, userId, limit)

    /** Per item type: target and units per status; types without units are included. */
    fun observeCategorySummaries(): Flow<List<CategorySummary>> =
        combine(
            db.itemDao().observeUnitTotalsByCategory(),
            db.categoryDao().observeAll(),
        ) { totals, categories ->
            val byType = totals.associateBy { it.category }
            val targets = categories.associate { it.name to it.targetQty }
            (byType.keys + targets.keys).distinct()
                .sortedWith(compareBy({ it.isEmpty() }, { it }))
                .map { name ->
                    val t = byType[name]
                    CategorySummary(
                        name = name,
                        targetQty = targets[name],
                        total = t?.total ?: 0,
                        available = t?.available ?: 0,
                        borrowed = t?.borrowed ?: 0,
                        issued = t?.issued ?: 0,
                    )
                }
        }

    // --- Rejected transactions ---

    suspend fun getFailed(): List<PendingTransactionEntity> = db.pendingTransactionDao().getFailed()

    suspend fun retryFailed() = db.pendingTransactionDao().retryFailed()

    suspend fun deleteFailed() = db.pendingTransactionDao().deleteFailed()

    private companion object {
        /** Server-side limit (server/app/schemas.py). */
        const val MAX_NOTE = 500
    }
}
