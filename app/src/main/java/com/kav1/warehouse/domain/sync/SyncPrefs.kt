package com.kav1.warehouse.domain.sync

import android.content.Context
import java.util.UUID

class SyncPrefs(context: Context) {
    private val prefs = context.applicationContext
        .getSharedPreferences("sync_prefs", Context.MODE_PRIVATE)

    /** Stable per-install id, sent with pushes for server-side logging. */
    val deviceId: String
        get() = prefs.getString(KEY_DEVICE_ID, null)
            ?: UUID.randomUUID().toString().also {
                prefs.edit().putString(KEY_DEVICE_ID, it).apply()
            }

    var lastSuccessfulSync: Long
        get() = prefs.getLong(KEY_LAST_SYNC, 0L)
        set(value) = prefs.edit().putLong(KEY_LAST_SYNC, value).apply()

    private companion object {
        const val KEY_DEVICE_ID = "device_id"
        const val KEY_LAST_SYNC = "last_sync"
    }
}
