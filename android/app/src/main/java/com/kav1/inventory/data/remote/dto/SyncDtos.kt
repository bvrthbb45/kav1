package com.kav1.inventory.data.remote.dto

import com.google.gson.annotations.SerializedName

// JSON contract for the FastAPI sync endpoints. Collections are nullable because Gson
// ignores Kotlin default values when a field is missing from the payload.

data class TransactionDto(
    @SerializedName("tx_id") val txId: String,
    @SerializedName("qr_id") val qrId: String,
    @SerializedName("user_id") val userId: String,
    /** "BORROW" or "RETURN". */
    @SerializedName("action_type") val actionType: String,
    /** Epoch millis on the device when the action happened. */
    @SerializedName("timestamp") val timestamp: Long,
)

data class SyncPushRequest(
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("transactions") val transactions: List<TransactionDto>,
)

data class RejectedTxDto(
    @SerializedName("tx_id") val txId: String,
    @SerializedName("reason") val reason: String?,
)

data class SyncPushResponse(
    /** txIds the server stored (or had already stored — pushes must be idempotent). */
    @SerializedName("accepted") val accepted: List<String>?,
    /** txIds the server will never accept (e.g. unknown item); dropped from the queue. */
    @SerializedName("rejected") val rejected: List<RejectedTxDto>?,
)

data class ItemDto(
    @SerializedName("qr_id") val qrId: String,
    @SerializedName("name") val name: String,
    @SerializedName("status") val status: String,
)

data class UserDto(
    @SerializedName("user_id") val userId: String,
    @SerializedName("name") val name: String,
)

data class SyncPullResponse(
    /** Server clock (epoch millis); sent back as `since` on the next pull. */
    @SerializedName("server_time") val serverTime: Long,
    @SerializedName("items") val items: List<ItemDto>?,
    @SerializedName("users") val users: List<UserDto>?,
    @SerializedName("deleted_item_ids") val deletedItemIds: List<String>?,
    @SerializedName("deleted_user_ids") val deletedUserIds: List<String>?,
)
