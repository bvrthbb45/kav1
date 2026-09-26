package com.kav1.warehouse.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

object ItemStatus {
    const val AVAILABLE = "AVAILABLE"
    const val BORROWED = "BORROWED"
    const val ISSUED = "ISSUED"
}

object ActionType {
    /** Temporary loan (השאלה). */
    const val BORROW = "BORROW"
    /** Permanent issue to a soldier (ניפוק). */
    const val ISSUE = "ISSUE"
    /** Back to the warehouse (החזרה). */
    const val RETURN = "RETURN"

    fun resultingStatus(actionType: String): String = when (actionType) {
        BORROW -> ItemStatus.BORROWED
        ISSUE -> ItemStatus.ISSUED
        else -> ItemStatus.AVAILABLE
    }

    /** Who holds the item after [actionType] by [userId]. */
    fun resultingHolder(actionType: String, userId: String): String? =
        if (actionType == RETURN) null else userId
}

@Entity(tableName = "items")
data class ItemEntity(
    @PrimaryKey @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "name") val name: String,
    @ColumnInfo(name = "current_status") val currentStatus: String,
    @ColumnInfo(name = "holder_user_id") val holderUserId: String? = null,
    /** Epoch ms (device time) of the latest action on this item. */
    @ColumnInfo(name = "last_action_at") val lastActionAt: Long? = null,
    /** Created/renamed in the management screen and not yet sent to the server. */
    @ColumnInfo(name = "pending_upload", defaultValue = "0") val pendingUpload: Boolean = false,
)

@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "full_name") val fullName: String,
    @ColumnInfo(name = "unit") val unit: String,
    @ColumnInfo(name = "pending_upload", defaultValue = "0") val pendingUpload: Boolean = false,
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

/** Dashboard row: an item plus the name of whoever holds it. */
data class ItemWithHolder(
    @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "name") val name: String,
    @ColumnInfo(name = "current_status") val currentStatus: String,
    @ColumnInfo(name = "holder_user_id") val holderUserId: String?,
    @ColumnInfo(name = "last_action_at") val lastActionAt: Long?,
    @ColumnInfo(name = "holder_name") val holderName: String?,
    @ColumnInfo(name = "holder_unit") val holderUnit: String?,
    @ColumnInfo(name = "pending_upload") val pendingUpload: Boolean,
)

data class StatusCount(
    @ColumnInfo(name = "status") val status: String,
    @ColumnInfo(name = "count") val count: Int,
)
