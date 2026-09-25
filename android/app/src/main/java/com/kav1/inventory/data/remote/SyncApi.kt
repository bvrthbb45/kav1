package com.kav1.inventory.data.remote

import com.kav1.inventory.data.remote.dto.SyncPullResponse
import com.kav1.inventory.data.remote.dto.SyncPushRequest
import com.kav1.inventory.data.remote.dto.SyncPushResponse
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

interface SyncApi {
    /** Uploads locally recorded transactions. Non-2xx responses throw [retrofit2.HttpException]. */
    @POST("api/sync/push")
    suspend fun push(@Body request: SyncPushRequest): SyncPushResponse

    /**
     * Downloads items and users changed since [since] (epoch millis of the previous
     * `server_time`; omit or 0 for a full snapshot).
     */
    @GET("api/sync/pull")
    suspend fun pull(@Query("since") since: Long?): SyncPullResponse
}
