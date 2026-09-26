package com.kav1.warehouse.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

interface WarehouseApi {
    @POST("api/sync/push")
    suspend fun push(@Body request: PushRequestDto): Response<PushResponseDto>

    @GET("api/sync/pull")
    suspend fun pull(): Response<PullResponseDto>
}
