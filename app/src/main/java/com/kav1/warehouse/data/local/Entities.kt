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
    /** Item type (e.g. "מכשיר קשר"); the QR / [qrId] is the unit's serial number. */
    @ColumnInfo(name = "category", defaultValue = "''") val category: String = "",
)

/** An item type with its target quantity (תקן), from the server. */
@Entity(tableName = "categories")
data class CategoryEntity(
    @PrimaryKey @ColumnInfo(name = "name") val name: String,
    @ColumnInfo(name = "target_qty") val targetQty: Int?,
)

/** A past action already stored on the server (item history / soldier card). */
@Entity(
    tableName = "history",
    indices = [Index(value = ["qr_id"]), Index(value = ["user_id"])],
)
data class HistoryEntity(
    @PrimaryKey @ColumnInfo(name = "tx_id") val txId: String,
    @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "action_type") val actionType: String,
    @ColumnInfo(name = "timestamp") val timestamp: Long,
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
    @ColumnInfo(name = "category") val category: String,
)

/** One action in a history list, with names resolved; [pending] = not yet on the server. */
data class HistoryRow(
    @ColumnInfo(name = "tx_id") val txId: String,
    @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "action_type") val actionType: String,
    @ColumnInfo(name = "timestamp") val timestamp: Long,
    @ColumnInfo(name = "pending") val pending: Boolean,
    @ColumnInfo(name = "item_name") val itemName: String?,
    @ColumnInfo(name = "category") val category: String?,
    @ColumnInfo(name = "user_name") val userName: String?,
)

data class CategoryStatusCount(
    @ColumnInfo(name = "category") val category: String,
    @ColumnInfo(name = "status") val status: String,
    @ColumnInfo(name = "count") val count: Int,
)

/** Dashboard row per item type. */
data class CategorySummary(
    val name: String,
    val targetQty: Int?,
    val total: Int,
    val available: Int,
    val borrowed: Int,
    val issued: Int,
) {
    /** Units still missing to reach the target, or null without a target. */
    val missing: Int? get() = targetQty?.let { (it - total).coerceAtLeast(0) }
}

data class StatusCount(
    @ColumnInfo(name = "status") val status: String,
    @ColumnInfo(name = "count") val count: Int,
)
