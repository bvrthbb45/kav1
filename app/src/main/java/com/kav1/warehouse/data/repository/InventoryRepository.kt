package com.kav1.warehouse.data.repository

import androidx.room.withTransaction
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.CategorySummary
import com.kav1.warehouse.data.local.HistoryRow
import com.kav1.warehouse.data.local.ItemEntity
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.ItemWithHolder
import com.kav1.warehouse.data.local.PendingTransactionEntity
import com.kav1.warehouse.data.local.StatusCount
import com.kav1.warehouse.data.local.UserEntity
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import java.util.UUID

/** Local-only operations used by the UI. Network work lives in SyncManager. */
class InventoryRepository(private val db: AppDatabase) {

    suspend fun getItem(qrId: String): ItemEntity? = db.itemDao().getById(qrId)

    suspend fun getUsers(): List<UserEntity> = db.userDao().getAll()

    suspend fun getUser(userId: String): UserEntity? = db.userDao().getById(userId)

    /**
     * Records a borrow/issue/return in the outbox and optimistically updates
     * the local item, atomically.
     */
    suspend fun recordAction(qrId: String, userId: String, actionType: String) {
        val tx = PendingTransactionEntity(
            txId = UUID.randomUUID().toString(),
            qrId = qrId,
            userId = userId,
            actionType = actionType,
            timestamp = System.currentTimeMillis(),
        )
        db.withTransaction {
            db.pendingTransactionDao().insert(tx)
            db.itemDao().applyAction(
                qrId,
                ActionType.resultingStatus(actionType),
                ActionType.resultingHolder(actionType, userId),
                tx.timestamp,
            )
        }
    }

    // --- Management (queued for upload on the next sync) ---

    /** Adds a new item, or edits an existing one without touching its status. */
    suspend fun saveItem(qrId: String, name: String, category: String) {
        db.withTransaction {
            if (db.itemDao().updateLocal(qrId, name, category) == 0) {
                db.itemDao().insert(
                    ItemEntity(qrId, name, ItemStatus.AVAILABLE, pendingUpload = true, category = category),
                )
            }
        }
    }

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

    fun observeStatusCounts(): Flow<List<StatusCount>> = db.itemDao().observeStatusCounts()

    fun observeItems(status: String?, query: String, category: String? = null): Flow<List<ItemWithHolder>> =
        db.itemDao().observeWithHolder(status, category, query.trim(), null)

    fun observeHeldBy(userId: String): Flow<List<ItemWithHolder>> =
        db.itemDao().observeWithHolder(null, null, "", userId)

    fun observeItemHistory(qrId: String, limit: Int = 50): Flow<List<HistoryRow>> =
        db.historyDao().observe(qrId, null, limit)

    fun observeUserHistory(userId: String, limit: Int = 300): Flow<List<HistoryRow>> =
        db.historyDao().observe(null, userId, limit)

    /** Per item type: target and units per status; types without units are included. */
    fun observeCategorySummaries(): Flow<List<CategorySummary>> =
        combine(
            db.itemDao().observeCategoryStatusCounts(),
            db.categoryDao().observeAll(),
        ) { counts, categories ->
            val byType = counts.groupBy { it.category }
            val targets = categories.associate { it.name to it.targetQty }
            (byType.keys + targets.keys).distinct()
                .sortedWith(compareBy({ it.isEmpty() }, { it }))
                .map { name ->
                    val c = byType[name].orEmpty().associate { it.status to it.count }
                    CategorySummary(
                        name = name,
                        targetQty = targets[name],
                        total = c.values.sum(),
                        available = c[ItemStatus.AVAILABLE] ?: 0,
                        borrowed = c[ItemStatus.BORROWED] ?: 0,
                        issued = c[ItemStatus.ISSUED] ?: 0,
                    )
                }
        }

    fun observeUsers(query: String): Flow<List<UserEntity>> = db.userDao().observeFiltered(query.trim())

    // --- Rejected transactions ---

    suspend fun getFailed(): List<PendingTransactionEntity> = db.pendingTransactionDao().getFailed()

    suspend fun retryFailed() = db.pendingTransactionDao().retryFailed()

    suspend fun deleteFailed() = db.pendingTransactionDao().deleteFailed()
}
