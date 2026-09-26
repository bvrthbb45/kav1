package com.kav1.warehouse.data.repository

import androidx.room.withTransaction
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.ItemEntity
import com.kav1.warehouse.data.local.PendingTransactionEntity
import com.kav1.warehouse.data.local.UserEntity
import kotlinx.coroutines.flow.Flow
import java.util.UUID

/** Local-only operations used by the UI. Network work lives in SyncManager. */
class InventoryRepository(private val db: AppDatabase) {

    suspend fun getItem(qrId: String): ItemEntity? = db.itemDao().getById(qrId)

    suspend fun getUsers(): List<UserEntity> = db.userDao().getAll()

    suspend fun getUser(userId: String): UserEntity? = db.userDao().getById(userId)

    /**
     * Records a borrow/return in the outbox and optimistically updates the
     * local item status, atomically.
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
            db.itemDao().updateStatus(qrId, ActionType.resultingStatus(actionType))
        }
    }

    fun observeUnsyncedCount(): Flow<Int> = db.pendingTransactionDao().observeUnsyncedCount()

    fun observeFailedCount(): Flow<Int> = db.pendingTransactionDao().observeFailedCount()

    fun observeItemCount(): Flow<Int> = db.itemDao().observeCount()

    fun observeUserCount(): Flow<Int> = db.userDao().observeCount()

    suspend fun getFailed(): List<PendingTransactionEntity> = db.pendingTransactionDao().getFailed()

    suspend fun retryFailed() = db.pendingTransactionDao().retryFailed()

    suspend fun deleteFailed() = db.pendingTransactionDao().deleteFailed()
}
