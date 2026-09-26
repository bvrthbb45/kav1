package com.kav1.warehouse.data.remote

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

// Suppress wildcards so Retrofit sees List<ItemUpsertDto>, not List<? extends ...>.
@JvmSuppressWildcards
interface WarehouseApi {
    @POST("api/sync/push")
    suspend fun push(@Body request: PushRequestDto): Response<PushResponseDto>

    @GET("api/sync/pull")
    suspend fun pull(): Response<PullResponseDto>

    @POST("api/admin/items")
    suspend fun upsertItems(@Body items: List<ItemUpsertDto>): Response<UpsertResponseDto>

    @POST("api/admin/users")
    suspend fun upsertUsers(@Body users: List<UserUpsertDto>): Response<UpsertResponseDto>
}
