package com.kav1.warehouse.domain.sync

import android.util.Log
import androidx.room.withTransaction
import com.google.gson.JsonParseException
import com.kav1.warehouse.data.local.ActionType
import com.kav1.warehouse.data.local.AppDatabase
import com.kav1.warehouse.data.local.AppPrefs
import com.kav1.warehouse.data.local.CategoryEntity
import com.kav1.warehouse.data.local.HistoryEntity
import com.kav1.warehouse.data.local.HoldingEntity
import com.kav1.warehouse.data.local.ItemEntity
import com.kav1.warehouse.data.local.ItemKind
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.UserEntity
import com.kav1.warehouse.data.local.CatalogChangeEntity
import com.kav1.warehouse.data.remote.ApiClient
import com.kav1.warehouse.data.remote.CatalogChangeDto
import com.kav1.warehouse.data.remote.ChangesResponseDto
import com.kav1.warehouse.data.remote.ErrorDto
import com.kav1.warehouse.data.remote.ItemUpsertDto
import com.kav1.warehouse.data.remote.PendingTransactionDto
import com.kav1.warehouse.data.remote.PullResponseDto
import com.kav1.warehouse.data.remote.PushResponseDto
import com.kav1.warehouse.data.remote.PushRequestDto
import com.kav1.warehouse.data.remote.UsbInboxDto
import com.kav1.warehouse.data.remote.UsbOutboxDto
import com.kav1.warehouse.data.remote.UserUpsertDto
import com.kav1.warehouse.data.remote.WarehouseApi
import com.kav1.warehouse.domain.stock.CatalogChanges
import com.kav1.warehouse.domain.stock.LocalStock
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
        // Deletes and id changes first (later edits use the new ids), then
        // management edits: new items/users must exist on the server before
        // actions that reference them.
        pushCatalogChanges()
        pushManagementEdits()
        val (pushed, rejected) = pushPending()
        val (itemCount, userCount) = pullState()
        prefs.lastSuccessfulSync = System.currentTimeMillis()
        return SyncResult.Success(pushed, rejected, itemCount, userCount)
    }

    /**
     * The upload form of a locally edited item. A consumable's local stock
     * already has this device's not-yet-pushed issues taken off, while the
     * server subtracts them again when they arrive; add them back here.
     */
    private suspend fun upsertDto(items: List<ItemEntity>): List<ItemUpsertDto> {
        val pendingIssues = db.pendingTransactionDao().getUnsynced()
            .filter { it.actionType == ActionType.ISSUE }
            .groupBy { it.qrId }
            .mapValues { (_, txs) -> txs.sumOf { it.quantity } }
        return items.map {
            val stock = if (it.kind == ItemKind.CONSUMABLE) it.quantity + (pendingIssues[it.qrId] ?: 0) else it.quantity
            ItemUpsertDto(it.qrId, it.name, it.category, stock, it.kind)
        }
    }

    private fun CatalogChangeEntity.toDto() = CatalogChangeDto(opId, op, targetId, newId)

    private suspend fun pushCatalogChanges() {
        val changes = db.catalogDao().getQueued()
        for (batch in changes.chunked(PUSH_BATCH_SIZE)) {
            applyChangesResult(batch, api.applyChanges(batch.map { it.toDto() }).bodyOrThrow())
        }
    }

    /**
     * Drops the changes the server answered. A refused change (e.g. the new
     * serial is taken on the server) is dropped too: the next pull brings
     * back the server's version.
     */
    private suspend fun applyChangesResult(sent: List<CatalogChangeEntity>, body: ChangesResponseDto) {
        val results = body.results ?: throw MalformedResponseException("results missing")
        results.filter { it.applied == false }.forEach { Log.w(TAG, "change refused: ${it.message}") }
        val sentIds = sent.mapTo(HashSet()) { it.opId }
        db.catalogDao().dropQueued(results.mapNotNull { it.opId }.filter { it in sentIds })
    }

    private suspend fun pushManagementEdits() {
        val items = db.itemDao().getPendingUpload()
        for (batch in items.chunked(PUSH_BATCH_SIZE)) {
            api.upsertItems(upsertDto(batch)).bodyOrThrow()
            db.withTransaction {
                batch.forEach { db.itemDao().markUploaded(it.qrId, it.name, it.category, it.quantity, it.kind) }
            }
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
        val pending = db.pendingTransactionDao().getUnsynced()
        var accepted = 0
        var rejected = 0
        // Batches keep each request small over a flaky link; a failure part-way
        // loses nothing because every batch is acknowledged individually.
        for (batch in pending.chunked(PUSH_BATCH_SIZE)) {
            val request = PushRequestDto(
                deviceId = prefs.deviceId,
                transactions = batch.map {
                    PendingTransactionDto(it.txId, it.qrId, it.userId, it.actionType, it.timestamp, it.quantity)
                },
            )
            val body = api.push(request).bodyOrThrow()
            val (a, r) = applyPushResult(batch.mapTo(HashSet()) { it.txId }, body)
            accepted += a
            rejected += r
        }
        return accepted to rejected
    }

    /** Drops accepted and flags rejected transactions among [sentIds]. @return (accepted, rejected). */
    private suspend fun applyPushResult(sentIds: Set<String>, body: PushResponseDto): Pair<Int, Int> {
        val dao = db.pendingTransactionDao()
        val acceptedIds = body.accepted ?: throw MalformedResponseException("accepted missing")
        db.withTransaction {
            dao.deleteByIds(acceptedIds.filter { it in sentIds })
            body.rejected.orEmpty().forEach { result ->
                val txId = result.txId ?: return@forEach
                if (txId in sentIds) {
                    dao.markFailed(txId, result.message ?: "")
                }
            }
        }
        return acceptedIds.size to body.rejected.orEmpty().size
    }

    /** @return (items, users) counts now stored locally. */
    private suspend fun pullState(): Pair<Int, Int> = applyPull(api.pull().bodyOrThrow())

    private suspend fun applyPull(body: PullResponseDto): Pair<Int, Int> {
        val items = body.items?.mapNotNull { dto ->
            val qrId = dto.qrId ?: return@mapNotNull null
            val status = dto.currentStatus ?: ItemStatus.AVAILABLE
            // Servers before 1.6 send no quantities: one unit, out if not available.
            val out = if (status == ItemStatus.AVAILABLE) 0 else 1
            ItemEntity(
                qrId = qrId,
                name = dto.name.orEmpty(),
                currentStatus = status,
                holderUserId = dto.holderUserId,
                lastActionAt = dto.lastActionAt,
                category = dto.category.orEmpty(),
                quantity = dto.quantity ?: 1,
                availableQty = dto.availableQty ?: (1 - out),
                borrowedQty = dto.borrowedQty ?: if (status == ItemStatus.BORROWED) 1 else 0,
                issuedQty = dto.issuedQty ?: if (status == ItemStatus.ISSUED) 1 else 0,
                kind = dto.kind ?: ItemKind.LOAN,
            )
        } ?: throw MalformedResponseException("items missing")
        val users = body.users?.mapNotNull { dto ->
            val userId = dto.userId ?: return@mapNotNull null
            UserEntity(userId, dto.fullName.orEmpty(), dto.unit.orEmpty())
        } ?: throw MalformedResponseException("users missing")
        val categories = body.categories.orEmpty().mapNotNull { dto ->
            dto.name?.let { CategoryEntity(it, dto.targetQty) }
        }
        val history = body.history.orEmpty().mapNotNull { dto ->
            HistoryEntity(
                txId = dto.txId ?: return@mapNotNull null,
                qrId = dto.qrId ?: return@mapNotNull null,
                userId = dto.userId ?: return@mapNotNull null,
                actionType = dto.actionType ?: return@mapNotNull null,
                timestamp = dto.timestamp ?: return@mapNotNull null,
                quantity = dto.quantity ?: 1,
            )
        }
        val holdings = body.holdings?.mapNotNull { dto ->
            HoldingEntity(
                qrId = dto.qrId ?: return@mapNotNull null,
                userId = dto.userId ?: return@mapNotNull null,
                borrowed = dto.borrowed ?: 0,
                issued = dto.issued ?: 0,
                since = dto.since,
            )
        } ?: items.filter { it.holderUserId != null && it.currentStatus != ItemStatus.AVAILABLE }.map {
            HoldingEntity(it.qrId, it.holderUserId!!, it.borrowedQty, it.issuedQty, it.lastActionAt)
        }

        db.withTransaction {
            db.itemDao().replaceAll(items)
            db.userDao().replaceAll(users)
            db.categoryDao().replaceAll(categories)
            db.historyDao().replaceAll(history)
            db.holdingDao().replaceAll(holdings)
            // Deletes and id changes made here after the outbox was sent.
            val changes = CatalogChanges(db)
            db.catalogDao().getQueued().forEach { changes.apply(it) }
            val stock = LocalStock(db)
            // Quantities edited here and not uploaded yet.
            db.itemDao().getPendingUpload().forEach { stock.refresh(it.qrId) }
            // Actions recorded after the push started are not on the server
            // yet; re-apply them so the device keeps showing what it did.
            db.pendingTransactionDao().getUnsynced().forEach {
                stock.apply(it.qrId, it.userId, it.actionType, it.quantity, it.timestamp)
            }
        }
        return items.size to users.size
    }

    // --- Wired sync over USB (ADB) ---------------------------------------
    //
    // The PC agent cannot open a connection to the server from the tablet
    // (no USB tethering on some devices), so it drives the exchange itself:
    // it asks for an outbox, sends it to the server, and hands back the
    // server's answers. The same bookkeeping as the network sync applies.

    /** Snapshot of everything waiting to be sent. */
    suspend fun exportForUsb(requestId: String): UsbOutboxDto = lock.withLock {
        UsbOutboxDto(
            requestId = requestId,
            deviceId = prefs.deviceId,
            transactions = db.pendingTransactionDao().getUnsynced().map {
                PendingTransactionDto(it.txId, it.qrId, it.userId, it.actionType, it.timestamp, it.quantity)
            },
            items = upsertDto(db.itemDao().getPendingUpload()),
            users = db.userDao().getPendingUpload().map { UserUpsertDto(it.userId, it.fullName, it.unit) },
            changes = db.catalogDao().getQueued().map { it.toDto() },
        )
    }

    /** Applies the server's answers to a previous [exportForUsb]. */
    suspend fun importFromUsb(outbox: UsbOutboxDto, inbox: UsbInboxDto): SyncResult = lock.withLock {
        try {
            if (inbox.requestId != outbox.requestId) {
                throw MalformedResponseException("request id mismatch")
            }
            inbox.changes?.let { answered ->
                val sent = outbox.changes.orEmpty().map {
                    CatalogChangeEntity(it.opId, it.op, it.targetId, it.newId, 0)
                }
                applyChangesResult(sent, answered)
            }
            db.withTransaction {
                inbox.itemsUploaded.orEmpty().forEach {
                    db.itemDao().markUploaded(
                        it.qrId,
                        it.name,
                        it.category.orEmpty(),
                        it.quantity ?: 1,
                        it.kind ?: ItemKind.LOAN,
                    )
                }
                inbox.usersUploaded.orEmpty().forEach {
                    db.userDao().markUploaded(it.userId, it.fullName, it.unit)
                }
            }
            val push = inbox.push ?: throw MalformedResponseException("push missing")
            val (pushed, rejected) = applyPushResult(outbox.transactions.mapTo(HashSet()) { it.txId }, push)
            val state = inbox.state ?: throw MalformedResponseException("state missing")
            val (itemCount, userCount) = applyPull(state)
            prefs.lastSuccessfulSync = System.currentTimeMillis()
            SyncResult.Success(pushed, rejected, itemCount, userCount)
        } catch (e: CancellationException) {
            throw e
        } catch (e: MalformedResponseException) {
            Log.w(TAG, "bad USB inbox: ${e.message}")
            SyncResult.InvalidResponse
        } catch (e: Exception) {
            Log.e(TAG, "USB import failed", e)
            SyncResult.Failed(e)
        }
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
