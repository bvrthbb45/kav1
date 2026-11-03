package com.kav1.warehouse.domain.sync

sealed class SyncResult {
    /**
     * [rejected] actions were refused by the server and kept on the device
     * with the reason, so the operator can review them.
     */
    data class Success(
        val pushed: Int,
        val rejected: Int,
        val itemCount: Int,
        val userCount: Int,
    ) : SyncResult()

    /** Server unreachable (not tethered, server down, timeout). Nothing was lost. */
    object Offline : SyncResult()

    /** Server answered with an error; [message] is the server's Hebrew message if any. */
    data class ServerError(val code: Int, val message: String?) : SyncResult()

    /** Server answered 2xx with a body we could not understand. */
    object InvalidResponse : SyncResult()

    /** Anything else (e.g. local database failure). */
    data class Failed(val error: Throwable) : SyncResult()
}
