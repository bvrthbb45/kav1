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

    @Query(
        "UPDATE items SET current_status = :status, holder_user_id = :holderUserId, " +
            "last_action_at = :at WHERE qr_id = :qrId",
    )
    abstract suspend fun applyAction(qrId: String, status: String, holderUserId: String?, at: Long)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAll(items: List<ItemEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insert(item: ItemEntity)

    @Query("UPDATE items SET name = :name, pending_upload = 1 WHERE qr_id = :qrId")
    abstract suspend fun renameLocal(qrId: String, name: String): Int

    @Query("DELETE FROM items")
    abstract suspend fun deleteAll()

    @Query("SELECT * FROM items WHERE pending_upload = 1")
    abstract suspend fun getPendingUpload(): List<ItemEntity>

    /** Clears the flag only if the row was not edited again meanwhile. */
    @Query("UPDATE items SET pending_upload = 0 WHERE qr_id = :qrId AND name = :sentName")
    abstract suspend fun markUploaded(qrId: String, sentName: String)

    @Query("SELECT COUNT(*) FROM items")
    abstract fun observeCount(): Flow<Int>

    @Query("SELECT COUNT(*) FROM items WHERE pending_upload = 1")
    abstract fun observePendingUploadCount(): Flow<Int>

    @Query("SELECT current_status AS status, COUNT(*) AS count FROM items GROUP BY current_status")
    abstract fun observeStatusCounts(): Flow<List<StatusCount>>

    /** [status] null = all statuses; [query] matches name, code or holder name. */
    @Query(
        """
        SELECT i.qr_id, i.name, i.current_status, i.holder_user_id, i.last_action_at,
               i.pending_upload, u.full_name AS holder_name, u.unit AS holder_unit
        FROM items i LEFT JOIN users u ON u.user_id = i.holder_user_id
        WHERE (:status IS NULL OR i.current_status = :status)
          AND (:query = '' OR i.name LIKE '%' || :query || '%'
               OR i.qr_id LIKE '%' || :query || '%'
               OR u.full_name LIKE '%' || :query || '%'
               OR u.user_id LIKE '%' || :query || '%')
        ORDER BY i.name
        """,
    )
    abstract fun observeWithHolder(status: String?, query: String): Flow<List<ItemWithHolder>>

    /**
     * Replaces all items with the server's list, keeping local edits that
     * have not been uploaded yet (their name wins; status stays the server's).
     */
    @Transaction
    open suspend fun replaceAll(items: List<ItemEntity>) {
        val localEdits = getPendingUpload()
        deleteAll()
        items.chunked(SQL_CHUNK).forEach { insertAll(it) }
        localEdits.forEach { edit ->
            if (renameLocal(edit.qrId, edit.name) == 0) insert(edit)
        }
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

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insert(user: UserEntity)

    @Query("DELETE FROM users")
    abstract suspend fun deleteAll()

    @Query("SELECT * FROM users WHERE pending_upload = 1")
    abstract suspend fun getPendingUpload(): List<UserEntity>

    @Query(
        "UPDATE users SET pending_upload = 0 WHERE user_id = :userId " +
            "AND full_name = :sentName AND unit = :sentUnit",
    )
    abstract suspend fun markUploaded(userId: String, sentName: String, sentUnit: String)

    @Query("SELECT COUNT(*) FROM users")
    abstract fun observeCount(): Flow<Int>

    @Query("SELECT COUNT(*) FROM users WHERE pending_upload = 1")
    abstract fun observePendingUploadCount(): Flow<Int>

    @Query(
        """
        SELECT * FROM users
        WHERE :query = '' OR full_name LIKE '%' || :query || '%'
              OR user_id LIKE '%' || :query || '%' OR unit LIKE '%' || :query || '%'
        ORDER BY full_name
        """,
    )
    abstract fun observeFiltered(query: String): Flow<List<UserEntity>>

    /** Replaces all users with the server's list, keeping not-yet-uploaded local edits. */
    @Transaction
    open suspend fun replaceAll(users: List<UserEntity>) {
        val localEdits = getPendingUpload()
        deleteAll()
        users.chunked(SQL_CHUNK).forEach { insertAll(it) }
        if (localEdits.isNotEmpty()) insertAll(localEdits)
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
