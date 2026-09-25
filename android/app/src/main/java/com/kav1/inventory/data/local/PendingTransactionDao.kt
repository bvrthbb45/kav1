package com.kav1.inventory.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

@Dao
abstract class PendingTransactionDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    abstract suspend fun insert(tx: PendingTransaction)

    @Query("SELECT * FROM pending_transactions ORDER BY timestamp ASC LIMIT :limit")
    abstract suspend fun oldest(limit: Int): List<PendingTransaction>

    @Query("SELECT COUNT(*) FROM pending_transactions")
    abstract fun observeCount(): Flow<Int>

    @Query("SELECT DISTINCT qrId FROM pending_transactions")
    abstract suspend fun pendingQrIds(): List<String>

    @Query("DELETE FROM pending_transactions WHERE txId IN (:txIds)")
    abstract suspend fun deleteByIds(txIds: List<String>)

    @Query("UPDATE items SET status = :status WHERE qrId = :qrId")
    abstract suspend fun setItemStatus(qrId: String, status: String)

    /**
     * Queues [tx] and optimistically applies it to the local item so the UI reflects the
     * action immediately. The server's view overwrites it on the next successful pull.
     */
    @Transaction
    open suspend fun record(tx: PendingTransaction) {
        insert(tx)
        val newStatus = when (tx.actionType) {
            ActionType.BORROW -> ItemStatus.BORROWED
            ActionType.RETURN -> ItemStatus.AVAILABLE
        }
        setItemStatus(tx.qrId, newStatus)
    }
}
