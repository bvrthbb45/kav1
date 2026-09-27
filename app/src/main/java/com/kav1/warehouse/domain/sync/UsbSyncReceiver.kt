package com.kav1.warehouse.domain.sync

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.widget.Toast
import com.kav1.warehouse.R
import com.kav1.warehouse.WarehouseApp
import com.kav1.warehouse.data.remote.ApiClient
import com.kav1.warehouse.data.remote.UsbInboxDto
import com.kav1.warehouse.data.remote.UsbOutboxDto
import com.kav1.warehouse.ui.syncResultMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.io.File

/**
 * Wired sync driven by the PC agent over ADB (server/app/usb_sync.py), for
 * tablets without network access to the server.
 *
 * The agent sends EXPORT, pulls outbox.json, runs it against the server,
 * pushes inbox.json and sends IMPORT. Progress is reported through small
 * marker files the agent polls. Only the ADB shell can send these broadcasts
 * (it holds DUMP; regular apps cannot).
 */
class UsbSyncReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val requestId = intent.getStringExtra(EXTRA_REQUEST_ID) ?: return
        val app = context.applicationContext as WarehouseApp
        val dir = syncDir(app) ?: return
        val pending = goAsync()
        scope.launch {
            try {
                when (intent.action) {
                    ACTION_EXPORT -> export(app, dir, requestId)
                    ACTION_IMPORT -> import(app, dir, requestId)
                }
            } catch (e: Exception) {
                Log.e(TAG, "USB sync ${intent.action} failed", e)
                writeAtomically(File(dir, doneFile(intent.action)), "$requestId|error|${e.javaClass.simpleName}")
            } finally {
                pending.finish()
            }
        }
    }

    private suspend fun export(app: WarehouseApp, dir: File, requestId: String) {
        val outbox = app.syncManager.exportForUsb(requestId)
        writeAtomically(File(dir, OUTBOX), ApiClient.gson.toJson(outbox))
        writeAtomically(File(dir, EXPORT_DONE), requestId)
    }

    private suspend fun import(app: WarehouseApp, dir: File, requestId: String) {
        val outbox = ApiClient.gson.fromJson(File(dir, OUTBOX).readText(), UsbOutboxDto::class.java)
        val inbox = ApiClient.gson.fromJson(File(dir, INBOX).readText(), UsbInboxDto::class.java)
        val result = if (outbox.requestId == requestId && inbox.requestId == requestId) {
            app.syncManager.importFromUsb(outbox, inbox)
        } else {
            SyncResult.InvalidResponse
        }
        File(dir, INBOX).delete()
        val message = app.syncResultMessage(result)
        val status = if (result is SyncResult.Success) "ok" else "error"
        writeAtomically(File(dir, IMPORT_DONE), "$requestId|$status|$message")
        Handler(Looper.getMainLooper()).post {
            Toast.makeText(app, app.getString(R.string.usb_sync_prefix, message), Toast.LENGTH_LONG).show()
        }
    }

    private fun writeAtomically(file: File, text: String) {
        val tmp = File(file.parentFile, file.name + ".tmp")
        tmp.writeText(text)
        if (!tmp.renameTo(file)) {
            file.writeText(text)
            tmp.delete()
        }
    }

    private fun doneFile(action: String?) = if (action == ACTION_IMPORT) IMPORT_DONE else EXPORT_DONE

    companion object {
        private const val TAG = "UsbSync"
        const val ACTION_EXPORT = "com.kav1.warehouse.USB_EXPORT"
        const val ACTION_IMPORT = "com.kav1.warehouse.USB_IMPORT"
        const val EXTRA_REQUEST_ID = "request_id"
        const val OUTBOX = "outbox.json"
        const val INBOX = "inbox.json"
        const val EXPORT_DONE = "export.done"
        const val IMPORT_DONE = "import.done"

        private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

        /** /sdcard/Android/data/com.kav1.warehouse/files/usb-sync (readable by adb, no permission needed). */
        fun syncDir(context: Context): File? =
            context.getExternalFilesDir(null)?.let { File(it, "usb-sync").apply { mkdirs() } }
    }
}
