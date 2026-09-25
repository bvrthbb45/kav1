package com.kav1.inventory.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "items")
data class Item(
    @PrimaryKey val qrId: String,
    val name: String,
    /** One of [ItemStatus]; kept as a String so unknown server values don't break decoding. */
    val status: String,
)

object ItemStatus {
    const val AVAILABLE = "AVAILABLE"
    const val BORROWED = "BORROWED"
}

@Entity(tableName = "users")
data class User(
    @PrimaryKey val userId: String,
    val name: String,
)

enum class ActionType { BORROW, RETURN }

/** A scan recorded offline, waiting to be pushed to the server by the SyncWorker. */
@Entity(
    tableName = "pending_transactions",
    indices = [Index("qrId")],
)
data class PendingTransaction(
    /** Client-generated UUID; lets the server de-duplicate retried pushes. */
    @PrimaryKey val txId: String,
    val qrId: String,
    val userId: String,
    val actionType: ActionType,
    /** Epoch millis when the action happened on the device. */
    val timestamp: Long,
)
