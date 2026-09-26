package com.kav1.warehouse.ui

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.kav1.warehouse.R
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.ItemEntity
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.UserEntity
import com.kav1.warehouse.databinding.ActivityItemBinding
import com.kav1.warehouse.domain.sync.SyncScheduler
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/** Post-scan screen: item details plus borrow / issue / return. */
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
        setActionsEnabled(false)
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
                binding.txtHolder.visibility = View.GONE
                binding.txtLastAction.visibility = View.GONE
                binding.txtUnknown.visibility = View.VISIBLE
                binding.btnRegister.visibility = View.VISIBLE
                setActionsEnabled(false)
                return@launch
            }
            binding.txtName.text = getString(R.string.label_name, loaded.name)
            binding.txtStatus.text = getString(R.string.label_status, statusLabel(loaded.currentStatus))
            binding.txtStatus.setTextColor(statusColor(loaded.currentStatus))
            val holder = loaded.holderUserId?.let { id -> app.repository.getUser(id)?.fullName ?: id }
            binding.txtHolder.visibility = if (holder != null) View.VISIBLE else View.GONE
            binding.txtHolder.text = getString(R.string.label_holder, holder.orEmpty())
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
        lifecycleScope.launch {
            var users = app.repository.getUsers()
            if (users.isEmpty()) {
                toast(R.string.no_users)
                return@launch
            }
            // On return, the current holder is the most likely pick: list them first.
            current.holderUserId?.let { holderId ->
                val (holder, others) = users.partition { it.userId == holderId }
                users = holder + others
            }
            UserPickerDialog.show(this@ItemActivity, users) { user ->
                confirmAction(current, user, actionType)
            }
        }
    }

    private fun confirmAction(item: ItemEntity, user: UserEntity, actionType: String) {
        val question = getString(
            when (actionType) {
                ActionType.BORROW -> R.string.confirm_borrow
                ActionType.ISSUE -> R.string.confirm_issue
                else -> R.string.confirm_return
            },
            item.name,
            user.fullName,
        )
        val isReturn = actionType == ActionType.RETURN
        val warning = when {
            !isReturn && item.currentStatus != ItemStatus.AVAILABLE ->
                getString(R.string.warn_not_available, statusLabel(item.currentStatus))
            isReturn && item.currentStatus == ItemStatus.AVAILABLE ->
                getString(R.string.warn_already_available)
            else -> null
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.confirm_title)
            .setMessage(if (warning == null) question else "$warning\n\n$question")
            .setPositiveButton(R.string.btn_confirm) { _, _ -> save(item, user, actionType) }
            .setNegativeButton(R.string.btn_cancel, null)
            .show()
    }

    private fun save(item: ItemEntity, user: UserEntity, actionType: String) {
        setActionsEnabled(false)
        lifecycleScope.launch {
            try {
                app.repository.recordAction(item.qrId, user.userId, actionType)
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

        fun intent(context: Context, qrId: String): Intent =
            Intent(context, ItemActivity::class.java).putExtra(EXTRA_QR_ID, qrId)
    }
}
