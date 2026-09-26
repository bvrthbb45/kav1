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

/** Post-scan screen: item details plus borrow / return. */
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
        binding.btnReturn.setOnClickListener { startAction(ActionType.RETURN) }
        binding.btnBack.setOnClickListener { finish() }
        setActionsEnabled(false)
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
                binding.txtUnknown.visibility = View.VISIBLE
            } else {
                binding.txtName.text = getString(R.string.label_name, loaded.name)
                binding.txtStatus.text = getString(R.string.label_status, statusLabel(loaded.currentStatus))
                binding.txtUnknown.visibility = View.GONE
                setActionsEnabled(true)
            }
        }
    }

    private fun setActionsEnabled(enabled: Boolean) {
        binding.btnBorrow.isEnabled = enabled
        binding.btnReturn.isEnabled = enabled
    }

    private fun startAction(actionType: String) {
        val current = item ?: return
        lifecycleScope.launch {
            val users = app.repository.getUsers()
            if (users.isEmpty()) {
                toast(R.string.no_users)
                return@launch
            }
            UserPickerDialog.show(this@ItemActivity, users) { user ->
                confirmAction(current, user, actionType)
            }
        }
    }

    private fun confirmAction(item: ItemEntity, user: UserEntity, actionType: String) {
        val isBorrow = actionType == ActionType.BORROW
        val question = getString(
            if (isBorrow) R.string.confirm_borrow else R.string.confirm_return,
            item.name,
            user.fullName,
        )
        val warning = when {
            isBorrow && item.currentStatus == ItemStatus.BORROWED -> getString(R.string.warn_already_borrowed)
            !isBorrow && item.currentStatus == ItemStatus.AVAILABLE -> getString(R.string.warn_already_available)
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
