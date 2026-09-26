package com.kav1.warehouse.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

object ItemStatus {
    const val AVAILABLE = "AVAILABLE"
    const val BORROWED = "BORROWED"
}

object ActionType {
    const val BORROW = "BORROW"
    const val RETURN = "RETURN"

    fun resultingStatus(actionType: String): String =
        if (actionType == BORROW) ItemStatus.BORROWED else ItemStatus.AVAILABLE
}

@Entity(tableName = "items")
data class ItemEntity(
    @PrimaryKey @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "name") val name: String,
    @ColumnInfo(name = "current_status") val currentStatus: String,
)

@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "full_name") val fullName: String,
    @ColumnInfo(name = "unit") val unit: String,
)

/**
 * An action recorded on the device and not yet accepted by the server.
 *
 * [syncError] is set when the server permanently rejected the action (e.g. an
 * unknown user); such rows are excluded from future pushes until the operator
 * retries or discards them.
 */
@Entity(
    tableName = "pending_transactions",
    indices = [Index(value = ["sync_error"])],
)
data class PendingTransactionEntity(
    @PrimaryKey @ColumnInfo(name = "tx_id") val txId: String,
    @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "action_type") val actionType: String,
    /** Epoch milliseconds when the action happened on the device. */
    @ColumnInfo(name = "timestamp") val timestamp: Long,
    @ColumnInfo(name = "sync_error") val syncError: String? = null,
)
