package com.kav1.warehouse.data.remote

import com.google.gson.Gson
import com.kav1.warehouse.BuildConfig
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    val gson: Gson = Gson()

    fun create(baseUrl: String = BuildConfig.SERVER_BASE_URL): WarehouseApi {
        // Short connect timeout: devices are usually off the tether, and we
        // want to fail fast rather than hang the UI or a worker.
        val http = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(http)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(WarehouseApi::class.java)
    }
}
