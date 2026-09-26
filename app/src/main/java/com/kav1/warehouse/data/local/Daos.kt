package com.kav1.warehouse.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

/** Keeps IN (...) lists under SQLite's 999-variable limit on old devices. */
private const val SQL_CHUNK = 500

@Dao
abstract class ItemDao {
    @Query("SELECT * FROM items WHERE qr_id = :qrId LIMIT 1")
    abstract suspend fun getById(qrId: String): ItemEntity?

    @Query("UPDATE items SET current_status = :status WHERE qr_id = :qrId")
    abstract suspend fun updateStatus(qrId: String, status: String)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAll(items: List<ItemEntity>)

    @Query("DELETE FROM items")
    abstract suspend fun deleteAll()

    @Query("SELECT COUNT(*) FROM items")
    abstract fun observeCount(): Flow<Int>

    @Transaction
    open suspend fun replaceAll(items: List<ItemEntity>) {
        deleteAll()
        items.chunked(SQL_CHUNK).forEach { insertAll(it) }
    }
}

@Dao
abstract class UserDao {
    @Query("SELECT * FROM users ORDER BY full_name")
    abstract suspend fun getAll(): List<UserEntity>

    @Query("SELECT * FROM users WHERE user_id = :userId LIMIT 1")
    abstract suspend fun getById(userId: String): UserEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAll(users: List<UserEntity>)

    @Query("DELETE FROM users")
    abstract suspend fun deleteAll()

    @Query("SELECT COUNT(*) FROM users")
    abstract fun observeCount(): Flow<Int>

    @Transaction
    open suspend fun replaceAll(users: List<UserEntity>) {
        deleteAll()
        users.chunked(SQL_CHUNK).forEach { insertAll(it) }
    }
}

@Dao
abstract class PendingTransactionDao {
    @Insert(onConflict = OnConflictStrategy.ABORT)
    abstract suspend fun insert(tx: PendingTransactionEntity)

    /** Transactions waiting to be pushed, oldest first. */
    @Query("SELECT * FROM pending_transactions WHERE sync_error IS NULL ORDER BY timestamp")
    abstract suspend fun getUnsynced(): List<PendingTransactionEntity>

    @Query("SELECT * FROM pending_transactions WHERE sync_error IS NOT NULL ORDER BY timestamp")
    abstract suspend fun getFailed(): List<PendingTransactionEntity>

    @Query("SELECT COUNT(*) FROM pending_transactions WHERE sync_error IS NULL")
    abstract fun observeUnsyncedCount(): Flow<Int>

    @Query("SELECT COUNT(*) FROM pending_transactions WHERE sync_error IS NOT NULL")
    abstract fun observeFailedCount(): Flow<Int>

    @Query("DELETE FROM pending_transactions WHERE tx_id IN (:txIds)")
    abstract suspend fun deleteByIdsChunk(txIds: List<String>)

    @Transaction
    open suspend fun deleteByIds(txIds: List<String>) {
        txIds.chunked(SQL_CHUNK).forEach { deleteByIdsChunk(it) }
    }

    @Query("UPDATE pending_transactions SET sync_error = :error WHERE tx_id = :txId")
    abstract suspend fun markFailed(txId: String, error: String)

    /** Puts rejected transactions back in the queue (e.g. after the user was added on the server). */
    @Query("UPDATE pending_transactions SET sync_error = NULL WHERE sync_error IS NOT NULL")
    abstract suspend fun retryFailed()

    @Query("DELETE FROM pending_transactions WHERE sync_error IS NOT NULL")
    abstract suspend fun deleteFailed()
}
