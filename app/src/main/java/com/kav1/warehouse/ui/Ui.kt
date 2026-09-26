package com.kav1.warehouse.ui

import android.app.Activity
import android.content.Context
import android.widget.Toast
import com.kav1.warehouse.R
import com.kav1.warehouse.WarehouseApp
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.domain.sync.SyncResult

val Activity.app: WarehouseApp
    get() = application as WarehouseApp

fun Context.toast(message: String) =
    Toast.makeText(this, message, Toast.LENGTH_LONG).show()

fun Context.toast(resId: Int) = toast(getString(resId))

fun Context.statusLabel(status: String?): String = getString(
    when (status) {
        ItemStatus.AVAILABLE -> R.string.status_available
        ItemStatus.BORROWED -> R.string.status_borrowed
        else -> R.string.status_unknown
    },
)

fun Context.actionLabel(actionType: String): String = getString(
    if (actionType == ActionType.BORROW) R.string.action_borrow_short else R.string.action_return_short,
)

fun Context.syncResultMessage(result: SyncResult): String = when (result) {
    is SyncResult.Success ->
        if (result.rejected > 0) {
            getString(R.string.sync_success_with_rejected, result.rejected)
        } else {
            getString(R.string.sync_success, result.pushed, result.itemCount, result.userCount)
        }
    SyncResult.Offline -> getString(R.string.sync_offline)
    is SyncResult.ServerError ->
        if (result.message.isNullOrBlank()) {
            getString(R.string.sync_server_error_no_message, result.code)
        } else {
            getString(R.string.sync_server_error, result.code, result.message)
        }
    SyncResult.InvalidResponse -> getString(R.string.sync_invalid_response)
    is SyncResult.Failed -> getString(R.string.sync_failed)
}
