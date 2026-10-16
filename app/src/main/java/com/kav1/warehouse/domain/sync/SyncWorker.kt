package com.kav1.warehouse.domain.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.kav1.warehouse.WarehouseApp

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val syncManager = (applicationContext as WarehouseApp).syncManager
        return when (syncManager.sync()) {
            is SyncResult.Success -> Result.success()
            // Transient: try again with backoff, but don't retry forever — the
            // periodic job will pick the work up later anyway.
            SyncResult.Offline, is SyncResult.ServerError, SyncResult.InvalidResponse, is SyncResult.Failed ->
                if (runAttemptCount < MAX_ATTEMPTS) Result.retry() else Result.success()
        }
    }

    private companion object {
        const val MAX_ATTEMPTS = 5
    }
}
