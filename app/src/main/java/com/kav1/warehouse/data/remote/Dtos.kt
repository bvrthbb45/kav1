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
)

data class ItemUpsertDto(
    @SerializedName("qr_id") val qrId: String,
    @SerializedName("name") val name: String,
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
