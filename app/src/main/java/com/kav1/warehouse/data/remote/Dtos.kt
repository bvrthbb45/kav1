package com.kav1.warehouse.data.remote

import com.google.gson.annotations.SerializedName

// Fields are nullable because Gson bypasses Kotlin null-safety; callers must
// treat missing values as a malformed response.

data class PendingTransactionDto(
    @SerializedName("tx_id") val txId: String,
    @SerializedName("qr_id") val qrId: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("action_type") val actionType: String,
    @SerializedName("timestamp") val timestamp: Long,
    @SerializedName("quantity") val quantity: Int,
)

data class PushRequestDto(
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("transactions") val transactions: List<PendingTransactionDto>,
)

data class TxResultDto(
    @SerializedName("tx_id") val txId: String?,
    @SerializedName("accepted") val accepted: Boolean?,
    @SerializedName("message") val message: String?,
)

data class PushResponseDto(
    @SerializedName("success") val success: Boolean?,
    @SerializedName("message") val message: String?,
    @SerializedName("accepted") val accepted: List<String>?,
    @SerializedName("rejected") val rejected: List<TxResultDto>?,
)

data class ItemDto(
    @SerializedName("qr_id") val qrId: String?,
    @SerializedName("name") val name: String?,
    @SerializedName("current_status") val currentStatus: String?,
    @SerializedName("holder_user_id") val holderUserId: String?,
    @SerializedName("last_action_at") val lastActionAt: Long?,
    @SerializedName("category") val category: String?,
    // Missing from servers older than 1.6.
    @SerializedName("quantity") val quantity: Int?,
    @SerializedName("available_qty") val availableQty: Int?,
    @SerializedName("borrowed_qty") val borrowedQty: Int?,
    @SerializedName("issued_qty") val issuedQty: Int?,
)

data class HoldingDto(
    @SerializedName("qr_id") val qrId: String?,
    @SerializedName("user_id") val userId: String?,
    @SerializedName("borrowed") val borrowed: Int?,
    @SerializedName("issued") val issued: Int?,
    @SerializedName("since") val since: Long?,
)

data class UserDto(
    @SerializedName("user_id") val userId: String?,
    @SerializedName("full_name") val fullName: String?,
    @SerializedName("unit") val unit: String?,
)

data class PullResponseDto(
    @SerializedName("success") val success: Boolean?,
    @SerializedName("message") val message: String?,
    @SerializedName("server_time") val serverTime: Long?,
    @SerializedName("items") val items: List<ItemDto>?,
    @SerializedName("users") val users: List<UserDto>?,
    /** Missing from servers older than 1.5; treated as empty. */
    @SerializedName("categories") val categories: List<CategoryDto>?,
    @SerializedName("history") val history: List<HistoryDto>?,
    @SerializedName("holdings") val holdings: List<HoldingDto>?,
)

data class CategoryDto(
    @SerializedName("name") val name: String?,
    @SerializedName("target_qty") val targetQty: Int?,
)

data class HistoryDto(
    @SerializedName("tx_id") val txId: String?,
    @SerializedName("qr_id") val qrId: String?,
    @SerializedName("user_id") val userId: String?,
    @SerializedName("action_type") val actionType: String?,
    @SerializedName("timestamp") val timestamp: Long?,
    @SerializedName("quantity") val quantity: Int?,
)

data class ItemUpsertDto(
    @SerializedName("qr_id") val qrId: String,
    @SerializedName("name") val name: String,
    // Nullable: Gson leaves it null when reading an older server's echo.
    @SerializedName("category") val category: String?,
    @SerializedName("quantity") val quantity: Int?,
)

data class UserUpsertDto(
    @SerializedName("user_id") val userId: String,
    @SerializedName("full_name") val fullName: String,
    @SerializedName("unit") val unit: String,
)

data class UpsertResponseDto(
    @SerializedName("success") val success: Boolean?,
    @SerializedName("message") val message: String?,
    @SerializedName("count") val count: Int?,
)

/** Shape of every error body returned by the server. */
data class ErrorDto(
    @SerializedName("message") val message: String?,
)

// --- Wired (ADB) sync files; must match server/app/usb_sync.py ---

/** outbox.json, written by the tablet for the PC agent. */
data class UsbOutboxDto(
    @SerializedName("request_id") val requestId: String,
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("transactions") val transactions: List<PendingTransactionDto>,
    @SerializedName("items") val items: List<ItemUpsertDto>,
    @SerializedName("users") val users: List<UserUpsertDto>,
)

/** inbox.json, written by the PC agent with the server's answers. */
data class UsbInboxDto(
    @SerializedName("request_id") val requestId: String?,
    @SerializedName("push") val push: PushResponseDto?,
    @SerializedName("items_uploaded") val itemsUploaded: List<ItemUpsertDto>?,
    @SerializedName("users_uploaded") val usersUploaded: List<UserUpsertDto>?,
    @SerializedName("state") val state: PullResponseDto?,
)
