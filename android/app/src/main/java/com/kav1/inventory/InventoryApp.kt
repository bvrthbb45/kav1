package com.kav1.inventory

import android.app.Application
import android.content.Context
import com.kav1.inventory.data.InventoryRepository
import com.kav1.inventory.data.local.AppDatabase
import com.kav1.inventory.data.remote.ApiClient
import com.kav1.inventory.sync.SyncScheduler

class InventoryApp : Application() {

    val repository: InventoryRepository by lazy {
        InventoryRepository(
            db = AppDatabase.get(this),
            api = ApiClient.createSyncApi(),
            prefs = getSharedPreferences("sync", Context.MODE_PRIVATE),
        )
    }

    override fun onCreate() {
        super.onCreate()
        SyncScheduler.schedulePeriodic(this)
        SyncScheduler.syncNow(this)
    }
}

val Context.inventoryRepository: InventoryRepository
    get() = (applicationContext as InventoryApp).repository
