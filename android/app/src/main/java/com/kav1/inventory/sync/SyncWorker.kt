package com.kav1.inventory.sync

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.kav1.inventory.inventoryRepository
import retrofit2.HttpException
import java.io.IOException

/**
 * Pushes queued transactions first, then pulls fresh items/users. Push goes first so the
 * pull reflects this device's actions and doesn't briefly revert optimistic local state.
 */
class SyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val repository = applicationContext.inventoryRepository
        return try {
            val pushed = repository.pushPending()
            repository.pullUpdates()
            Log.i(TAG, "Sync complete: pushed $pushed transaction(s)")
            Result.success()
        } catch (e: IOException) {
            // Server unreachable (USB tether unplugged, server down, timeout): back off and retry.
            Log.w(TAG, "Sync failed, server unreachable (attempt $runAttemptCount)", e)
            retryOrFail()
        } catch (e: HttpException) {
            Log.w(TAG, "Sync failed with HTTP ${e.code()}", e)
            if (e.code() >= 500 || e.code() == 408 || e.code() == 429) retryOrFail() else Result.failure()
        }
    }

    private fun retryOrFail(): Result =
        if (runAttemptCount < MAX_ATTEMPTS) Result.retry() else Result.failure()

    private companion object {
        const val TAG = "SyncWorker"
        const val MAX_ATTEMPTS = 10
    }
}
