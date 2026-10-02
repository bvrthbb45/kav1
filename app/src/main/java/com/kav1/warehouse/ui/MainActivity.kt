package com.kav1.warehouse.ui

import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import android.view.LayoutInflater
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import com.kav1.warehouse.R
import com.kav1.warehouse.databinding.ActivityMainBinding
import com.kav1.warehouse.domain.sync.SyncResult
import com.kav1.warehouse.domain.sync.UsbLink
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    private val scanLauncher = registerForActivityResult(ScanContract()) { result ->
        val code = result.contents?.trim()
        if (code.isNullOrEmpty()) {
            toast(R.string.scan_cancelled)
        } else {
            startActivity(ItemActivity.intent(this, code))
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnScan.setOnClickListener { startScan() }
        binding.btnManualEntry.setOnClickListener { showManualEntry() }
        binding.btnSync.setOnClickListener { runManualSync() }
        binding.btnDashboard.setOnClickListener {
            startActivity(Intent(this, DashboardActivity::class.java))
        }
        binding.btnAdmin.setOnClickListener {
            requireAdminPin { startActivity(Intent(this, AdminActivity::class.java)) }
        }
        binding.txtFailed.setOnClickListener { showFailedTransactions() }

        observeLocalState()
        observeUsbLink()
    }

    override fun onResume() {
        super.onResume()
        renderLastSync()
    }

    private fun startScan() {
        val options = ScanOptions()
            .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            .setPrompt(getString(R.string.scan_prompt))
            .setBeepEnabled(true)
            .setOrientationLocked(true)
        scanLauncher.launch(options)
    }

    /** Fallback for damaged labels or devices whose camera can't focus. */
    private fun showManualEntry() {
        val view = LayoutInflater.from(this).inflate(R.layout.dialog_manual_entry, null)
        val edit = view.findViewById<EditText>(R.id.editCode)
        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.manual_entry_title)
            .setView(view)
            .setPositiveButton(R.string.btn_confirm, null)
            .setNegativeButton(R.string.btn_cancel, null)
            .create()
        val submit = {
            val code = edit.text.toString().trim()
            if (code.isEmpty()) {
                edit.error = getString(R.string.manual_entry_empty)
            } else {
                dialog.dismiss()
                startActivity(ItemActivity.intent(this, code))
            }
        }
        edit.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) submit()
            true
        }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { submit() }
        }
        dialog.show()
    }

    /**
     * Over the network when the server is reachable; otherwise, with the cable
     * plugged in, asks the PC agent to run a wired sync right away.
     */
    private fun runManualSync() {
        setSyncing(true)
        lifecycleScope.launch {
            try {
                val link = UsbLink.status(this@MainActivity)
                if (link.cableConnected && link.serverSeen()) {
                    syncOverUsb()
                    return@launch
                }
                val result = app.syncManager.sync()
                renderLastSync()
                when {
                    result != SyncResult.Offline -> toast(syncResultMessage(result))
                    link.cableConnected -> explainUsbProblem(link)
                    else -> toast(R.string.sync_offline_no_cable)
                }
            } finally {
                setSyncing(false)
            }
        }
    }

    private suspend fun syncOverUsb() {
        val before = app.prefs.lastUsbSync
        if (!UsbLink.requestSync(this)) {
            toast(R.string.sync_failed)
            return
        }
        toast(R.string.usb_sync_requested)
        val deadline = SystemClock.elapsedRealtime() + USB_SYNC_WAIT_MS
        while (SystemClock.elapsedRealtime() < deadline) {
            delay(500)
            if (app.prefs.lastUsbSync != before) {
                // UsbSyncReceiver already showed the result.
                renderLastSync()
                renderUsbStatus()
                return
            }
        }
        toast(R.string.usb_sync_timeout)
    }

    private fun explainUsbProblem(link: UsbLink.Status) {
        val message = if (link.adbEnabled) {
            // Picked up as soon as the server sees the tablet.
            UsbLink.requestSync(this)
            R.string.usb_problem_not_seen
        } else {
            R.string.usb_problem_debug_off
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.usb_problem_title)
            .setMessage(message)
            .setPositiveButton(R.string.btn_close, null)
            .show()
    }

    private fun observeUsbLink() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (true) {
                    renderUsbStatus()
                    delay(2_000)
                }
            }
        }
    }

    private fun renderUsbStatus() {
        val link = UsbLink.status(this)
        val lastUsb = app.prefs.lastUsbSync
        val lines = listOf(
            getString(if (link.cableConnected) R.string.usb_cable_on else R.string.usb_cable_off),
            getString(if (link.adbEnabled) R.string.usb_debug_on else R.string.usb_debug_off),
            getString(if (link.serverSeen()) R.string.usb_server_seen else R.string.usb_server_not_seen),
            if (lastUsb == 0L) {
                getString(R.string.usb_never_synced)
            } else {
                getString(R.string.usb_last_sync, formatDateTime(lastUsb))
            },
        )
        binding.txtUsbStatus.text = lines.joinToString("\n")
    }

    private fun setSyncing(syncing: Boolean) {
        binding.btnSync.isEnabled = !syncing
        binding.btnSync.setText(if (syncing) R.string.syncing else R.string.btn_manual_sync)
        binding.syncProgress.visibility = if (syncing) View.VISIBLE else View.GONE
    }

    private fun observeLocalState() {
        val repo = app.repository
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                val pendingEdits = combine(
                    repo.observePendingItemEdits(),
                    repo.observePendingUserEdits(),
                ) { items, users -> items + users }
                combine(
                    repo.observeUnsyncedCount(),
                    repo.observeFailedCount(),
                    repo.observeItemCount(),
                    repo.observeUserCount(),
                    pendingEdits,
                ) { pending, failed, items, users, edits -> intArrayOf(pending, failed, items, users, edits) }
                    .collect { (pending, failed, items, users, edits) ->
                        binding.txtPendingEdits.text = getString(R.string.status_pending_edits, edits)
                        binding.txtPendingEdits.visibility = if (edits > 0) View.VISIBLE else View.GONE
                        binding.txtPending.text = getString(R.string.status_pending, pending)
                        binding.txtFailed.text = getString(R.string.status_failed, failed)
                        binding.txtFailed.visibility = if (failed > 0) View.VISIBLE else View.GONE
                        binding.txtLocalData.text = getString(R.string.status_local_data, items, users)
                        // A background sync may have just finished.
                        renderLastSync()
                    }
            }
        }
    }

    private fun renderLastSync() {
        val last = app.prefs.lastSuccessfulSync
        binding.txtLastSync.text = if (last == 0L) {
            getString(R.string.status_never_synced)
        } else {
            getString(R.string.status_last_sync, formatDateTime(last))
        }
    }

    private fun showFailedTransactions() {
        lifecycleScope.launch {
            val failed = app.repository.getFailed()
            if (failed.isEmpty()) return@launch
            val lines = failed.map { tx ->
                val item = app.repository.getItem(tx.qrId)?.name ?: tx.qrId
                val user = app.repository.getUser(tx.userId)?.fullName ?: tx.userId
                getString(R.string.failed_row, actionLabel(tx.actionType), item, user, tx.syncError)
            }
            AlertDialog.Builder(this@MainActivity)
                .setTitle(R.string.failed_title)
                .setItems(lines.toTypedArray(), null)
                .setPositiveButton(R.string.failed_retry) { _, _ ->
                    lifecycleScope.launch {
                        app.repository.retryFailed()
                        toast(R.string.failed_requeued)
                    }
                }
                .setNegativeButton(R.string.failed_delete) { _, _ -> confirmDeleteFailed() }
                .setNeutralButton(R.string.btn_close, null)
                .show()
        }
    }

    private fun confirmDeleteFailed() {
        AlertDialog.Builder(this)
            .setMessage(R.string.failed_delete_confirm)
            .setPositiveButton(R.string.failed_delete) { _, _ ->
                lifecycleScope.launch {
                    app.repository.deleteFailed()
                    toast(R.string.failed_deleted)
                }
            }
            .setNegativeButton(R.string.btn_cancel, null)
            .show()
    }

    private companion object {
        const val USB_SYNC_WAIT_MS = 45_000L
    }
}
