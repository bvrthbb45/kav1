package com.kav1.warehouse.ui

import android.app.Activity
import android.content.Context
import android.text.InputType
import android.text.format.DateFormat
import android.view.LayoutInflater
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import com.kav1.warehouse.R
import com.kav1.warehouse.WarehouseApp
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.HistoryRow
import com.kav1.warehouse.data.local.ItemKind
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

/** Item status in words; consumables read "in stock" / "out of stock". */
fun Context.itemStatusLabel(kind: String, status: String?): String =
    if (kind == ItemKind.CONSUMABLE) {
        getString(if (status == ItemStatus.ISSUED) R.string.status_out_of_stock else R.string.status_in_stock)
    } else {
        statusLabel(status)
    }

fun Context.kindLabel(kind: String): String =
    getString(if (kind == ItemKind.CONSUMABLE) R.string.kind_consumable else R.string.kind_loan)

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

fun Context.actionColor(actionType: String): Int = ContextCompat.getColor(
    this,
    when (actionType) {
        ActionType.BORROW -> R.color.borrow
        ActionType.ISSUE -> R.color.issued
        else -> R.color.return_green
    },
)

fun Context.categoryLabel(category: String?): String =
    if (category.isNullOrEmpty()) getString(R.string.no_category) else category

/** Adds a row_item view (title / colored status / details) to [container]. */
fun Context.addListRow(
    container: LinearLayout,
    title: String,
    status: String,
    statusColor: Int,
    details: String,
    onClick: (() -> Unit)? = null,
) {
    val row = LayoutInflater.from(this).inflate(R.layout.row_item, container, false)
    row.findViewById<TextView>(R.id.txtItemName).text = title
    row.findViewById<TextView>(R.id.txtItemStatus).apply {
        text = status
        setTextColor(statusColor)
    }
    row.findViewById<TextView>(R.id.txtItemDetails).text = details
    if (onClick != null) {
        row.setBackgroundResource(android.R.drawable.list_selector_background)
        row.setOnClickListener { onClick() }
    }
    container.addView(row)
}

/**
 * Fills [container] with history rows. [byItem]: the title is the item
 * (soldier card); otherwise the soldier (item screen).
 */
fun Context.fillHistory(
    container: LinearLayout,
    rows: List<HistoryRow>,
    byItem: Boolean,
    onRowClick: ((HistoryRow) -> Unit)? = null,
) {
    container.removeAllViews()
    if (rows.isEmpty()) {
        container.addView(
            TextView(this).apply {
                setText(R.string.history_empty)
                setTextColor(ContextCompat.getColor(context, R.color.text_secondary))
                textSize = 16f
                setPadding(0, 12, 0, 12)
            },
        )
        return
    }
    rows.forEach { h ->
        val title = if (byItem) h.itemName ?: h.qrId else h.userName ?: h.userId
        val reference = if (byItem) h.qrId else h.userId
        var details = getString(R.string.history_row_user, formatDateTime(h.timestamp), reference)
        if (h.pending) details += " · " + getString(R.string.history_pending)
        if (!h.note.isNullOrBlank()) details += "\n" + getString(R.string.history_note, h.note)
        addListRow(
            container,
            title,
            if (h.quantity > 1) getString(R.string.history_action_qty, actionLabel(h.actionType), h.quantity) else actionLabel(h.actionType),
            actionColor(h.actionType),
            details,
            onRowClick?.let { click -> { click(h) } },
        )
    }
}

/** "מושאל 3 · מונפק 2" for a soldier's holding of an item. */
fun Context.heldLabel(borrowed: Int, issued: Int): String = listOfNotNull(
    if (borrowed > 0) getString(R.string.held_borrowed, borrowed) else null,
    if (issued > 0) getString(R.string.held_issued, issued) else null,
).joinToString(" · ")
