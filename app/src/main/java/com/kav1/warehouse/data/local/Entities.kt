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

/** How an item is handed out. */
object ItemKind {
    /** מושאל: borrow and return only; the stock does not shrink. */
    const val LOAN = "LOAN"
    /** ניצרך: issue only; issued units leave the stock for good. */
    const val CONSUMABLE = "CONSUMABLE"
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
    /** Item type (e.g. "מכשיר קשר"); the QR / [qrId] is the item's serial number. */
    @ColumnInfo(name = "category", defaultValue = "''") val category: String = "",
    /** Units in stock under this QR, and where they are now (see StockRules). */
    @ColumnInfo(name = "quantity", defaultValue = "1") val quantity: Int = 1,
    @ColumnInfo(name = "available_qty", defaultValue = "1") val availableQty: Int = 1,
    @ColumnInfo(name = "borrowed_qty", defaultValue = "0") val borrowedQty: Int = 0,
    /** Loans: issued units still out (legacy). Consumables: units issued so far (ניפוקים). */
    @ColumnInfo(name = "issued_qty", defaultValue = "0") val issuedQty: Int = 0,
    /** [ItemKind]; for consumables [quantity] is what is left in stock. */
    @ColumnInfo(name = "kind", defaultValue = "'LOAN'") val kind: String = ItemKind.LOAN,
)

/** Units of one item held by one soldier. */
@Entity(
    tableName = "holdings",
    primaryKeys = ["qr_id", "user_id"],
    indices = [Index(value = ["user_id"])],
)
data class HoldingEntity(
    @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "borrowed") val borrowed: Int,
    @ColumnInfo(name = "issued") val issued: Int,
    /** Epoch ms of the soldier's latest action on the item. */
    @ColumnInfo(name = "since") val since: Long?,
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
    @ColumnInfo(name = "quantity", defaultValue = "1") val quantity: Int = 1,
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
    @ColumnInfo(name = "quantity", defaultValue = "1") val quantity: Int = 1,
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
    @ColumnInfo(name = "quantity") val quantity: Int,
    @ColumnInfo(name = "available_qty") val availableQty: Int,
    @ColumnInfo(name = "kind") val kind: String,
)

/** Soldier card row: units of an item a soldier holds. */
data class HeldItemRow(
    @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "name") val name: String?,
    @ColumnInfo(name = "category") val category: String?,
    @ColumnInfo(name = "borrowed") val borrowed: Int,
    @ColumnInfo(name = "issued") val issued: Int,
    @ColumnInfo(name = "since") val since: Long?,
)

/** Item screen row: a soldier holding units of the item. */
data class ItemHolderRow(
    @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "full_name") val fullName: String?,
    @ColumnInfo(name = "unit") val unit: String?,
    @ColumnInfo(name = "borrowed") val borrowed: Int,
    @ColumnInfo(name = "issued") val issued: Int,
    @ColumnInfo(name = "since") val since: Long?,
)

/** Units per status, summed over items (optionally per type). */
data class UnitTotals(
    @ColumnInfo(name = "category") val category: String,
    @ColumnInfo(name = "total") val total: Int,
    @ColumnInfo(name = "available") val available: Int,
    @ColumnInfo(name = "borrowed") val borrowed: Int,
    @ColumnInfo(name = "issued") val issued: Int,
)

/** One action in a history list, with names resolved; [pending] = not yet on the server. */
data class HistoryRow(
    @ColumnInfo(name = "tx_id") val txId: String,
    @ColumnInfo(name = "qr_id") val qrId: String,
    @ColumnInfo(name = "user_id") val userId: String,
    @ColumnInfo(name = "action_type") val actionType: String,
    @ColumnInfo(name = "timestamp") val timestamp: Long,
    @ColumnInfo(name = "quantity") val quantity: Int,
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

/** Kinds of [CatalogChangeEntity]; must match server/app/services.py. */
object CatalogOp {
    const val DELETE_ITEM = "DELETE_ITEM"
    const val DELETE_USER = "DELETE_USER"
    const val RENAME_ITEM = "RENAME_ITEM"
    const val RENAME_USER = "RENAME_USER"
}

/**
 * A delete or serial / personal number change made on this device, sent to
 * the server (in order) before the other edits on the next sync.
 */
@Entity(tableName = "catalog_changes")
data class CatalogChangeEntity(
    @PrimaryKey @ColumnInfo(name = "op_id") val opId: String,
    @ColumnInfo(name = "op") val op: String,
    @ColumnInfo(name = "target_id") val targetId: String,
    @ColumnInfo(name = "new_id") val newId: String?,
    @ColumnInfo(name = "created_at") val createdAt: Long,
)
