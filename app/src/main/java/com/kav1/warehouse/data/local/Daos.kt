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

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAll(items: List<ItemEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insert(item: ItemEntity)

    @Query(
        "UPDATE items SET name = :name, category = :category, quantity = :quantity, kind = :kind, " +
            "pending_upload = 1 WHERE qr_id = :qrId",
    )
    abstract suspend fun updateLocal(qrId: String, name: String, category: String, quantity: Int, kind: String): Int

    /** Consumables: what is left in stock and how many were issued so far. */
    @Query(
        "UPDATE items SET quantity = :quantity, available_qty = :quantity, issued_qty = :issued, " +
            "current_status = :status WHERE qr_id = :qrId",
    )
    abstract suspend fun updateConsumable(qrId: String, quantity: Int, issued: Int, status: String)

    @Query(
        "UPDATE items SET current_status = :status, holder_user_id = :holderUserId, " +
            "available_qty = :available, borrowed_qty = :borrowed, issued_qty = :issued WHERE qr_id = :qrId",
    )
    abstract suspend fun updateStock(
        qrId: String,
        status: String,
        holderUserId: String?,
        available: Int,
        borrowed: Int,
        issued: Int,
    )

    @Query("UPDATE items SET last_action_at = :at WHERE qr_id = :qrId")
    abstract suspend fun setLastAction(qrId: String, at: Long)

    @Query(
        "SELECT '' AS category, IFNULL(SUM(quantity), 0) AS total, IFNULL(SUM(available_qty), 0) AS available, " +
            "IFNULL(SUM(borrowed_qty), 0) AS borrowed, IFNULL(SUM(issued_qty), 0) AS issued FROM items",
    )
    abstract fun observeUnitTotals(): Flow<UnitTotals>

    @Query(
        "SELECT category, SUM(quantity) AS total, SUM(available_qty) AS available, " +
            "SUM(borrowed_qty) AS borrowed, SUM(issued_qty) AS issued FROM items GROUP BY category",
    )
    abstract fun observeUnitTotalsByCategory(): Flow<List<UnitTotals>>

    @Query("DELETE FROM items")
    abstract suspend fun deleteAll()

    @Query("SELECT * FROM items WHERE pending_upload = 1")
    abstract suspend fun getPendingUpload(): List<ItemEntity>

    /** Clears the flag only if the row was not edited again meanwhile. */
    @Query(
        "UPDATE items SET pending_upload = 0 WHERE qr_id = :qrId AND name = :sentName " +
            "AND category = :sentCategory AND quantity = :sentQuantity AND kind = :sentKind",
    )
    abstract suspend fun markUploaded(
        qrId: String,
        sentName: String,
        sentCategory: String,
        sentQuantity: Int,
        sentKind: String,
    )

    @Query("SELECT COUNT(*) FROM items")
    abstract fun observeCount(): Flow<Int>

    @Query("SELECT COUNT(*) FROM items WHERE pending_upload = 1")
    abstract fun observePendingUploadCount(): Flow<Int>

    @Query("SELECT current_status AS status, COUNT(*) AS count FROM items GROUP BY current_status")
    abstract fun observeStatusCounts(): Flow<List<StatusCount>>

    @Query(
        "SELECT category, current_status AS status, COUNT(*) AS count FROM items " +
            "GROUP BY category, current_status",
    )
    abstract fun observeCategoryStatusCounts(): Flow<List<CategoryStatusCount>>

    @Query("SELECT DISTINCT category FROM items WHERE category != '' ORDER BY category")
    abstract suspend fun getCategoryNames(): List<String>

    /**
     * [status] / [category] null = any; [query] matches name, serial, type or holder.
     * [holderId] non-null limits to items held by that soldier.
     */
    @Query(
        """
        SELECT i.qr_id, i.name, i.current_status, i.holder_user_id, i.last_action_at,
               i.pending_upload, i.category, i.quantity, i.available_qty, i.kind,
               u.full_name AS holder_name, u.unit AS holder_unit
        FROM items i LEFT JOIN users u ON u.user_id = i.holder_user_id
        WHERE (:status IS NULL
               OR (:status = 'AVAILABLE' AND i.available_qty > 0)
               OR (:status = 'BORROWED' AND i.borrowed_qty > 0)
               OR (:status = 'ISSUED' AND i.issued_qty > 0))
          AND (:category IS NULL OR i.category = :category)
          AND (:holderId IS NULL OR i.holder_user_id = :holderId)
          AND (:query = '' OR i.name LIKE '%' || :query || '%'
               OR i.qr_id LIKE '%' || :query || '%'
               OR i.category LIKE '%' || :query || '%'
               OR u.full_name LIKE '%' || :query || '%'
               OR u.user_id LIKE '%' || :query || '%')
        ORDER BY i.category, i.name, i.qr_id
        """,
    )
    abstract fun observeWithHolder(
        status: String?,
        category: String?,
        query: String,
        holderId: String?,
    ): Flow<List<ItemWithHolder>>

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
            if (updateLocal(edit.qrId, edit.name, edit.category, edit.quantity, edit.kind) == 0) insert(edit)
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

@Dao
abstract class CategoryDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAll(categories: List<CategoryEntity>)

    @Query("DELETE FROM categories")
    abstract suspend fun deleteAll()

    @Query("SELECT * FROM categories ORDER BY name")
    abstract fun observeAll(): Flow<List<CategoryEntity>>

    @Query("SELECT name FROM categories ORDER BY name")
    abstract suspend fun getNames(): List<String>

    @Transaction
    open suspend fun replaceAll(categories: List<CategoryEntity>) {
        deleteAll()
        insertAll(categories)
    }
}

@Dao
abstract class HistoryDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAll(rows: List<HistoryEntity>)

    @Query("DELETE FROM history")
    abstract suspend fun deleteAll()

    @Transaction
    open suspend fun replaceAll(rows: List<HistoryEntity>) {
        deleteAll()
        rows.chunked(SQL_CHUNK).forEach { insertAll(it) }
    }

    /** Server history plus this device's not-yet-synced actions, newest first. */
    @Query(
        """
        SELECT h.tx_id, h.qr_id, h.user_id, h.action_type, h.timestamp, h.quantity, h.pending,
               i.name AS item_name, i.category AS category, u.full_name AS user_name
        FROM (
            SELECT tx_id, qr_id, user_id, action_type, timestamp, quantity, 0 AS pending
            FROM history WHERE (:qrId IS NULL OR qr_id = :qrId) AND (:userId IS NULL OR user_id = :userId)
            UNION ALL
            SELECT tx_id, qr_id, user_id, action_type, timestamp, quantity, 1 AS pending
            FROM pending_transactions
            WHERE sync_error IS NULL AND (:qrId IS NULL OR qr_id = :qrId)
              AND (:userId IS NULL OR user_id = :userId)
        ) h
        LEFT JOIN items i ON i.qr_id = h.qr_id
        LEFT JOIN users u ON u.user_id = h.user_id
        ORDER BY h.timestamp DESC
        LIMIT :limit
        """,
    )
    abstract fun observe(qrId: String?, userId: String?, limit: Int): Flow<List<HistoryRow>>
}

@Dao
abstract class HoldingDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAll(rows: List<HoldingEntity>)

    @Query("DELETE FROM holdings")
    abstract suspend fun deleteAll()

    @Query("SELECT * FROM holdings WHERE qr_id = :qrId")
    abstract suspend fun getForItem(qrId: String): List<HoldingEntity>

    @Query("DELETE FROM holdings WHERE qr_id = :qrId")
    abstract suspend fun deleteForItem(qrId: String)

    @Transaction
    open suspend fun replaceAll(rows: List<HoldingEntity>) {
        deleteAll()
        rows.chunked(SQL_CHUNK).forEach { insertAll(it) }
    }

    @Transaction
    open suspend fun replaceForItem(qrId: String, rows: List<HoldingEntity>) {
        deleteForItem(qrId)
        insertAll(rows)
    }

    @Query(
        """
        SELECT h.qr_id, i.name, i.category, h.borrowed, h.issued, h.since
        FROM holdings h LEFT JOIN items i ON i.qr_id = h.qr_id
        WHERE h.user_id = :userId
        ORDER BY i.category, i.name
        """,
    )
    abstract fun observeForUser(userId: String): Flow<List<HeldItemRow>>

    @Query(
        """
        SELECT h.user_id, u.full_name, u.unit, h.borrowed, h.issued, h.since
        FROM holdings h LEFT JOIN users u ON u.user_id = h.user_id
        WHERE h.qr_id = :qrId
        ORDER BY h.since DESC
        """,
    )
    abstract fun observeForItem(qrId: String): Flow<List<ItemHolderRow>>
}
