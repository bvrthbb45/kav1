package com.kav1.warehouse.ui

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.InputFilter
import android.text.InputType
import android.util.Log
import android.view.View
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.kav1.warehouse.R
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.ItemEntity
import com.kav1.warehouse.data.local.ItemKind
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.UserEntity
import com.kav1.warehouse.databinding.ActivityItemBinding
import com.kav1.warehouse.domain.sync.SyncScheduler
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * Post-scan screen: item details, stock and holders, plus borrow / issue /
 * return. Items stocked in more than one unit ask how many units first.
 */
class ItemActivity : AppCompatActivity() {

    private lateinit var binding: ActivityItemBinding
    private lateinit var qrId: String
    private var item: ItemEntity? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityItemBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setTitle(R.string.item_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        qrId = intent.getStringExtra(EXTRA_QR_ID).orEmpty()
        binding.btnBorrow.setOnClickListener { startAction(ActionType.BORROW) }
        binding.btnIssue.setOnClickListener { startAction(ActionType.ISSUE) }
        binding.btnReturn.setOnClickListener { startAction(ActionType.RETURN) }
        binding.btnRegister.setOnClickListener {
            requireAdminPin { startActivity(AdminActivity.newItemIntent(this, qrId)) }
        }
        binding.btnBack.setOnClickListener { finish() }
        binding.txtHolder.setOnClickListener {
            item?.holderUserId?.let { startActivity(UserCardActivity.intent(this, it)) }
        }
        setActionsEnabled(false)
        observeHoldersAndHistory()
    }

    private fun observeHoldersAndHistory() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    app.repository.observeItemHolders(qrId).collect { holders ->
                        // Single-unit items show the holder line instead.
                        val show = holders.isNotEmpty() && (item?.quantity ?: 1) > 1
                        binding.txtHoldersTitle.visibility = if (show) View.VISIBLE else View.GONE
                        binding.listHolders.visibility = if (show) View.VISIBLE else View.GONE
                        binding.listHolders.removeAllViews()
                        holders.forEach { h ->
                            addListRow(
                                binding.listHolders,
                                h.fullName ?: h.userId,
                                heldLabel(h.borrowed, h.issued),
                                statusColor(if (h.borrowed > 0) ItemStatus.BORROWED else ItemStatus.ISSUED),
                                getString(
                                    R.string.history_row_user,
                                    h.since?.let { formatDateTime(it) } ?: getString(R.string.card_since_unknown),
                                    h.userId,
                                ),
                            ) { startActivity(UserCardActivity.intent(this@ItemActivity, h.userId)) }
                        }
                    }
                }
                app.repository.observeItemHistory(qrId).collect { rows ->
                    val visible = if (rows.isEmpty() && item == null) View.GONE else View.VISIBLE
                    binding.txtHistoryTitle.visibility = visible
                    binding.listHistory.visibility = visible
                    fillHistory(binding.listHistory, rows, byItem = false) { row ->
                        startActivity(UserCardActivity.intent(this@ItemActivity, row.userId))
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Also refreshes after registering the item in the management screen.
        loadItem()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    private fun loadItem() {
        lifecycleScope.launch {
            val loaded = app.repository.getItem(qrId)
            item = loaded
            binding.txtQr.text = getString(R.string.label_qr, qrId)
            if (loaded == null) {
                binding.txtName.text = qrId
                binding.txtStatus.text = getString(R.string.label_status, getString(R.string.status_unknown))
                binding.txtStock.visibility = View.GONE
                binding.txtHolder.visibility = View.GONE
                binding.txtCategory.visibility = View.GONE
                binding.txtLastAction.visibility = View.GONE
                binding.txtUnknown.visibility = View.VISIBLE
                binding.btnRegister.visibility = View.VISIBLE
                setActionsEnabled(false)
                return@launch
            }
            binding.txtName.text = loaded.name
            binding.txtCategory.visibility = View.VISIBLE
            binding.txtCategory.text = listOfNotNull(
                getString(R.string.label_category, categoryLabel(loaded.category)) +
                    " · " + getString(R.string.label_kind, kindLabel(loaded.kind)),
                loaded.department.ifBlank { null }?.let { getString(R.string.label_department, it) },
                loaded.location.ifBlank { null }?.let { getString(R.string.label_location, it) },
            ).joinToString("\n")
            val consumable = loaded.kind == ItemKind.CONSUMABLE
            val multi = loaded.quantity > 1 || consumable
            binding.txtStatus.visibility = if (multi) View.GONE else View.VISIBLE
            binding.txtStatus.text = getString(R.string.label_status, statusLabel(loaded.currentStatus))
            binding.txtStatus.setTextColor(statusColor(loaded.currentStatus))
            binding.txtStock.visibility = if (multi) View.VISIBLE else View.GONE
            binding.txtStock.text = if (consumable) {
                getString(R.string.label_stock_consumable, loaded.quantity, loaded.issuedQty)
            } else {
                getString(R.string.label_stock, loaded.quantity, loaded.availableQty, loaded.borrowedQty)
            }
            // Loans are borrowed and returned; consumables are only issued.
            binding.btnIssue.visibility = if (consumable) View.VISIBLE else View.GONE
            binding.btnBorrow.visibility = if (consumable) View.GONE else View.VISIBLE
            binding.btnReturn.visibility = if (consumable) View.GONE else View.VISIBLE
            val holder = if (multi) {
                null
            } else {
                loaded.holderUserId?.let { id -> app.repository.getUser(id)?.fullName ?: id }
            }
            binding.txtHolder.visibility = if (holder != null) View.VISIBLE else View.GONE
            binding.txtHolder.text = getString(
                R.string.label_holder,
                getString(R.string.holder_open_card, holder.orEmpty()),
            )
            binding.txtLastAction.visibility = if (loaded.lastActionAt != null) View.VISIBLE else View.GONE
            loaded.lastActionAt?.let {
                binding.txtLastAction.text = getString(R.string.label_last_action, formatDateTime(it))
            }
            binding.txtUnknown.visibility = View.GONE
            binding.btnRegister.visibility = View.GONE
            setActionsEnabled(true)
        }
    }

    private fun setActionsEnabled(enabled: Boolean) {
        binding.btnBorrow.isEnabled = enabled
        binding.btnIssue.isEnabled = enabled
        binding.btnReturn.isEnabled = enabled
    }

    private fun startAction(actionType: String) {
        val current = item ?: return
        if (actionType == ActionType.RETURN) {
            // Who returns first; the amount defaults to what they hold.
            pickUser(current, actionType) { user, held ->
                askQuantity(current, actionType, user, held) { qty -> confirmAction(current, user, actionType, qty, held) }
            }
        } else {
            // "How many?" right after the scan, then the soldier.
            askQuantity(current, actionType, null, 0) { qty ->
                pickUser(current, actionType) { user, held -> confirmAction(current, user, actionType, qty, held) }
            }
        }
    }

    /** Opens the soldier picker; [onPicked] gets the soldier and how many units they hold now. */
    private fun pickUser(current: ItemEntity, actionType: String, onPicked: (UserEntity, Int) -> Unit) {
        lifecycleScope.launch {
            var users = app.repository.getUsers()
            if (users.isEmpty()) {
                toast(R.string.no_users)
                return@launch
            }
            val holdings = app.repository.getHoldingsForItem(current.qrId).associateBy { it.userId }
            if (actionType == ActionType.RETURN && holdings.isNotEmpty()) {
                // Current holders are the likeliest pick: list them first.
                val (holders, others) = users.partition { it.userId in holdings }
                users = holders + others
            }
            UserPickerDialog.show(this@ItemActivity, users) { user ->
                val held = holdings[user.userId]?.let { it.borrowed + it.issued } ?: 0
                onPicked(user, held)
            }
        }
    }

    /** Asks for the number of units; single-unit items skip the question. */
    private fun askQuantity(
        current: ItemEntity,
        actionType: String,
        user: UserEntity?,
        held: Int,
        onQuantity: (Int) -> Unit,
    ) {
        // Single-unit loans need no question; consumables are always counted.
        if (current.quantity <= 1 && current.kind != ItemKind.CONSUMABLE) {
            onQuantity(1)
            return
        }
        val (view, edit) = dialogEditText(R.string.quantity_hint, InputType.TYPE_CLASS_NUMBER)
        val suggested = if (actionType == ActionType.RETURN) held.coerceAtLeast(1) else 1
        edit.setText(suggested.toString())
        edit.setSelectAllOnFocus(true)
        val message = if (actionType == ActionType.RETURN) {
            getString(R.string.quantity_return_message, user?.fullName.orEmpty(), held)
        } else if (current.kind == ItemKind.CONSUMABLE) {
            getString(R.string.quantity_consumable_message, current.quantity)
        } else {
            getString(R.string.quantity_take_message, current.availableQty, current.quantity)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle(
                when (actionType) {
                    ActionType.BORROW -> R.string.quantity_title_borrow
                    ActionType.ISSUE -> R.string.quantity_title_issue
                    else -> R.string.quantity_title_return
                },
            )
            .setMessage(message)
            .setView(view)
            .setPositiveButton(R.string.btn_continue, null)
            .setNegativeButton(R.string.btn_cancel, null)
            .create()
        dialog.setOnShowListener {
            edit.requestFocus()
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val qty = edit.text.toString().trim().toIntOrNull()
                if (qty == null || qty < 1 || qty > MAX_QUANTITY) {
                    edit.error = getString(R.string.quantity_invalid)
                } else {
                    dialog.dismiss()
                    onQuantity(qty)
                }
            }
        }
        dialog.show()
    }

    private fun confirmAction(item: ItemEntity, user: UserEntity, actionType: String, qty: Int, held: Int) {
        val multi = item.quantity > 1 || item.kind == ItemKind.CONSUMABLE
        val question = if (multi) {
            getString(
                when (actionType) {
                    ActionType.BORROW -> R.string.confirm_borrow_qty
                    ActionType.ISSUE -> R.string.confirm_issue_qty
                    else -> R.string.confirm_return_qty
                },
                qty,
                item.name,
                user.fullName,
            )
        } else {
            getString(
                when (actionType) {
                    ActionType.BORROW -> R.string.confirm_borrow
                    ActionType.ISSUE -> R.string.confirm_issue
                    else -> R.string.confirm_return
                },
                item.name,
                user.fullName,
            )
        }
        val isReturn = actionType == ActionType.RETURN
        val warning = when {
            item.kind == ItemKind.CONSUMABLE && item.quantity == 0 -> getString(R.string.consumable_out_of_stock)
            item.kind == ItemKind.CONSUMABLE && qty > item.quantity ->
                getString(R.string.warn_consumable_not_enough, item.quantity)
            multi && !isReturn && qty > item.availableQty -> getString(R.string.warn_not_enough, item.availableQty)
            multi && isReturn && qty > held -> getString(R.string.warn_return_more, held)
            multi -> null
            !isReturn && item.currentStatus != ItemStatus.AVAILABLE ->
                getString(R.string.warn_not_available, statusLabel(item.currentStatus))
            isReturn && item.currentStatus == ItemStatus.AVAILABLE ->
                getString(R.string.warn_already_available)
            else -> null
        }
        // Optional note, saved with the action (e.g. "לתרגיל", "הוחזר פגום").
        val (noteView, noteEdit) = dialogEditText(R.string.note_hint, InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)
        noteEdit.filters = arrayOf(InputFilter.LengthFilter(MAX_NOTE))
        AlertDialog.Builder(this)
            .setTitle(R.string.confirm_title)
            .setMessage(if (warning == null) question else "$warning\n\n$question")
            .setView(noteView)
            .setPositiveButton(R.string.btn_confirm) { _, _ ->
                save(item, user, actionType, qty, noteEdit.text.toString().trim())
            }
            .setNegativeButton(R.string.btn_cancel, null)
            .show()
    }

    private fun save(item: ItemEntity, user: UserEntity, actionType: String, qty: Int, note: String) {
        setActionsEnabled(false)
        lifecycleScope.launch {
            try {
                app.repository.recordAction(item.qrId, user.userId, actionType, qty, note)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "saving action failed", e)
                toast(R.string.action_save_failed)
                setActionsEnabled(true)
                return@launch
            }
            toast(R.string.action_saved)
            SyncScheduler.requestSoon(applicationContext)
            finish()
        }
    }

    companion object {
        private const val TAG = "ItemActivity"
        private const val EXTRA_QR_ID = "qr_id"
        private const val MAX_QUANTITY = 1_000_000
        private const val MAX_NOTE = 500

        fun intent(context: Context, qrId: String): Intent =
            Intent(context, ItemActivity::class.java).putExtra(EXTRA_QR_ID, qrId)
    }
}
