package com.kav1.inventory.data

import android.content.SharedPreferences
import android.util.Log
import androidx.core.content.edit
import androidx.room.withTransaction
import com.kav1.inventory.data.local.ActionType
import com.kav1.inventory.data.local.AppDatabase
import com.kav1.inventory.data.local.Item
import com.kav1.inventory.data.local.PendingTransaction
import com.kav1.inventory.data.local.User
import com.kav1.inventory.data.remote.SyncApi
import com.kav1.inventory.data.remote.dto.SyncPushRequest
import com.kav1.inventory.data.remote.dto.TransactionDto
import kotlinx.coroutines.flow.Flow
import java.util.UUID

class InventoryRepository(
    private val db: AppDatabase,
    private val api: SyncApi,
    private val prefs: SharedPreferences,
) {
    private val itemDao = db.itemDao()
    private val userDao = db.userDao()
    private val pendingDao = db.pendingTransactionDao()

    fun observeItem(qrId: String): Flow<Item?> = itemDao.observe(qrId)
    fun observeUsers(): Flow<List<User>> = userDao.observeAll()
    fun observePendingCount(): Flow<Int> = pendingDao.observeCount()

    suspend fun recordTransaction(qrId: String, userId: String, action: ActionType) {
        pendingDao.record(
            PendingTransaction(
                txId = UUID.randomUUID().toString(),
                qrId = qrId,
                userId = userId,
                actionType = action,
                timestamp = System.currentTimeMillis(),
            ),
        )
    }

    /** Pushes the whole queue in batches. Returns the number of transactions removed. */
    suspend fun pushPending(): Int {
        var removed = 0
        while (true) {
            val batch = pendingDao.oldest(PUSH_BATCH_SIZE)
            if (batch.isEmpty()) break

            val response = api.push(
                SyncPushRequest(
                    deviceId = deviceId(),
                    transactions = batch.map {
                        TransactionDto(it.txId, it.qrId, it.userId, it.actionType.name, it.timestamp)
                    },
                ),
            )
            val rejected = response.rejected.orEmpty()
            rejected.forEach { Log.w(TAG, "Server rejected tx ${it.txId}: ${it.reason}") }

            val done = (response.accepted.orEmpty() + rejected.map { it.txId }).distinct()
            if (done.isEmpty()) break // Server made no progress; avoid spinning on the same batch.
            pendingDao.deleteByIds(done)
            removed += done.size
            if (batch.size < PUSH_BATCH_SIZE) break
        }
        return removed
    }

    /** Pulls changed items/users since the last successful pull and stores them. */
    suspend fun pullUpdates() {
        val since = prefs.getLong(KEY_LAST_PULL, 0L)
        val response = api.pull(since.takeIf { it > 0 })

        db.withTransaction {
            // Items with unpushed local actions keep their optimistic status; the server's
            // value would be stale until those transactions are pushed.
            val pending = pendingDao.pendingQrIds().toSet()
            val incoming = response.items.orEmpty().map { Item(it.qrId, it.name, it.status) }
            itemDao.upsertAll(
                incoming.map { item ->
                    if (item.qrId in pending) {
                        itemDao.get(item.qrId)?.let { local -> item.copy(status = local.status) } ?: item
                    } else item
                },
            )
            userDao.upsertAll(response.users.orEmpty().map { User(it.userId, it.name) })
            response.deletedItemIds?.takeIf { it.isNotEmpty() }?.let { itemDao.deleteByIds(it) }
            response.deletedUserIds?.takeIf { it.isNotEmpty() }?.let { userDao.deleteByIds(it) }
        }
        prefs.edit { putLong(KEY_LAST_PULL, response.serverTime) }
    }

    private fun deviceId(): String =
        prefs.getString(KEY_DEVICE_ID, null) ?: UUID.randomUUID().toString().also {
            prefs.edit { putString(KEY_DEVICE_ID, it) }
        }

    private companion object {
        const val TAG = "InventoryRepository"
        const val PUSH_BATCH_SIZE = 100
        const val KEY_LAST_PULL = "last_pull_server_time"
        const val KEY_DEVICE_ID = "device_id"
    }
}
