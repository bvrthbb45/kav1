package com.kav1.warehouse

import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import androidx.multidex.MultiDexApplication
import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.remote.ApiClient
import com.kav1.warehouse.data.repository.InventoryRepository
import com.kav1.warehouse.domain.sync.SyncManager
import com.kav1.warehouse.domain.sync.SyncPrefs
import com.kav1.warehouse.domain.sync.SyncScheduler

/** Also acts as the (tiny) dependency container. */
class WarehouseApp : MultiDexApplication() {

    val database: AppDatabase by lazy { AppDatabase.get(this) }
    val repository: InventoryRepository by lazy { InventoryRepository(database) }
    val syncPrefs: SyncPrefs by lazy { SyncPrefs(this) }
    val syncManager: SyncManager by lazy { SyncManager(database, ApiClient.create(), syncPrefs) }

    override fun onCreate() {
        super.onCreate()
        // Force Hebrew (and therefore RTL layout, dialogs included) whatever
        // the device language is.
        AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags("he"))
        SyncScheduler.schedulePeriodic(this)
    }
}
