package com.kav1.warehouse.domain.sync

import android.util.Log
import androidx.room.withTransaction
import com.google.gson.JsonParseException
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.AppPrefs
import com.kav1.warehouse.data.local.ItemEntity
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.UserEntity
import com.kav1.warehouse.data.remote.ApiClient
import com.kav1.warehouse.data.remote.ErrorDto
import com.kav1.warehouse.data.remote.ItemUpsertDto
import com.kav1.warehouse.data.remote.PendingTransactionDto
import com.kav1.warehouse.data.remote.PushRequestDto
import com.kav1.warehouse.data.remote.UserUpsertDto
import com.kav1.warehouse.data.remote.WarehouseApi
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import retrofit2.Response
import java.io.IOException

/**
 * Sync flow: upload items/users added in the management screen, push the
 * outbox, drop what the server accepted, then replace the local items/users
 * with the server's state.
 *
 * Safe to call from the UI and from [SyncWorker] concurrently: runs are
 * serialised by a process-wide lock. Never throws for network/server
 * problems; those are reported through [SyncResult].
 */
class SyncManager(
    private val db: AppDatabase,
    /** Called per sync so a changed server address takes effect immediately. */
    private val apiProvider: () -> WarehouseApi,
    private val prefs: AppPrefs,
) {
    private lateinit var api: WarehouseApi

    suspend fun sync(): SyncResult = lock.withLock {
        try {
            runSync()
        } catch (e: CancellationException) {
            throw e
        } catch (e: IOException) {
            Log.i(TAG, "server unreachable: ${e.javaClass.simpleName}: ${e.message}")
            SyncResult.Offline
        } catch (e: JsonParseException) {
            Log.w(TAG, "malformed server response", e)
            SyncResult.InvalidResponse
        } catch (e: ServerErrorException) {
            Log.w(TAG, "server error ${e.code}: ${e.serverMessage}")
            SyncResult.ServerError(e.code, e.serverMessage)
        } catch (e: MalformedResponseException) {
            Log.w(TAG, "malformed server response: ${e.message}")
            SyncResult.InvalidResponse
        } catch (e: Exception) {
            Log.e(TAG, "sync failed", e)
            SyncResult.Failed(e)
        }
    }

    private suspend fun runSync(): SyncResult {
        api = apiProvider()
        // Management edits first: new items/users must exist on the server
        // before actions that reference them.
        pushManagementEdits()
        val (pushed, rejected) = pushPending()
        val (itemCount, userCount) = pullState()
        prefs.lastSuccessfulSync = System.currentTimeMillis()
        return SyncResult.Success(pushed, rejected, itemCount, userCount)
    }

    private suspend fun pushManagementEdits() {
        val items = db.itemDao().getPendingUpload()
        for (batch in items.chunked(PUSH_BATCH_SIZE)) {
            api.upsertItems(batch.map { ItemUpsertDto(it.qrId, it.name) }).bodyOrThrow()
            db.withTransaction { batch.forEach { db.itemDao().markUploaded(it.qrId, it.name) } }
        }
        val users = db.userDao().getPendingUpload()
        for (batch in users.chunked(PUSH_BATCH_SIZE)) {
            api.upsertUsers(batch.map { UserUpsertDto(it.userId, it.fullName, it.unit) }).bodyOrThrow()
            db.withTransaction {
                batch.forEach { db.userDao().markUploaded(it.userId, it.fullName, it.unit) }
            }
        }
    }

    /** @return (accepted, rejected) counts. */
    private suspend fun pushPending(): Pair<Int, Int> {
        val dao = db.pendingTransactionDao()
        val pending = dao.getUnsynced()
        var accepted = 0
        var rejected = 0
        // Batches keep each request small over a flaky link; a failure part-way
        // loses nothing because every batch is acknowledged individually.
        for (batch in pending.chunked(PUSH_BATCH_SIZE)) {
            val request = PushRequestDto(
                deviceId = prefs.deviceId,
                transactions = batch.map {
                    PendingTransactionDto(it.txId, it.qrId, it.userId, it.actionType, it.timestamp)
                },
            )
            val body = api.push(request).bodyOrThrow()
            val acceptedIds = body.accepted ?: throw MalformedResponseException("accepted missing")
            val batchIds = batch.mapTo(HashSet()) { it.txId }

            db.withTransaction {
                dao.deleteByIds(acceptedIds.filter { it in batchIds })
                body.rejected.orEmpty().forEach { result ->
                    val txId = result.txId ?: return@forEach
                    if (txId in batchIds) {
                        dao.markFailed(txId, result.message ?: "")
                    }
                }
            }
            accepted += acceptedIds.size
            rejected += body.rejected.orEmpty().size
        }
        return accepted to rejected
    }

    /** @return (items, users) counts now stored locally. */
    private suspend fun pullState(): Pair<Int, Int> {
        val body = api.pull().bodyOrThrow()
        val items = body.items?.mapNotNull { dto ->
            val qrId = dto.qrId ?: return@mapNotNull null
            ItemEntity(
                qrId = qrId,
                name = dto.name.orEmpty(),
                currentStatus = dto.currentStatus ?: ItemStatus.AVAILABLE,
                holderUserId = dto.holderUserId,
                lastActionAt = dto.lastActionAt,
            )
        } ?: throw MalformedResponseException("items missing")
        val users = body.users?.mapNotNull { dto ->
            val userId = dto.userId ?: return@mapNotNull null
            UserEntity(userId, dto.fullName.orEmpty(), dto.unit.orEmpty())
        } ?: throw MalformedResponseException("users missing")

        db.withTransaction {
            db.itemDao().replaceAll(items)
            db.userDao().replaceAll(users)
            // Actions recorded after the push started are not on the server
            // yet; re-apply them so the device keeps showing what it did.
            db.pendingTransactionDao().getUnsynced().forEach {
                db.itemDao().applyAction(
                    it.qrId,
                    ActionType.resultingStatus(it.actionType),
                    ActionType.resultingHolder(it.actionType, it.userId),
                    it.timestamp,
                )
            }
        }
        return items.size to users.size
    }

    private fun <T> Response<T>.bodyOrThrow(): T {
        if (isSuccessful) {
            return body() ?: throw MalformedResponseException("empty body")
        }
        val serverMessage = try {
            errorBody()?.string()?.let { ApiClient.gson.fromJson(it, ErrorDto::class.java)?.message }
        } catch (e: Exception) {
            null
        }
        throw ServerErrorException(code(), serverMessage)
    }

    private class ServerErrorException(val code: Int, val serverMessage: String?) :
        Exception("HTTP $code")

    private class MalformedResponseException(message: String) : Exception(message)

    private companion object {
        const val TAG = "SyncManager"
        const val PUSH_BATCH_SIZE = 200
        val lock = Mutex()
    }
}
