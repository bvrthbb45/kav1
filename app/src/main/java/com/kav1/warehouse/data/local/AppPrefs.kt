package com.kav1.warehouse.data.local

import android.content.Context
import com.kav1.warehouse.BuildConfig
import java.util.UUID

/** Small device-local settings. */
class AppPrefs(context: Context) {
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

    /** Base URL of the sync server, always ending with "/". */
    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, null) ?: BuildConfig.SERVER_BASE_URL
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value).apply()

    /** PIN protecting the management screen. */
    var adminPin: String
        get() = prefs.getString(KEY_ADMIN_PIN, null) ?: DEFAULT_ADMIN_PIN
        set(value) = prefs.edit().putString(KEY_ADMIN_PIN, value).apply()

    companion object {
        const val DEFAULT_ADMIN_PIN = "1234"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_LAST_SYNC = "last_sync"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_ADMIN_PIN = "admin_pin"
    }
}
