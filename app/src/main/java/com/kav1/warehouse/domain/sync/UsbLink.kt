package com.kav1.warehouse.domain.sync

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.provider.Settings
import java.io.File

/**
 * What the tablet can tell about the wired (ADB) link to the server PC.
 *
 * The PC agent (server/app/usb_sync.py) rewrites agent.alive every few
 * seconds while it sees the tablet, and picks up sync.request to sync at once.
 */
object UsbLink {
    private const val ALIVE = "agent.alive"
    private const val REQUEST = "sync.request"

    /** The agent polls every 3 s; a sync can keep it busy a little longer. */
    const val SEEN_WINDOW_MS = 20_000L

    data class Status(
        val cableConnected: Boolean,
        val adbEnabled: Boolean,
        /** When the server last touched the tablet, 0 if never. */
        val serverSeenAt: Long,
    ) {
        fun serverSeen(now: Long = System.currentTimeMillis()) =
            serverSeenAt > 0 && now - serverSeenAt in -5_000L..SEEN_WINDOW_MS
    }

    fun status(context: Context): Status = Status(
        cableConnected = isUsbPowered(context),
        adbEnabled = isAdbEnabled(context),
        serverSeenAt = aliveFile(context)?.takeIf { it.exists() }?.lastModified() ?: 0L,
    )

    /** Asks the PC agent to sync on its next poll; false if storage is unavailable. */
    fun requestSync(context: Context): Boolean {
        val dir = UsbSyncReceiver.syncDir(context) ?: return false
        return try {
            File(dir, REQUEST).writeText(System.currentTimeMillis().toString())
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun aliveFile(context: Context): File? =
        UsbSyncReceiver.syncDir(context)?.let { File(it, ALIVE) }

    private fun isUsbPowered(context: Context): Boolean {
        // Sticky broadcast: returns the current battery state without a receiver.
        val battery = context.applicationContext.registerReceiver(
            null,
            IntentFilter(Intent.ACTION_BATTERY_CHANGED),
        ) ?: return false
        return battery.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) == BatteryManager.BATTERY_PLUGGED_USB
    }

    private fun isAdbEnabled(context: Context): Boolean =
        Settings.Global.getInt(context.contentResolver, Settings.Global.ADB_ENABLED, 0) == 1
}
