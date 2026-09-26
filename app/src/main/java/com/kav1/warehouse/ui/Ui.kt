package com.kav1.warehouse.ui

import android.app.Activity
import android.content.Context
import android.text.InputType
import android.text.format.DateFormat
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import com.kav1.warehouse.R
import com.kav1.warehouse.WarehouseApp
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.domain.sync.SyncResult
import java.util.Date

val Activity.app: WarehouseApp
    get() = application as WarehouseApp

fun Context.toast(message: String) =
    Toast.makeText(this, message, Toast.LENGTH_LONG).show()

fun Context.toast(resId: Int) = toast(getString(resId))

fun Context.statusLabel(status: String?): String = getString(
    when (status) {
        ItemStatus.AVAILABLE -> R.string.status_available
        ItemStatus.BORROWED -> R.string.status_borrowed
        ItemStatus.ISSUED -> R.string.status_issued
        else -> R.string.status_unknown
    },
)

fun Context.statusColor(status: String?): Int = ContextCompat.getColor(
    this,
    when (status) {
        ItemStatus.AVAILABLE -> R.color.return_green
        ItemStatus.BORROWED -> R.color.borrow
        ItemStatus.ISSUED -> R.color.issued
        else -> R.color.text_secondary
    },
)

fun Context.actionLabel(actionType: String): String = getString(
    when (actionType) {
        ActionType.BORROW -> R.string.action_borrow_short
        ActionType.ISSUE -> R.string.action_issue_short
        else -> R.string.action_return_short
    },
)

fun Context.formatDateTime(epochMs: Long): String {
    val date = Date(epochMs)
    return "${DateFormat.getDateFormat(this).format(date)} ${DateFormat.getTimeFormat(this).format(date)}"
}

/** A padded EditText suitable for AlertDialog.setView(). */
fun Context.dialogEditText(hint: Int, inputType: Int = InputType.TYPE_CLASS_TEXT): Pair<FrameLayout, EditText> {
    val edit = EditText(this).apply {
        setHint(hint)
        this.inputType = inputType
        setSingleLine(true)
    }
    val pad = (20 * resources.displayMetrics.density).toInt()
    val frame = FrameLayout(this).apply {
        setPadding(pad, pad / 2, pad, 0)
        addView(edit)
    }
    return frame to edit
}

/** Asks for the management PIN and runs [onSuccess] if it matches. */
fun Activity.requireAdminPin(onSuccess: () -> Unit) {
    val (view, edit) = dialogEditText(
        R.string.admin_pin_hint,
        InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD,
    )
    val dialog = AlertDialog.Builder(this)
        .setTitle(R.string.admin_pin_title)
        .setView(view)
        .setPositiveButton(R.string.btn_confirm, null)
        .setNegativeButton(R.string.btn_cancel, null)
        .create()
    dialog.setOnShowListener {
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            if (edit.text.toString() == app.prefs.adminPin) {
                dialog.dismiss()
                onSuccess()
            } else {
                edit.error = getString(R.string.admin_pin_wrong)
                edit.text.clear()
            }
        }
    }
    dialog.show()
}

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
